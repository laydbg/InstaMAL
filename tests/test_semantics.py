import os
import pytest
import tempfile
from pathlib import Path

from instamal.instantiator import ModelInstantiator


TRAININGLANG_PATH = (
    f"{Path(__file__).resolve().parent}/org.mal-lang.trainingLang-1.0.0.mar"
)


@pytest.fixture(scope="function")
def instantiate():
    def _instantiate(spec: str, lang_src: str, n: int = 1) -> None:
        tmp_spec_file_name: str = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as tmp_spec_file:
                tmp_spec_file.write(spec)
                tmp_spec_file_name = tmp_spec_file.name

            with tempfile.TemporaryDirectory() as tmp_dir:
                instantiator: ModelInstantiator = ModelInstantiator(tmp_spec_file.name, lang_src)
                instantiator.instantiate(tmp_dir, n)
        finally:
            if tmp_spec_file_name is not None:
                os.remove(tmp_spec_file_name)
    return _instantiate


def test_no_exception_on_valid_spec(instantiate):
    spec: str = \
"""
subsystem HostWithData {
    let host = Host(1);
    let data = Data(Uniform(0, 4));

    connect {
        1: host --> [data] data;
    }
}

let networks = Network(2);
let hosts = HostWithData(10);
let users = User(TruncatedNormal(15, 4));

connect {
    1.0: networks --> [toNetworks] networks;
    0.5: hosts.host --> [networks] networks;
    0.5: users --> [hosts] hosts.host;
}
"""
    lang_src = TRAININGLANG_PATH

    instantiate(spec, lang_src, n=5)


def test_exception_on_variable_not_declared(instantiate):
    spec: str = \
"""
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
    spec: str = \
"""
let users = Useer(); // <- line 2
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 2" in str(exc_info.value).lower()


def test_exception_on_non_existent_association(instantiate):
    spec: str = \
"""
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
    spec: str = \
"""
let Data = Network(2); // <- line 2
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 2" in str(exc_info.value).lower()


def test_exception_on_asset_as_subsystem_name(instantiate):
    spec: str = \
"""
subsystem Host { // <- line 2
    let data = Data(Uniform(0, 4));
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 2" in str(exc_info.value).lower()


def test_exception_on_subsystem_as_variable_name(instantiate):
    spec: str = \
"""
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
    spec: str = \
"""
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
    spec: str = \
"""
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
    spec: str = \
"""
subsystem HostWithData {
    let hosts = HostWithData(2); // <- line 3
}
"""
    lang_src = TRAININGLANG_PATH

    with pytest.raises(Exception) as exc_info:
        instantiate(spec, lang_src, n=5)

    assert "line 3" in str(exc_info.value).lower()
