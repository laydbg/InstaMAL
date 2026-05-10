"""
Rubric checks for menuPass scenario 1.

Usage:
    python test_menuPass_scenario1.py [--regen] [-n N]

Flags:
    --regen     Regenerate model instances even if they already exist.
    --n N       Number of instances to generate/check (default: 100).

Directory layout:
    evaluation/
        specifications/menuPass_scenario1.spec
        tests/
            test_menuPass_scenario1.py
            testdata/org.mal-lang.coreLang-1.0.0.mar
            generated/menuPass_scenario1/
                model_0.yml ... model_N.yml
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import traceback
import yaml

from instamal import ModelInstantiator

# Config

N_INSTANCES = 100

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_DIR = os.path.join(_THIS_DIR, '..')

SPEC_PATH = os.path.join(_EVAL_DIR, 'specifications', 'menuPass_scenario1.spec')
LANG_PATH = os.path.join(_THIS_DIR, 'testdata', 'org.mal-lang.coreLang-1.0.0.mar')
OUT_DIR = os.path.join(_THIS_DIR, 'generated', 'menuPass_scenario1')
MODEL_PREFIX = 'model_'

# Generation


def generate_instances(n: int, regen: bool) -> None:
    existing = glob.glob(os.path.join(OUT_DIR, f'{MODEL_PREFIX}*.yml'))
    if not regen and len(existing) >= n:
        print(
            f'[generate] {len(existing)} instances already in {OUT_DIR}, skipping (--regen to overwrite)\n'
        )
        return

    print(f'[generate] generating {n} instances to {OUT_DIR}')

    if existing:
        for path in existing:
            try:
                os.remove(path)
            except OSError as e:
                print(f'[generate] warning: failed to delete {path}: {e}')

    ModelInstantiator(SPEC_PATH, LANG_PATH, interactive=False).instantiate(
        OUT_DIR, n=n, modelPrefix=MODEL_PREFIX
    )
    print('[generate] done\n')


# Loading


def _load_yaml(path: str) -> dict[int, dict]:
    with open(path) as f:
        raw = yaml.safe_load(f)

    if 'model' in raw:
        assets_raw = raw['model'].get('assets', {}) or {}
    else:
        assets_raw = raw.get('assets', {}) or {}

    assets: dict[int, dict] = {}
    for aid, adict in assets_raw.items():
        raw_assoc = adict.get('associated_assets', {}) or {}
        normalised = {}
        for field, targets in raw_assoc.items():
            if isinstance(targets, dict):
                normalised[field] = set(int(k) for k in targets)
            elif isinstance(targets, list):
                normalised[field] = set(int(k) for k in targets)
            else:
                normalised[field] = set()
        assets[int(aid)] = {
            'id': int(aid),
            'name': adict.get('name', ''),
            'type': adict.get('type', ''),
            'defenses': adict.get('defenses', {}) or {},
            'assoc': normalised,
        }
    return assets


def load_instances(n: int) -> list[dict[int, dict]]:
    out = []
    for i in range(n):
        path = os.path.join(OUT_DIR, f'{MODEL_PREFIX}{i}.yml')
        if not os.path.exists(path):
            print(f'  [WARNING] missing {path}', file=sys.stderr)
            continue
        out.append(_load_yaml(path))
    return out


# Graph helpers


def assoc(assets: dict, aid: int, field: str) -> set[int]:
    return assets[aid]['assoc'].get(field, set())


def of_type(assets: dict, t: str) -> set[int]:
    return {k for k, v in assets.items() if v['type'] == t}


# Motif resolvers


def machines(assets: dict) -> set[int]:
    """M1: Applications connected to at least one ConnectionRule."""
    return {
        aid
        for aid, a in assets.items()
        if a['type'] == 'Application'
        and (
            assoc(assets, aid, 'appConnections')
            or assoc(assets, aid, 'outgoingAppConnections')
        )
    }


def workstations(assets: dict) -> set[int]:
    """M2: Machines that initiate outbound connections."""
    return {
        aid for aid in machines(assets) if assoc(assets, aid, 'outgoingAppConnections')
    }


def internal_machines(assets: dict) -> set[int]:
    """M3: Machines with no outbound connections."""
    return {
        aid
        for aid in machines(assets)
        if not assoc(assets, aid, 'outgoingAppConnections')
    }


def ntds_data(assets: dict) -> int | None:
    """M4: Data asset with the most information entries (the DC credential store)."""
    best, best_n = None, -1
    for aid, a in assets.items():
        if a['type'] != 'Data':
            continue
        n = len(assoc(assets, aid, 'information'))
        if n > best_n:
            best, best_n = aid, n
    return best


def domain_controller(assets: dict) -> int | None:
    """M5: The internal machine that contains the NTDS.dit."""
    ntds = ntds_data(assets)
    if ntds is None:
        return None
    candidates = assoc(assets, ntds, 'containingApp') & internal_machines(assets)

    assert len(candidates) == 1, 'ntds_data must be contained in one machine only'
    return list(candidates)[0]


def servers(assets: dict) -> set[int]:
    """M6: Internal machines that are not the DC."""
    dc = domain_controller(assets)
    return internal_machines(assets) - ({dc} if dc is not None else set())


def sam_data(assets: dict, app: int) -> int | None:
    """M7: Local account database on app (contained Data where every information
    entry is a hash and at least one hash's origCreds are scoped to app)."""
    for data in assoc(assets, app, 'containedData'):
        info = assoc(assets, data, 'information')
        if not info:
            continue
        all_hashes = True
        has_local = 0
        for cred in info:
            if cred not in assets:
                all_hashes = False
                break
            origs = assoc(assets, cred, 'origCreds')
            if not origs:
                all_hashes = False
                break
            assert len(origs) == 1, 'A credential hash has only one origCreds'
            orig = list(origs)[0]
            if orig not in assets:
                continue
            for ident in assoc(assets, orig, 'identities'):
                scope = assoc(assets, ident, 'highPrivApps') | assoc(
                    assets, ident, 'lowPrivApps'
                )
                if app in scope:
                    has_local += 1
        if all_hashes and has_local >= 1:
            return data
    return None


def lsass_data(assets: dict, app: int) -> int | None:
    """M8: In-memory credential store on app (contained Data with a plaintext
    Credentials entry (has hashes) whose identity is scoped to app)."""
    for data in assoc(assets, app, 'containedData'):
        if data not in assets:
            continue
        for cred in assoc(assets, data, 'information'):
            if cred not in assets:
                continue
            if not assoc(assets, cred, 'hashes'):
                continue
            for ident in assoc(assets, cred, 'identities'):
                scope = assoc(assets, ident, 'highPrivApps') | assoc(
                    assets, ident, 'lowPrivApps'
                )
                if app in scope:
                    return data
    return None


def domain_admin(assets: dict) -> int | None:
    """M10: Identity with credentials and highPrivApps containing the DC."""
    dc = domain_controller(assets)
    if dc is None:
        return None
    for aid, a in assets.items():
        if a['type'] != 'Identity':
            continue
        if assoc(assets, aid, 'credentials') and dc in assoc(
            assets, aid, 'highPrivApps'
        ):
            return aid
    return None


def msp_admin(assets: dict) -> int | None:
    """M9: Identity with highPrivApps equal to the full machine set."""
    candidates = set()
    machine_set = machines(assets)
    for aid, a in assets.items():
        if (
            a['type'] == 'Identity'
            and assoc(assets, aid, 'highPrivApps') == machine_set
        ):
            candidates.add(aid)
    if not candidates:
        return None
    candidates.discard(domain_admin(assets))
    assert len(candidates) == 1, 'There should only be one candidate for msp_admin'
    return list(candidates)[0]


def local_users(
    assets: dict, machine_set: set[int], exclude: set[int]
) -> dict[int, int]:
    """M11: Identities scoped to exactly one machine, not in exclude, with a locally stored hash.

    Returns {identity_id: machine_id}.
    """
    result = {}
    for aid, a in assets.items():
        if a['type'] != 'Identity' or aid in exclude:
            continue
        scope = assoc(assets, aid, 'highPrivApps') | assoc(assets, aid, 'lowPrivApps')
        if len(scope) != 1:
            continue
        mid = list(scope)[0]
        if mid not in machine_set:
            continue
        if aid == msp_admin(assets) or aid == domain_admin(assets):
            continue
        for cred in assoc(assets, aid, 'credentials'):
            if cred not in assets:
                continue
            for chash in assoc(assets, cred, 'hashes'):
                if chash not in assets:
                    continue
                for data in assoc(assets, chash, 'containerData'):
                    if data in assets and mid in assoc(assets, data, 'containingApp'):
                        result[aid] = mid
    return result


def external_network(assets: dict) -> int | None:
    """M12: Network whose CRs have outbound application roles and no
    bidirectional role."""
    candidates = set()
    for nid, a in assets.items():
        if a['type'] != 'Network':
            continue
        crs = assoc(assets, nid, 'netConnections')
        if not crs:
            continue
        has_out = False
        has_bidir = False
        for cr in crs:
            if cr not in assets:
                continue
            if assoc(assets, cr, 'applications'):
                has_bidir = True
                break
            if assoc(assets, cr, 'outApplications'):
                has_out = True
        if not has_bidir and has_out:
            candidates.add(nid)
    if not candidates:
        return None
    assert len(candidates) == 1, (
        'There should only be one candidate for external_network'
    )
    return list(candidates)[0]


def internal_networks(assets: dict) -> set[int]:
    """M13: Networks with bidirectional application participation."""
    out = set()
    for nid, a in assets.items():
        if a['type'] != 'Network':
            continue
        if any(
            assoc(assets, cr, 'applications')
            for cr in assoc(assets, nid, 'netConnections')
            if cr in assets
        ):
            out.add(nid)
    return out


def internet_facing_apps(assets: dict) -> set[int]:
    """M14: Applications reachable from the external network as server-side endpoints."""
    ext = external_network(assets)
    if ext is None:
        return set()
    result = set()
    for cr in assoc(assets, ext, 'netConnections'):
        if cr not in assets:
            continue
        result |= assoc(assets, cr, 'applications')
        result |= assoc(assets, cr, 'inApplications')
        result |= assoc(assets, cr, 'outApplications')
    for cr1 in assoc(assets, ext, 'outgoingNetConnections'):
        for net in assoc(assets, cr1, 'inNetworks'):
            if net == ext:
                continue
            for cr2 in assoc(assets, net, 'netConnections'):
                result |= assoc(assets, cr2, 'inApplications')
    return result


# Check helpers


def _header(label: str) -> None:
    print('=' * 70)
    print(label)
    print('=' * 70)


def _report(
    label: str, n: int, failures: list[tuple[int, str]], require_all: bool = False
) -> None:
    passed = n - len(failures)
    pct = 100.0 * passed / n if n else 0.0
    ok = not failures if require_all else True
    print(f'  {label}: {passed}/{n} passed ({pct:.0f}%) -> {"PASS" if ok else "FAIL"}')
    for idx, reason in failures[:10]:
        print(f'    instance {idx:3d}: {reason}')
    if len(failures) > 10:
        print(f'    ... and {len(failures) - 10} more')
    print()


# Checks


def check_r1(instances: list) -> None:
    _header('R1: Domain Controller structure')
    failures = []
    for idx, a in enumerate(instances):
        ntds = ntds_data(a)
        dc_count = sum(
            1
            for m in internal_machines(a)
            if ntds and ntds in assoc(a, m, 'containedData')
        )
        if dc_count != 1:
            failures.append((idx, f'DC count = {dc_count}'))
            continue

        dc = domain_controller(a)

        assert dc is not None and ntds is not None

        reachable = any(
            net in internal_networks(a)
            for cr in assoc(a, dc, 'appConnections')
            if cr in a
            for net in assoc(a, cr, 'networks')
        )
        if not reachable:
            failures.append((idx, 'DC not connected to any internal network'))
            continue

        chain_ok = any(
            dc in assoc(a, ident, 'highPrivApps')
            for cred in assoc(a, ntds, 'information')
            if cred in a
            for orig in assoc(a, cred, 'origCreds')
            if orig in a
            for ident in assoc(a, orig, 'identities')
        )
        if not chain_ok:
            failures.append(
                (
                    idx,
                    'NTDS.dit has no credential chain to a DA-level identity on the DC',
                )
            )

    _report('R1', len(instances), failures, require_all=True)


def check_r2(instances: list) -> None:
    _header('R2: MSP Admin covers all machines')
    failures = []
    for idx, a in enumerate(instances):
        if msp_admin(a) is None:
            failures.append(
                (
                    idx,
                    f'no Identity with highPrivApps == all {len(machines(a))} machines',
                )
            )
    _report('R2', len(instances), failures, require_all=True)


def check_r3(instances: list) -> None:
    _header('R3: Workstation SAM + LSASS linkage')
    failures = []
    for idx, a in enumerate(instances):
        found = False
        for ws in workstations(a):
            sam = sam_data(a, ws)
            lsass = lsass_data(a, ws)
            if sam is None or lsass is None or sam == lsass:
                continue
            sam_info = assoc(a, sam, 'information')
            lsass_info = assoc(a, lsass, 'information')
            if any(
                plain in lsass_info
                for chash in sam_info
                if chash in a
                for plain in assoc(a, chash, 'origCreds')
            ):
                found = True
                break
        if not found:
            failures.append(
                (
                    idx,
                    f'{len(workstations(a))} workstation(s), none with linked SAM+LSASS pair',
                )
            )
    _report('R3', len(instances), failures, require_all=True)


def check_r4(instances: list) -> None:
    _header('R4: Workstation / server count variation')
    ws_counts = [len(workstations(a)) for a in instances]
    srv_counts = [len(servers(a)) for a in instances]
    dist_ws = sorted(set(ws_counts))
    dist_srv = sorted(set(srv_counts))
    both_one = sum(1 for w, s in zip(ws_counts, srv_counts) if w == 1 and s == 1)
    n = len(instances)

    t_ws, t_srv, t_both = 3, 2, n // 5
    print(
        f'  distinct workstation counts : {dist_ws} (need >={t_ws}) -> {"PASS" if len(dist_ws) >= t_ws else "FAIL"}'
    )
    print(
        f'  distinct server counts      : {dist_srv} (need >={t_srv}) -> {"PASS" if len(dist_srv) >= t_srv else "FAIL"}'
    )
    print(
        f'  instances with ws=1,srv=1   : {both_one}/{n} (need <={t_both}) -> {"PASS" if both_one <= t_both else "FAIL"}'
    )
    print(
        f'  R4 overall: {"PASS" if len(dist_ws) >= t_ws and len(dist_srv) >= t_srv and both_one <= t_both else "FAIL"}\n'
    )


def check_r5(instances: list) -> None:
    _header('R5: External network exposure variation')
    e_counts = []
    third_seg = []
    for a in instances:
        ext = external_network(a)
        if ext is None:
            e_counts.append(0)
            third_seg.append(False)
        else:
            e = {
                v
                for cr in assoc(a, ext, 'netConnections')
                if cr in a
                for v in (
                    assoc(a, cr, 'inApplications') | assoc(a, cr, 'outApplications')
                )
            }
            third_seg_e = {
                v
                for cr1 in assoc(a, ext, 'outgoingNetConnections')
                if cr1 in a
                for net in assoc(a, cr1, 'inNetworks')
                if net in a and net != ext
                for cr2 in assoc(a, net, 'netConnections')
                if cr2 in a
                for v in assoc(a, cr2, 'inApplications')
            }
            e_counts.append(len(e | third_seg_e))
            third_seg.append(bool(len(third_seg_e)))

    c1 = sum(1 for e in e_counts if e == 1)
    c2 = sum(1 for e in e_counts if e >= 2)
    c3 = sum(third_seg)
    n = len(instances)
    t = n // 10
    print(
        f'  E=1 instances         : {c1}/{n} (need >={t}) -> {"PASS" if c1 >= t else "FAIL"}'
    )
    print(
        f'  E>=2 instances        : {c2}/{n} (need >={t}) -> {"PASS" if c2 >= t else "FAIL"}'
    )
    print(
        f'  third-segment present : {c3}/{n} (need >=1)  -> {"PASS" if c3 >= 1 else "FAIL"}'
    )
    print(f'  R5 overall: {"PASS" if c1 >= t and c2 >= t and c3 >= 1 else "FAIL"}\n')


def check_r6(instances: list) -> None:
    _header('R6: Domain admin credential sprawl')
    dc_only, sprawled, unclassified = 0, 0, 0
    for a in instances:
        da = domain_admin(a)
        if da is None:
            unclassified += 1
            continue
        containers = {
            app
            for orig in assoc(a, da, 'credentials')
            if orig in a
            for chash in assoc(a, orig, 'hashes')
            if chash in a
            for data in assoc(a, chash, 'containerData')
            if data in a
            for app in assoc(a, data, 'containingApp')
        }
        if not containers:
            unclassified += 1
        elif containers == {domain_controller(a)}:
            dc_only += 1
        else:
            sprawled += 1

    t = len(instances) // 3
    n = len(instances)
    print(
        f'  DC-only     : {dc_only}/{n} (need >={t}) -> {"PASS" if dc_only >= t else "FAIL"}'
    )
    print(
        f'  sprawled    : {sprawled}/{n} (need >={t}) -> {"PASS" if sprawled >= t else "FAIL"}'
    )
    if unclassified:
        print(f'  unclassified (no DA / no hashes)  : {unclassified}')
    print(f'  R6 overall: {"PASS" if dc_only >= t and sprawled >= t else "FAIL"}\n')


def check_r7(instances: list) -> None:
    _header('R7: Local user privilege variation')
    all_std, has_admin = 0, 0
    for a in instances:
        ws = workstations(a)
        srv = servers(a)
        msp = msp_admin(a)
        da = domain_admin(a)
        exclude = {x for x in (msp, da) if x is not None}
        lu = local_users(a, ws | srv, exclude)
        if any(assoc(a, uid, 'highPrivApps') for uid in lu):
            has_admin += 1
        else:
            all_std += 1

    n = len(instances)
    t = n // 5
    print(
        f'  all-standard    : {all_std}/{n} (need >={t}) -> {"PASS" if all_std >= t else "FAIL"}'
    )
    print(
        f'  has-local-admin : {has_admin}/{n} (need >={t}) -> {"PASS" if has_admin >= t else "FAIL"}'
    )
    print(f'  R7 overall: {"PASS" if all_std >= t and has_admin >= t else "FAIL"}\n')


def check_r8(instances: list) -> None:
    _header('R8: Server data + internet-facing variation')
    failures_a = []
    facing, internal = 0, 0
    for idx, a in enumerate(instances):
        srv = servers(a)
        if not any(assoc(a, s, 'containedData') for s in srv):
            failures_a.append(
                (idx, f'no server with containedData (servers: {len(srv)})')
            )
        if any(s in internet_facing_apps(a) for s in srv):
            facing += 1
        else:
            internal += 1

    _report('R8-A (server with data)', len(instances), failures_a, require_all=True)

    n = len(instances)
    t_low = n // 10
    t_high = n - t_low
    ok_int = t_low <= internal <= t_high
    ok_fac = t_low <= facing <= t_high
    print(
        f'  internal-only   : {internal}/{n} (need >={t_low}, <={t_high}) -> {"PASS" if ok_int else "FAIL"}'
    )
    print(
        f'  internet-facing : {facing}/{n} (need >={t_low}, <={t_high}) -> {"PASS" if ok_fac else "FAIL"}'
    )
    print(f'  R8-B overall: {"PASS" if ok_int and ok_fac else "FAIL"}\n')


def check_r9(instances: list) -> None:
    _header('R9: MSP admin credential storage variation')
    no_creds, dc_only, has_mgmt = 0, 0, 0
    for a in instances:
        msp = msp_admin(a)
        assert msp is not None
        if not assoc(a, msp, 'credentials'):
            no_creds += 1
            continue
        containers = {
            app
            for orig in assoc(a, msp, 'credentials')
            if orig in a
            for chash in assoc(a, orig, 'hashes')
            if chash in a
            for data in assoc(a, chash, 'containerData')
            if data in a
            for app in assoc(a, data, 'containingApp')
        }
        if not containers:
            no_creds += 1
        elif any(s in containers for s in servers(a)):
            has_mgmt += 1
        elif containers == {domain_controller(a)}:
            dc_only += 1
        else:
            raise RuntimeError('Unexpected state in check_r9')

    n = len(instances)
    t = n // 4
    print(f'  no-credentials : {no_creds}/{n}')
    print(f'  DC-only        : {dc_only}/{n}')
    print(
        f'  has-mgmt-host  : {has_mgmt}/{n} (need >={t}) -> {"PASS" if has_mgmt >= t else "FAIL"}'
    )
    both = dc_only > 0 and has_mgmt > 0
    print(f'  both configs present -> {"PASS" if both else "FAIL"}')
    print(f'  R9 overall: {"PASS" if has_mgmt >= t and both else "FAIL"}\n')


# Main


def main() -> None:
    ap = argparse.ArgumentParser(description='menuPass scenario 1 rubric checks')
    ap.add_argument('--regen', action='store_true', help='overwrite existing instances')
    ap.add_argument('-n', type=int, default=N_INSTANCES, help='number of instances')
    args = ap.parse_args()

    try:
        generate_instances(args.n, args.regen)
    except Exception as e:
        print(f'[ERROR] generation failed: {e}', file=sys.stderr)
        sys.exit(1)

    print(f'[load] loading {args.n} instances from {OUT_DIR}')
    instances = load_instances(args.n)
    if not instances:
        print('[ERROR] no instances loaded', file=sys.stderr)
        sys.exit(1)
    print(f'[load] loaded {len(instances)} instances\n')

    for check in [
        check_r1,
        check_r2,
        check_r3,
        check_r4,
        check_r5,
        check_r6,
        check_r7,
        check_r8,
        check_r9,
    ]:
        try:
            check(instances)
        except Exception as e:
            print(f'  [ERROR in {check.__name__}]: {e}')
            traceback.print_exc()
            print()


if __name__ == '__main__':
    main()
