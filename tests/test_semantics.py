import os
import pytest
import tempfile
from pathlib import Path

from instamal import ModelInstantiator


TRAININGLANG_PATH = (
    f'{Path(__file__).resolve().parent}/org.mal-lang.trainingLang-1.0.0.mar'
)


INHERITANCELANG_MAL = """
#id: "org.mal-lang.inheritanceLang"
#version: "1.0.0"

category Test {

  asset Base {
  }

  asset Child extends Base {
  }

  asset Other {
  }

}

associations {
  Base [bases] * <-- BaseOtherRelation --> * [others] Other
}
"""


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope='module')
def inheritancelang_path():
    with tempfile.NamedTemporaryFile(
        delete=False, mode='w', suffix='.mal', encoding='utf-8'
    ) as f:
        f.write(INHERITANCELANG_MAL)
        path = f.name
    yield path
    os.remove(path)


@pytest.fixture(scope='function')
def instantiate():
    def _instantiate(spec: str, lang_src: str, n: int = 1) -> None:
        tmp_spec_file_name: str = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, mode='w', encoding='utf-8'
            ) as tmp_spec_file:
                tmp_spec_file.write(spec)
                tmp_spec_file_name = tmp_spec_file.name

            with tempfile.TemporaryDirectory() as tmp_dir:
                instantiator: ModelInstantiator = ModelInstantiator(
                    tmp_spec_file.name, lang_src
                )
                instantiator.instantiate(tmp_dir, n)
        finally:
            if tmp_spec_file_name is not None:
                os.remove(tmp_spec_file_name)

    return _instantiate


# ── Basic valid and invalid specs ─────────────────────────────────────────────


def test_no_exception_on_valid_spec(instantiate):
    """A well-formed spec with nested subsystems, distributions, and connect
    blocks should instantiate without error."""
    spec: str = """
subsystem HostWithData {
    let host = Host();
    let users = User(Uniform(1, 3));
    let data = Data();
    connect {
        1: host --> [data] data;
        1: host --> [users] users;
    }
}

subsystem NetworkWithHosts {
    let network = Network();
    let hosts = HostWithData(TruncatedNormal(8, 3));
    connect {
        1: network --> [hosts] hosts.host;
    }
}

let networks = NetworkWithHosts(1+Binomial(7, 0.03));

connect {
    1: networks.network --> [toNetworks] networks.network;
}
"""
    instantiate(spec, TRAININGLANG_PATH, n=5)


def test_exception_on_variable_not_declared(instantiate):
    """Referencing a variable that has not been declared should raise an
    error pointing to the offending line."""
    spec: str = """
let networks = Network(2);

connect {
    1.0: networks --> [toNetworks] netwrks; // <- line 5
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 5' in str(exc_info.value).lower()


def test_exception_on_non_existent_asset(instantiate):
    """Using a type name that does not exist in the MAL language should raise
    an error pointing to the offending line."""
    spec: str = """
let users = Useer(); // <- line 2
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_non_existent_association(instantiate):
    """Using a fieldname that does not exist in the MAL language should raise
    an error pointing to the offending line."""
    spec: str = """
let hosts = Host(10);
let users = User(TruncatedNormal(15, 4));

connect {
    0.5: users --> [hsts] hosts; // <- line 6
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 6' in str(exc_info.value).lower()


# ── Name conflict checks ──────────────────────────────────────────────────────


def test_exception_on_asset_as_variable_name(instantiate):
    """Using an asset type name as a let variable name should raise an
    error pointing to the offending line."""
    spec: str = """
let Data = Network(2); // <- line 2
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_asset_as_subsystem_name(instantiate):
    """Using an asset type name as a subsystem name should raise an error
    pointing to the offending line."""
    spec: str = """
subsystem Host { // <- line 2
    let data = Data(Uniform(0, 4));
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_subsystem_as_variable_name(instantiate):
    """Using a subsystem name as a let variable name should raise an error
    pointing to the offending line."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
    let data = Data(Uniform(0, 4));

    connect {
        1: host --> [data] data;
    }
}

let HostWithData = Host(2); // <- line 11
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 11' in str(exc_info.value).lower()


def test_exception_on_variable_name_as_subset_name(instantiate):
    """Using an already-declared let variable name as a subsystem name should
    raise an error pointing to the offending line."""
    spec: str = """
let networks = Network(4);

subsystem networks { // <- line 4
    let host = Host(1);
    let data = Data(4);
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 4' in str(exc_info.value).lower()


def test_exception_on_subsystem_already_defined(instantiate):
    """Defining a subsystem with a name that has already been used for another
    subsystem should raise an error pointing to the offending line."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

subsystem HostWithData { // <- line 6
    let data = Data(4);
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 6' in str(exc_info.value).lower()


# ── Subsystem instantiation ───────────────────────────────────────────────────


def test_exception_on_recursive_subsystem(instantiate):
    """A subsystem that instantiates itself should raise an error pointing
    to the offending line."""
    spec: str = """
subsystem HostWithData {
    let hosts = HostWithData(2); // <- line 3
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH, n=5)

    assert 'line 3' in str(exc_info.value).lower()


def test_no_exception_on_nested_subsystem_access(instantiate):
    """Accessing members of a nested subsystem via dot notation in a connect
    block should be valid."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
    let data = Data(2);

    connect {
        1: host --> [data] data;
    }
}

subsystem NetworkWithHosts {
    let network = Network(1);
    let hosts = HostWithData(3);

    connect {
        1: network --> [hosts] hosts.host;
    }
}

let networks = NetworkWithHosts(2);

connect {
    1: networks.network --> [toNetworks] networks.network;
    1: networks.hosts.host --> [networks] networks.network;
}
"""
    instantiate(spec, TRAININGLANG_PATH, n=3)


def test_exception_on_invalid_nested_member_inside_subsystem(instantiate):
    """Accessing a member that does not exist on a nested subsystem inside
    another subsystem should raise an error pointing to the offending line."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

subsystem NetworkWithHosts {
    let network = Network(1);
    let hosts = HostWithData(3);

    connect {
        1: network --> [hosts] hosts.invalid; // <- line 11
    }
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 11' in str(exc_info.value).lower()


def test_exception_on_invalid_nested_member_outside_subsystem(instantiate):
    """Accessing a member that does not exist on a subsystem from outside
    it should raise an error pointing to the offending line."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

let hosts = HostWithData(2);

connect {
    1: hosts.invalid --> [networks] hosts.host; // <- line 9
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 9' in str(exc_info.value).lower()


def test_exception_on_member_access_of_non_subsystem(instantiate):
    """Using dot notation to access a member of a plain asset variable (not
    a subsystem) should raise an error pointing to the offending line."""
    spec: str = """
let users = User(2);

connect {
    1: users.host --> [networks] users; // <- line 5
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 5' in str(exc_info.value).lower()


def test_exception_on_deep_invalid_nested_access(instantiate):
    """Accessing an invalid member at the end of a deep dot-notation chain
    should raise an error pointing to the offending line."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

subsystem NetworkWithHosts {
    let hosts = HostWithData(2);
}

let networks = NetworkWithHosts(1);

connect {
    1: networks.hosts.host.invalid --> [toNetworks] networks.hosts.host; // <- line 13
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 13' in str(exc_info.value).lower()


def test_exception_on_undeclared_root_in_nested_access(instantiate):
    """Using an undeclared variable as the root of a dot-notation access
    should raise an error pointing to the offending line."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

connect {
    1: unknown.host --> [data] unknown.host; // <- line 7
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 7' in str(exc_info.value).lower()


def test_no_exception_on_three_level_nested_access(instantiate):
    """Dot-notation access through three levels of nested subsystems should
    be valid."""
    spec: str = """
subsystem Inner {
    let host = Host(1);
}

subsystem Middle {
    let inner = Inner(2);
}

subsystem Outer {
    let middle = Middle(3);
}

let outer = Outer(1);

connect {
    1: outer.middle.inner.host --> [data] Data();
}
"""
    instantiate(spec, TRAININGLANG_PATH)


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_zero_asset_instantiation_allowed(instantiate):
    """Instantiating zero assets should be valid and produce an empty set
    without error."""
    spec: str = """
let hosts = Host(0);
let users = User(0);

connect {
    1: hosts --> [users] users;
}
"""
    instantiate(spec, TRAININGLANG_PATH, n=5)


def test_zero_subsystem_instantiation_allowed(instantiate):
    """Instantiating a subsystem zero times should be valid and produce no
    assets without error."""
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
    let data = Data(1);

    connect {
        1: host --> [data] data;
    }
}

let hosts = HostWithData(0);

connect {
    1: hosts.host --> [data] hosts.data;
}
"""
    instantiate(spec, TRAININGLANG_PATH, n=5)


# ── Inheritance ───────────────────────────────────────────────────────────────


def test_no_exception_on_association_via_inheritance(instantiate, inheritancelang_path):
    """A child asset should be usable in an association defined on its parent."""
    spec = """
let children = Child(2);
let others = Other(3);

connect {
    1: children --> [others] others;
}
"""
    instantiate(spec, inheritancelang_path)


def test_no_exception_on_reverse_association_via_inheritance(
    instantiate, inheritancelang_path
):
    """The reverse direction of an inherited association should also be valid."""
    spec = """
let children = Child(2);
let others = Other(3);

connect {
    1: others --> [bases] children;
}
"""
    instantiate(spec, inheritancelang_path)


def test_exception_on_association_not_inherited(instantiate, inheritancelang_path):
    """An association that does not exist on the asset or any of its parents
    should raise an error pointing to the offending line."""
    spec = """
let children = Child(2);
let others = Other(3);

connect {
    1: children --> [nonexistent] others; // <- line 6
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, inheritancelang_path)

    assert 'line 6' in str(exc_info.value).lower()


def test_exception_on_wrong_type_for_inherited_association(
    instantiate, inheritancelang_path
):
    """Using the correct fieldname but the wrong asset type should raise an
    error even when the association is inherited, pointing to the offending
    line."""
    spec = """
let children_a = Child(2);
let children_b = Child(2);

connect {
    1: children_a --> [others] children_b; // <- line 6
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, inheritancelang_path)

    assert 'line 6' in str(exc_info.value).lower()


# ── Params ────────────────────────────────────────────────────────────────────


def test_no_exception_on_valid_param_constant(instantiate):
    """A param with = should be accepted and usable in a let expression."""
    spec = """
param numHosts = 4;

let hosts = Host(numHosts);
"""
    instantiate(spec, TRAININGLANG_PATH)


def test_no_exception_on_valid_param_distribution(instantiate):
    """A param with ~ should be accepted and usable in a let expression."""
    spec = """
param numHosts ~ Uniform(4, 8);

let hosts = Host(numHosts);
"""
    instantiate(spec, TRAININGLANG_PATH)


def test_no_exception_on_param_referencing_earlier_param(instantiate):
    """A param may reference a previously declared param."""
    spec = """
param base = 4;
param numHosts = base * 2;

let hosts = Host(numHosts);
"""
    instantiate(spec, TRAININGLANG_PATH)


def test_no_exception_on_param_used_in_subsystem(instantiate):
    """A global param should be usable inside a subsystem expression."""
    spec = """
param numHosts = 3;

subsystem NetworkUnit {
    let network = Network(1);
    let hosts = Host(numHosts);
}

let units = NetworkUnit(2);
"""
    instantiate(spec, TRAININGLANG_PATH)


def test_no_exception_on_multiple_params(instantiate):
    """Multiple params should all be usable without conflict."""
    spec = """
param n = 2;
param m = 3;
param total = n * m;

let hosts = Host(total);
"""
    instantiate(spec, TRAININGLANG_PATH)


def test_exception_on_param_name_conflicts_with_asset_name(instantiate):
    """A param name that matches an asset name should raise an error pointing
    to the offending line."""
    spec = """
param Host = 4; // <- line 2
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_param_name_conflicts_with_let_variable(instantiate):
    """A param declared after a let variable with the same name should raise
    an error pointing to the offending line."""
    spec = """
let hosts = Host(2);

param hosts = 4; // <- line 4
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 4' in str(exc_info.value).lower()


def test_exception_on_let_variable_conflicts_with_param(instantiate):
    """A let variable declared after a param with the same name should raise
    an error pointing to the offending line."""
    spec = """
param hosts = 4;

let hosts = Host(2); // <- line 4
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 4' in str(exc_info.value).lower()


def test_exception_on_param_name_conflicts_with_subsystem_name(instantiate):
    """A param declared after a subsystem with the same name should raise an
    error pointing to the offending line."""
    spec = """
subsystem NetworkUnit {
    let network = Network(1);
}

param NetworkUnit = 4; // <- line 6
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 6' in str(exc_info.value).lower()


def test_exception_on_subsystem_name_conflicts_with_param(instantiate):
    """A subsystem declared after a param with the same name should raise an
    error pointing to the offending line."""
    spec = """
param NetworkUnit = 4;

subsystem NetworkUnit { // <- line 4
    let network = Network(1);
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 4' in str(exc_info.value).lower()


def test_exception_on_duplicate_param_name(instantiate):
    """Declaring two params with the same name should raise an error pointing
    to the offending line."""
    spec = """
param n = 4;

param n = 8; // <- line 4
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 4' in str(exc_info.value).lower()


def test_exception_on_param_self_reference(instantiate):
    """A param that references itself in its own expression should raise an
    error pointing to the offending line."""
    spec = """
param n = n * 2; // <- line 2
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_param_forward_reference(instantiate):
    """A param that references another param not yet declared should raise an
    error pointing to the offending line."""
    spec = """
param n = m * 2; // <- line 2

param m = 4;
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, TRAININGLANG_PATH)

    assert 'line 2' in str(exc_info.value).lower()
