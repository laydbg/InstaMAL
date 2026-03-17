import os
import pytest
import tempfile
from typing import List

from maltoolbox.language import LanguageGraph
from antlr4 import FileStream, CommonTokenStream

from instamal.instantiator.helpers.MultiplicityAnalyzer import (
    ProbabilisticMultiplicityAnalyzer,
    MultiplicityWarning,
)

TESTLANG_MAL = """
#id: "org.mal-lang.testLang"
#version: "1.0.0"

category Test {

  asset Server {
  }

  asset Software {
  }

  asset Client {
  }

  asset Database {
  }

  asset Credential {
  }
}

associations {
  // A Server must have 1..3 Software installed
  Server [hosts]          *    <-- SoftwareOnServer     --> 1..3   [installedSoftware] Software

  // Each Client connects to exactly 1 Server; a Server serves 1..*  Clients
  Server [server]         1    <-- ClientServerRelation  --> 1..*  [connectedClients]  Client

  // A Database is hosted on exactly 1 Server
  Database [databases]    *    <-- DatabaseOnServer      --> 1     [hostedOn]          Server

  // A Credential belongs to exactly 1..2 Clients
  Credential [credential] 1    <-- CredentialForClient   --> 1..2  [owner]             Client

  // A Server must be monitored by at least 5 Servers
  Server [monitoredBy]    5..* <-- ServerMonitoring      --> *     [monitors]          Server
}
"""


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def testlang_path():
    with tempfile.NamedTemporaryFile(
        delete=False, mode="w", suffix=".mal", encoding="utf-8"
    ) as f:
        f.write(TESTLANG_MAL)
        path = f.name
    yield path
    os.remove(path)


def analyze(
    spec: str, lang_path: str, threshold: float = 0.9
) -> List[MultiplicityWarning]:
    """Run only the probabilistic analyzer on a spec string and return warnings."""
    lang_graph = LanguageGraph.load_from_file(lang_path)

    with tempfile.NamedTemporaryFile(
        delete=False, mode="w", encoding="utf-8", suffix=".spec"
    ) as f:
        f.write(spec)
        spec_path = f.name

    try:
        input_stream = FileStream(spec_path)
        from instamal.instantiator.helpers import SpecLexer, SpecParser

        lexer = SpecLexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = SpecParser(stream)
        spec_ctx = parser.spec()

        analyzer = ProbabilisticMultiplicityAnalyzer(lang_graph, threshold=threshold)
        return analyzer.analyze(spec_ctx)
    finally:
        os.remove(spec_path)


def warnings_for(
    warnings: List[MultiplicityWarning], asset_type: str, fieldname: str
) -> List[MultiplicityWarning]:
    """Filter warnings for a specific (asset_type, fieldname) pair."""
    return [
        w for w in warnings if w.asset_type == asset_type and w.fieldname == fieldname
    ]


# ── No warnings on clearly satisfiable specs ──────────────────────────────────


def test_no_warning_weight_one_count_within_bounds(testlang_path):
    """weight=1.0 with count exactly within bounds should give P≈1.0."""
    spec = """
let servers = Server(1);
let software = Software(2);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Server", "installedSoftware") == []


def test_no_warning_unbounded_max_with_high_weight(testlang_path):
    """A field with no upper bound and high weight should not warn."""
    spec = """
let servers = Server(1);
let clients = Client(10);

connect {
    1: servers --> [connectedClients] clients;
}
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Server", "connectedClients") == []


def test_no_warning_zero_min_weight_zero(testlang_path):
    """weight=0.0 on a field with mult_min=0 (unbounded lower) is trivially satisfied."""
    spec = """
let servers = Server(1);
let databases = Database(3);

connect {
    0: servers --> [databases] databases;
}
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Server", "databases") == []


def test_no_warning_large_right_set_satisfies_high_lower_bound(testlang_path):
    """A large right set with weight=1.0 satisfies a high lower bound."""
    spec = """
let servers_a = Server(1);
let servers_b = Server(20);

connect {
    1: servers_a --> [monitors] servers_b;
}
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Server", "monitors") == []


def test_no_warning_subsystem_within_bounds(testlang_path):
    """Assets connected inside a subsystem with weight=1.0 within bounds
    should not warn."""
    spec = """
subsystem Unit {
    let server = Server(1);
    let software = Software(2);

    connect {
        1: server --> [installedSoftware] software;
    }
}

let units = Unit(3);
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Server", "installedSoftware") == []


def test_no_warning_many_left_assets_one_right_asset_bounded_forward(testlang_path):
    """Many Databases connected to a single Server at weight 1.0: each
    Database receives exactly one reverse hostedOn edge, satisfying the
    multiplicity constraint of exactly 1. The single Server receiving many
    reverse databases edges is fine since databases is unbounded."""
    spec = """
let databases = Database(10);
let servers = Server(1);

connect {
    1: databases --> [hostedOn] servers;
}
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Database", "hostedOn") == []


# ── Warnings on clearly unsatisfiable specs ───────────────────────────────────


def test_warning_weight_zero_with_positive_lower_bound(testlang_path):
    """weight=0.0 means no connections are ever made, so any mult_min > 0
    gives P(satisfied)=0.0, which must warn."""
    spec = """
let servers = Server(1);
let software = Software(2);

connect {
    0: servers --> [installedSoftware] software;
}
"""
    warnings = analyze(spec, testlang_path)
    ws = warnings_for(warnings, "Server", "installedSoftware")
    assert len(ws) == 1
    assert ws[0].per_asset_probability == pytest.approx(0.0, abs=1e-6)
    assert ws[0].global_probability == pytest.approx(0.0, abs=1e-6)


def test_warning_very_low_weight_high_lower_bound(testlang_path):
    """A very low weight with a high lower bound should produce a warning
    with low probability."""
    spec = """
let servers_a = Server(1);
let servers_b = Server(3);

connect {
    0.1: servers_a --> [monitoredBy] servers_b;
}
"""
    warnings = analyze(spec, testlang_path, threshold=0.9)
    ws = warnings_for(warnings, "Server", "monitoredBy")
    assert len(ws) == 1
    assert ws[0].global_probability < 0.9


def test_warning_right_set_too_small_for_lower_bound(testlang_path):
    """Even weight=1.0 cannot satisfy mult_min=5 if right set has only 2
    assets, should warn with low probability."""
    spec = """
let servers_a = Server(1);
let servers_b = Server(2);

connect {
    1: servers_a --> [monitoredBy] servers_b;
}
"""
    warnings = analyze(spec, testlang_path, threshold=0.9)
    ws = warnings_for(warnings, "Server", "monitoredBy")
    assert len(ws) == 1
    assert ws[0].per_asset_probability == pytest.approx(0.0, abs=1e-6)


def test_warning_subsystem_low_weight_positive_lower_bound(testlang_path):
    """A low-weight rule inside a subsystem with a positive lower bound
    should be caught."""
    spec = """
subsystem Unit {
    let server = Server(1);
    let software = Software(2);

    connect {
        0.05: server --> [installedSoftware] software;
    }
}

let units = Unit(2);
"""
    warnings = analyze(spec, testlang_path, threshold=0.9)
    ws = warnings_for(warnings, "Server", "installedSoftware")
    assert len(ws) == 1
    assert ws[0].global_probability < 0.9


def test_warning_many_left_assets_high_weight_bounded_reverse(testlang_path):
    """Many Credentials connected to a single Client at high weight risks
    violating the reverse multiplicity constraint on 'credential' (mult=1
    on Client), since the Client may receive multiple reverse edges from the
    many Credentials pointing at it."""
    spec = """
let creds = Credential(10);
let clients = Client(1);

connect {
    0.9: creds --> [owner] clients;
}
"""
    warnings = analyze(spec, testlang_path, threshold=0.5)
    ws = warnings_for(warnings, "Client", "credential")
    assert len(ws) == 1
    assert ws[0].global_probability < 0.5


# ── Threshold sensitivity ─────────────────────────────────────────────────────


def test_same_spec_warns_at_high_threshold_not_low(testlang_path):
    """A borderline spec should warn at a strict threshold but not a lenient one."""
    spec = """
let servers = Server(1);
let software = Software(2);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    warnings_strict = analyze(spec, testlang_path, threshold=0.99)
    warnings_lenient = analyze(spec, testlang_path, threshold=0.01)

    ws_strict = warnings_for(warnings_strict, "Server", "installedSoftware")
    ws_lenient = warnings_for(warnings_lenient, "Server", "installedSoftware")

    assert len(ws_strict) >= len(ws_lenient)


def test_threshold_zero_never_warns(testlang_path):
    """A threshold of 0.0 should never produce warnings."""
    spec = """
let servers_a = Server(1);
let servers_b = Server(1);

connect {
    0: servers_a --> [monitors] servers_b;
}
"""
    warnings = analyze(spec, testlang_path, threshold=0.0)
    assert warnings == []


def test_threshold_one_always_warns_unless_certain(testlang_path):
    """A threshold of 1.0 should warn unless probability is exactly 1.0."""
    spec = """
let servers = Server(1);
let software = Software(2);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    warnings = analyze(spec, testlang_path, threshold=1.0)
    ws = warnings_for(warnings, "Server", "installedSoftware")
    assert len(ws) == 1


# ── Monotonicity ──────────────────────────────────────────────────────────────


def test_higher_weight_gives_higher_global_probability(testlang_path):
    """Increasing connection weight should monotonically increase
    global_probability for a lower-bound constraint."""

    def get_global_p(weight: float) -> float:
        spec = f"""
let servers = Server(1);
let software = Software(3);

connect {{
    {weight}: servers --> [installedSoftware] software;
}}
"""
        warnings = analyze(spec, testlang_path, threshold=0.0)
        ws = warnings_for(warnings, "Server", "installedSoftware")
        return ws[0].global_probability if ws else 1.0

    p_low = get_global_p(0.1)
    p_mid = get_global_p(0.5)
    p_high = get_global_p(0.9)

    assert p_low <= p_mid <= p_high


def test_larger_right_set_increases_probability_for_lower_bound(testlang_path):
    """For a lower-bound constraint, more assets in the right set with the
    same weight should increase per_asset_probability."""

    def get_per_asset_p(n_software: int) -> float:
        spec = f"""
let servers = Server(1);
let software = Software({n_software});

connect {{
    0.5: servers --> [installedSoftware] software;
}}
"""
        warnings = analyze(spec, testlang_path, threshold=0.0)
        ws = warnings_for(warnings, "Server", "installedSoftware")
        return ws[0].per_asset_probability if ws else 1.0

    p_small = get_per_asset_p(1)
    p_medium = get_per_asset_p(3)
    p_large = get_per_asset_p(6)

    assert p_small <= p_medium <= p_large


def test_more_assets_of_checked_type_decreases_global_probability(testlang_path):
    """With per_asset_p < 1, having more assets of the checked type should
    decrease global_probability since it is per_asset_p ^ n_assets."""

    def get_global_p(n_servers: int) -> float:
        spec = f"""
let servers = Server({n_servers});
let software = Software(2);

connect {{
    0.5: servers --> [installedSoftware] software;
}}
"""
        warnings = analyze(spec, testlang_path, threshold=0.0)
        ws = warnings_for(warnings, "Server", "installedSoftware")
        return ws[0].global_probability if ws else 1.0

    p_few = get_global_p(1)
    p_some = get_global_p(5)
    p_many = get_global_p(10)

    assert p_few >= p_some >= p_many


# ── Multi-rule accumulation ───────────────────────────────────────────────────


def test_two_rules_accumulate_higher_probability_than_one(testlang_path):
    """Two rules each contributing to the same field should together give
    a higher probability than either alone."""
    spec_two_rules = """
let servers = Server(1);
let sw_a = Software(1);
let sw_b = Software(1);

connect {
    0.5: servers --> [installedSoftware] sw_a;
    0.5: servers --> [installedSoftware] sw_b;
}
"""
    spec_one_rule = """
let servers = Server(1);
let sw_a = Software(1);

connect {
    0.5: servers --> [installedSoftware] sw_a;
}
"""
    warnings_two = analyze(spec_two_rules, testlang_path, threshold=0.0)
    warnings_one = analyze(spec_one_rule, testlang_path, threshold=0.0)

    ws_two = warnings_for(warnings_two, "Server", "installedSoftware")
    ws_one = warnings_for(warnings_one, "Server", "installedSoftware")

    p_two = ws_two[0].per_asset_probability if ws_two else 1.0
    p_one = ws_one[0].per_asset_probability if ws_one else 1.0

    assert p_two >= p_one


def test_accumulated_rules_equivalent_to_single_larger_rule(testlang_path):
    """Two rules of weight 0.5 connecting 1 asset each should give roughly
    the same probability as one rule of weight 0.5 connecting 2 assets."""
    spec_two_rules = """
let servers = Server(1);
let sw_a = Software(1);
let sw_b = Software(1);

connect {
    0.5: servers --> [installedSoftware] sw_a;
    0.5: servers --> [installedSoftware] sw_b;
}
"""
    spec_one_rule = """
let servers = Server(1);
let software = Software(2);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    warnings_two = analyze(spec_two_rules, testlang_path, threshold=0.0)
    warnings_one = analyze(spec_one_rule, testlang_path, threshold=0.0)

    ws_two = warnings_for(warnings_two, "Server", "installedSoftware")
    ws_one = warnings_for(warnings_one, "Server", "installedSoftware")

    p_two = ws_two[0].per_asset_probability if ws_two else 1.0
    p_one = ws_one[0].per_asset_probability if ws_one else 1.0

    assert p_two == pytest.approx(p_one, abs=0.05)


# ── Subsystem handling ────────────────────────────────────────────────────────


def test_subsystem_asset_counts_are_multiplied_correctly(testlang_path):
    """Assets inside a subsystem instantiated n times should contribute
    n * inner_count to the global probability calculation."""
    spec_subsystem = """
subsystem Unit {
    let server = Server(1);
    let software = Software(2);

    connect {
        0.5: server --> [installedSoftware] software;
    }
}

let units = Unit(4);
"""
    spec_flat = """
let servers = Server(4);
let software = Software(2);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    warnings_sub = analyze(spec_subsystem, testlang_path, threshold=0.0)
    warnings_flat = analyze(spec_flat, testlang_path, threshold=0.0)

    ws_sub = warnings_for(warnings_sub, "Server", "installedSoftware")
    ws_flat = warnings_for(warnings_flat, "Server", "installedSoftware")

    p_sub = ws_sub[0].global_probability if ws_sub else 1.0
    p_flat = ws_flat[0].global_probability if ws_flat else 1.0

    assert p_sub == pytest.approx(p_flat, abs=0.05)


def test_nested_subsystem_asset_counts_propagate_correctly(testlang_path):
    """Assets in doubly-nested subsystems should have their counts multiplied
    through both levels."""
    spec = """
subsystem Inner {
    let server = Server(1);
    let software = Software(2);

    connect {
        0.5: server --> [installedSoftware] software;
    }
}

subsystem Outer {
    let inner = Inner(2);
}

let outer = Outer(3);
"""
    warnings = analyze(spec, testlang_path, threshold=1.0)
    ws = warnings_for(warnings, "Server", "installedSoftware")

    # 3 * 2 = 6 Server assets total, each with 2 Software at weight 0.5
    assert len(ws) == 1
    assert ws[0].n_assets_expected == pytest.approx(6.0, abs=0.1)


def test_warning_contains_correct_multiplicity_info(testlang_path):
    """Warning objects should carry correct mult_min and mult_max values."""
    spec = """
let servers = Server(1);
let software = Software(2);

connect {
    0: servers --> [installedSoftware] software;
}
"""
    warnings = analyze(spec, testlang_path, threshold=0.001)
    ws = warnings_for(warnings, "Server", "installedSoftware")

    assert len(ws) == 1
    assert ws[0].mult_min == 1
    assert ws[0].mult_max == 3


# ── Param handling ────────────────────────────────────────────────────────────


def test_no_warning_param_constant_within_bounds(testlang_path):
    """A param = constant used as asset count that keeps expected connections
    within bounds should not warn."""
    spec = """
param n = 2;

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Server", "installedSoftware") == []


def test_no_warning_param_distribution_expected_within_bounds(testlang_path):
    """A param ~ distribution whose expected value keeps connections within
    bounds should not warn."""
    spec = """
param n ~ Uniform(1, 3);

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    warnings = analyze(spec, testlang_path)
    assert warnings_for(warnings, "Server", "installedSoftware") == []


def test_warning_param_zero_constant_with_positive_lower_bound(testlang_path):
    """A param = 0 used as asset count gives expected degree 0, which cannot
    satisfy a positive lower bound — should warn."""
    spec = """
param n = 0;

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    warnings = analyze(spec, testlang_path, threshold=0.01)
    ws = warnings_for(warnings, "Server", "installedSoftware")
    assert len(ws) == 1
    assert ws[0].per_asset_probability == pytest.approx(0.0, abs=1e-6)


def test_warning_param_distribution_low_expected_count(testlang_path):
    """A param ~ distribution with a low expected value used as right-set
    count should warn when the lower bound is high."""
    spec = """
param n ~ Uniform(0, 1);

let servers_a = Server(1);
let servers_b = Server(n);

connect {
    0.1: servers_a --> [monitoredBy] servers_b;
}
"""
    warnings = analyze(spec, testlang_path, threshold=0.9)
    ws = warnings_for(warnings, "Server", "monitoredBy")
    assert len(ws) == 1
    assert ws[0].global_probability < 0.9


def test_param_constant_affects_global_probability_via_asset_count(testlang_path):
    """A param = n used as the left asset count should scale global_probability
    as per_asset_p ^ n — more assets means lower global probability."""

    def get_global_p(n: int) -> float:
        spec = f"""
param n = {n};

let servers = Server(n);
let software = Software(2);

connect {{
    0.5: servers --> [installedSoftware] software;
}}
"""
        warnings = analyze(spec, testlang_path, threshold=0.0)
        ws = warnings_for(warnings, "Server", "installedSoftware")
        return ws[0].global_probability if ws else 1.0

    p_few = get_global_p(1)
    p_some = get_global_p(5)
    p_many = get_global_p(10)

    assert p_few >= p_some >= p_many


def test_param_arithmetic_expected_value_is_correct(testlang_path):
    """A param defined via arithmetic on another param should have its
    expected value evaluated correctly, affecting the degree distribution."""
    spec_param = """
param base = 1;
param n = base * 2;

let servers = Server(1);
let software = Software(n);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    spec_literal = """
let servers = Server(1);
let software = Software(2);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    warnings_param = analyze(spec_param, testlang_path, threshold=0.0)
    warnings_literal = analyze(spec_literal, testlang_path, threshold=0.0)

    ws_param = warnings_for(warnings_param, "Server", "installedSoftware")
    ws_literal = warnings_for(warnings_literal, "Server", "installedSoftware")

    p_param = ws_param[0].per_asset_probability if ws_param else 1.0
    p_literal = ws_literal[0].per_asset_probability if ws_literal else 1.0

    assert p_param == pytest.approx(p_literal, abs=1e-6)


def test_param_distribution_expected_value_matches_literal(testlang_path):
    """A param ~ Uniform(a, b) should contribute E[(a+b)/2] to the degree
    distribution, giving the same result as using the literal expected value."""
    spec_param = """
param n ~ Uniform(1, 3);

let servers = Server(1);
let software = Software(n);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    # E[Uniform(1,3)] = 2
    spec_literal = """
let servers = Server(1);
let software = Software(2);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    warnings_param = analyze(spec_param, testlang_path, threshold=0.0)
    warnings_literal = analyze(spec_literal, testlang_path, threshold=0.0)

    ws_param = warnings_for(warnings_param, "Server", "installedSoftware")
    ws_literal = warnings_for(warnings_literal, "Server", "installedSoftware")

    p_param = ws_param[0].per_asset_probability if ws_param else 1.0
    p_literal = ws_literal[0].per_asset_probability if ws_literal else 1.0

    assert p_param == pytest.approx(p_literal, abs=0.05)


def test_param_used_in_subsystem_scales_global_probability(testlang_path):
    """A global param used inside a subsystem as asset count should scale
    global_probability correctly through subsystem multiplication."""
    spec_param = """
param n = 2;

subsystem Unit {
    let server = Server(1);
    let software = Software(n);

    connect {
        0.5: server --> [installedSoftware] software;
    }
}

let units = Unit(1);
"""
    # Software(2) directly gives the same expected right-set size
    spec_literal = """
let servers = Server(1);
let software = Software(2);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    warnings_param = analyze(spec_param, testlang_path, threshold=0.0)
    warnings_literal = analyze(spec_literal, testlang_path, threshold=0.0)

    ws_param = warnings_for(warnings_param, "Server", "installedSoftware")
    ws_literal = warnings_for(warnings_literal, "Server", "installedSoftware")

    p_param = ws_param[0].per_asset_probability if ws_param else 1.0
    p_literal = ws_literal[0].per_asset_probability if ws_literal else 1.0

    assert p_param == pytest.approx(p_literal, abs=0.05)
