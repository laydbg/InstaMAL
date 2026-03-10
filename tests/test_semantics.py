import os
import pytest
import tempfile
from pathlib import Path

from instamal.instantiator import ModelInstantiator


TRAININGLANG_PATH = (
    f"{Path(__file__).resolve().parent}/org.mal-lang.trainingLang-1.0.0.mar"
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


@pytest.fixture(scope="module")
def inheritancelang_path():
    with tempfile.NamedTemporaryFile(
        delete=False, mode="w", suffix=".mal", encoding="utf-8"
    ) as f:
        f.write(INHERITANCELANG_MAL)
        path = f.name
    yield path
    os.remove(path)


@pytest.fixture(scope="function")
def instantiate():
    def _instantiate(spec: str, lang_src: str, n: int = 1) -> None:
        tmp_spec_file_name: str = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, mode="w", encoding="utf-8"
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


def test_no_exception_on_valid_spec(instantiate):
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
    lang_src = TRAININGLANG_PATH

    instantiate(spec, lang_src, n=5)


def test_exception_on_variable_not_declared(instantiate):
    spec: str = """
let networks = Network(2);

connect {
    1.0: networks --> [toNetworks] netwrks; // <- line 5
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 5" in str(exc_info.value).lower()


def test_exception_on_non_existent_asset(instantiate):
    spec: str = """
let users = Useer(); // <- line 2
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 2" in str(exc_info.value).lower()


def test_exception_on_non_existent_association(instantiate):
    spec: str = """
let hosts = Host(10);
let users = User(TruncatedNormal(15, 4));

connect {
    0.5: users --> [hsts] hosts; // <- line 6
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 6" in str(exc_info.value).lower()


def test_exception_on_asset_as_variable_name(instantiate):
    spec: str = """
let Data = Network(2); // <- line 2
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 2" in str(exc_info.value).lower()


def test_exception_on_asset_as_subsystem_name(instantiate):
    spec: str = """
subsystem Host { // <- line 2
    let data = Data(Uniform(0, 4));
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 2" in str(exc_info.value).lower()


def test_exception_on_subsystem_as_variable_name(instantiate):
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
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 11" in str(exc_info.value).lower()


def test_exception_on_variable_name_as_subset_name(instantiate):
    spec: str = """
let networks = Network(4);

subsystem networks { // <- line 4
    let host = Host(1);
    let data = Data(4);
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 4" in str(exc_info.value).lower()


def test_exception_on_subsystem_already_defined(instantiate):
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

subsystem HostWithData { // <- line 6
    let data = Data(4);
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 6" in str(exc_info.value).lower()


def test_exception_on_recursive_subsystem(instantiate):
    spec: str = """
subsystem HostWithData {
    let hosts = HostWithData(2); // <- line 3
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 3" in str(exc_info.value).lower()


def test_no_exception_on_nested_subsystem_access(instantiate):
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
    lang_src = TRAININGLANG_PATH

    instantiate(spec, lang_src, n=3)


def test_exception_on_invalid_nested_member_inside_subsystem(instantiate):
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
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src)

    assert "line 11" in str(exc_info.value).lower()


def test_exception_on_invalid_nested_member_outside_subsystem(instantiate):
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

let hosts = HostWithData(2);

connect {
    1: hosts.invalid --> [networks] hosts.host; // <- line 9
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src)

    assert "line 9" in str(exc_info.value).lower()


def test_exception_on_member_access_of_non_subsystem(instantiate):
    spec: str = """
let users = User(2);

connect {
    1: users.host --> [networks] users; // <- line 5
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src)

    assert "line 5" in str(exc_info.value).lower()


def test_exception_on_deep_invalid_nested_access(instantiate):
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
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src)

    assert "line 13" in str(exc_info.value).lower()


def test_exception_on_undeclared_root_in_nested_access(instantiate):
    spec: str = """
subsystem HostWithData {
    let host = Host(1);
}

connect {
    1: unknown.host --> [data] unknown.host; // <- line 7
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src)

    assert "line 7" in str(exc_info.value).lower()


def test_no_exception_on_three_level_nested_access(instantiate):
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
    lang_src = TRAININGLANG_PATH

    instantiate(spec, lang_src)


def test_zero_asset_instantiation_allowed(instantiate):
    spec: str = """
let hosts = Host(0);
let users = User(0);

connect {
    1: hosts --> [users] users;
}
"""
    lang_src = TRAININGLANG_PATH

    instantiate(spec, lang_src, n=5)


def test_zero_subsystem_instantiation_allowed(instantiate):
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
    lang_src = TRAININGLANG_PATH

    instantiate(spec, lang_src, n=5)


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
    should raise an error."""
    spec = """
let children = Child(2);
let others = Other(3);

connect {
    1: children --> [nonexistent] others; // <- line 6
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, inheritancelang_path)

    assert "line 6" in str(exc_info.value).lower()


def test_exception_on_wrong_type_for_inherited_association(
    instantiate, inheritancelang_path
):
    """Using the correct fieldname but wrong asset type should still raise
    an error, even when the association is inherited."""
    spec = """
let children_a = Child(2);
let children_b = Child(2);

connect {
    1: children_a --> [others] children_b; // <- line 6
}
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, inheritancelang_path)

    assert "line 6" in str(exc_info.value).lower()
