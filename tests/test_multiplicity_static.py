import os
import pytest
import tempfile

from instamal.instantiator import ModelInstantiator


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


@pytest.fixture(scope="module")
def testlang_path():
    """Write TESTLANG_MAL to a temp .mal file and yield its path."""
    with tempfile.NamedTemporaryFile(
        delete=False, mode="w", suffix=".mal", encoding="utf-8"
    ) as f:
        f.write(TESTLANG_MAL)
        path = f.name
    yield path
    os.remove(path)


@pytest.fixture(scope="function")
def instantiate():
    def _instantiate(spec: str, lang_src: str, n: int = 1) -> None:
        tmp_spec_file_name = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, mode="w", encoding="utf-8"
            ) as tmp_spec_file:
                tmp_spec_file.write(spec)
                tmp_spec_file_name = tmp_spec_file.name
            with tempfile.TemporaryDirectory() as tmp_dir:
                instantiator = ModelInstantiator(
                    tmp_spec_file_name, lang_src, interactive=False
                )
                instantiator.instantiate(tmp_dir, n)
        finally:
            if tmp_spec_file_name is not None:
                os.remove(tmp_spec_file_name)

    return _instantiate


def test_mal_loads_and_unconnected_spec_passes(instantiate, testlang_path):
    """Smoke test: inline MAL loads correctly and a spec with no connect
    blocks raises no exception."""
    spec = """
let servers = Server(2);
let software = Software(2);
"""
    instantiate(spec, testlang_path)


def test_no_violation_at_exact_upper_bound(instantiate, testlang_path):
    """Connecting exactly as many assets as the upper bound allows passes."""
    spec = """
let servers = Server(1);
let software = Software(3);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_at_exact_lower_bound(instantiate, testlang_path):
    """Connecting exactly as many assets as the lower bound requires passes."""
    spec = """
let servers = Server(1);
let software = Software(1);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_strictly_within_bounds(instantiate, testlang_path):
    """Connecting a count strictly between lower and upper bound passes."""
    spec = """
let servers = Server(1);
let software = Software(2);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_unbounded_max(instantiate, testlang_path):
    """Connecting many assets to a field with no upper bound passes."""
    spec = """
let servers = Server(1);
let clients = Client(100);

connect {
    1: servers --> [connectedClients] clients;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_exact_multiplicity_one(instantiate, testlang_path):
    """Connecting exactly one asset to a field with multiplicity 1 passes."""
    spec = """
let servers = Server(1);
let databases = Database(5);

connect {
    1: databases --> [hostedOn] servers;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_weight_below_one_does_not_trigger_underconnection(
    instantiate, testlang_path
):
    """A rule with weight < 1.0 conservatively contributes 0 to the guaranteed
    minimum, so under-connection cannot be statically guaranteed — no
    violation should be raised even if the set is too small."""
    spec = """
let servers = Server(1);
let software = Software(1);

connect {
    0.5: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_multiple_rules_accumulate_within_upper_bound(
    instantiate, testlang_path
):
    """Multiple rules writing to the same field are accumulated correctly;
    total guaranteed minimum must not exceed the upper bound."""
    spec = """
let servers = Server(1);
let software_a = Software(1);
let software_b = Software(1);

connect {
    1: servers --> [installedSoftware] software_a;
    1: servers --> [installedSoftware] software_b;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_lower_bound_above_one_satisfied(instantiate, testlang_path):
    """Connecting at least as many assets as a lower bound greater than 1
    requires passes."""
    spec = """
let servers = Server(6);

connect {
    1: servers --> [monitors] servers;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_within_bounds_inside_subsystem(instantiate, testlang_path):
    """A connection inside a subsystem that satisfies the multiplicity passes."""
    spec = """
subsystem Unit {
    let a = Server(1);
    let b = Software(2);

    connect {
        1: a --> [installedSoftware] b;
    }
}

let units = Unit(4);
"""
    instantiate(spec, testlang_path)


def test_no_violation_within_bounds_nested_subsystem(instantiate, testlang_path):
    """Connections inside a doubly-nested subsystem that satisfy multiplicities
    pass."""
    spec = """
subsystem Inner {
    let a = Server(1);
    let b = Software(1);

    connect {
        1: a --> [installedSoftware] b;
    }
}

subsystem Outer {
    let inner = Inner(2);
}

let outer = Outer(3);
"""
    instantiate(spec, testlang_path)


def test_no_violation_exact_upper_bound_with_distribution(instantiate, testlang_path):
    """A distribution whose entire support fits within the multiplicity range
    passes."""
    spec = """
let servers = Server(1);
let software = Software(Uniform(1, 3));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, testlang_path)


def test_no_violation_distribution_with_uncertain_bounds(instantiate, testlang_path):
    """A distribution whose bounds straddle the multiplicity limits cannot be
    statically guaranteed to violate, so no error is raised by the static
    analyzer. Runtime violations from maltoolbox are acceptable here."""
    spec = """
let servers = Server(1);
let software = Software(Binomial(5, 0.5));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    try:
        instantiate(spec, testlang_path)
    except ValueError:
        pass  # Probabilistic runtime violation, not a static analyzer error


def test_no_violation_certain_count_at_upper_bound_with_distribution(
    instantiate, testlang_path
):
    """A distribution that always yields exactly the upper bound passes."""
    spec = """
let servers = Server(1);
let software = Software(Binomial(3, 1.0));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, testlang_path)


def test_violation_guaranteed_over_upper_bound(instantiate, testlang_path):
    """A set whose minimum count exceeds the field's upper bound with weight=1
    is a guaranteed violation."""
    spec = """
let servers = Server(1);
let software = Software(4);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_over_upper_bound_multiple_rules_accumulated(
    instantiate, testlang_path
):
    """Multiple rules whose accumulated guaranteed minimum exceeds the upper
    bound is a violation."""
    spec = """
let servers = Server(1);
let sw_a = Software(2);
let sw_b = Software(2);

connect {
    1: servers --> [installedSoftware] sw_a;
    1: servers --> [installedSoftware] sw_b;
}
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_over_multiplicity_one(instantiate, testlang_path):
    """Connecting more than one asset to a field with multiplicity 1 with
    weight=1 is a guaranteed violation."""
    spec = """
let servers = Server(2);
let databases = Database(1);

connect {
    1: databases --> [hostedOn] servers;
}
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_over_upper_bound_inside_subsystem(
    instantiate, testlang_path
):
    """A guaranteed over-connection inside a subsystem is caught."""
    spec = """
subsystem Unit {
    let a = Server(1);
    let b = Software(4);

    connect {
        1: a --> [installedSoftware] b;
    }
}

let units = Unit(2);
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_over_distribution_certain_above_upper_bound(
    instantiate, testlang_path
):
    """A distribution that always yields a count above the upper bound is a
    guaranteed violation."""
    spec = """
let servers = Server(1);
let software = Software(Uniform(4, 5));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_over_distribution_always_max(instantiate, testlang_path):
    """A distribution with p=1.0 that always yields its maximum, which exceeds
    the upper bound, is a guaranteed violation."""
    spec = """
let servers = Server(1);
let software = Software(Binomial(10, 1.0));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_under_lower_bound(instantiate, testlang_path):
    """A set whose maximum count falls below the field's lower bound with
    weight=1 is a guaranteed violation."""
    spec = """
let servers_a = Server(1);
let servers_b = Server(3);

connect {
    1: servers_a --> [monitors] servers_b;
}
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_under_lower_bound_zero_assets(instantiate, testlang_path):
    """Connecting zero assets to a field with a lower bound greater than zero
    with weight=1 is a guaranteed violation."""
    spec = """
let servers = Server(1);
let software = Software(0);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)


def test_violation_guaranteed_under_lower_bound_inside_subsystem(
    instantiate, testlang_path
):
    """A guaranteed under-connection inside a subsystem is caught."""
    spec = """
subsystem Unit {
    let a = Server(1);
    let b = Server(3);

    connect {
        1: a --> [monitors] b;
    }
}

let units = Unit(2);
"""
    with pytest.raises(Exception, match="(?i)multiplicity"):
        instantiate(spec, testlang_path)
