"""
Static multiplicity analysis tests.

These tests exercise the StaticMultiplicityAnalyzer via ModelInstantiator and
verify that specs with guaranteed multiplicity violations are rejected before
instantiation, while specs that are within bounds or only probabilistically
unsafe are accepted.
"""
import pytest


# Boundary and within-bounds cases


def test_no_violation_at_exact_upper_bound(instantiate, multiplicityLang_path):
    """Connecting exactly as many assets as the upper bound allows passes."""
    spec = """
let servers = Server(1);
let software = Software(3);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_no_violation_at_exact_lower_bound(instantiate, multiplicityLang_path):
    """Connecting exactly as many assets as the lower bound requires passes."""
    spec = """
let servers = Server(1);
let software = Software(1);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_no_violation_strictly_within_bounds(instantiate, multiplicityLang_path):
    """Connecting a count strictly between lower and upper bound passes."""
    spec = """
let servers = Server(1);
let software = Software(2);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_no_violation_unbounded_max(instantiate, multiplicityLang_path):
    """Connecting many assets to a field with no upper bound passes."""
    spec = """
let servers = Server(1);
let clients = Client(100);

connect {
    1: servers --> [connectedClients] clients;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_no_violation_exact_multiplicity_one(instantiate, multiplicityLang_path):
    """Connecting exactly one asset to a field with multiplicity 1 passes."""
    spec = """
let servers = Server(1);
let databases = Database(5);

connect {
    1: databases --> [hostedOn] servers;
}
"""
    instantiate(spec, multiplicityLang_path)


# Guaranteed violations


def test_violation_guaranteed_over_upper_bound(instantiate, multiplicityLang_path):
    """A set whose minimum count exceeds the field's upper bound with weight=1
    is a guaranteed violation."""
    spec = """
let servers = Server(1);
let software = Software(4);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_over_multiplicity_one(instantiate, multiplicityLang_path):
    """Connecting more than one asset to a field with multiplicity 1 with
    weight=1 is a guaranteed violation."""
    spec = """
let servers = Server(2);
let databases = Database(1);

connect {
    1: databases --> [hostedOn] servers;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_under_lower_bound(instantiate, multiplicityLang_path):
    """A set whose maximum count falls below the field's lower bound with
    weight=1 is a guaranteed violation."""
    spec = """
let servers_a = Server(1);
let servers_b = Server(3);

connect {
    1: servers_a --> [monitors] servers_b;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_under_lower_bound_zero_assets(
    instantiate, multiplicityLang_path
):
    """Connecting zero assets to a field with a lower bound greater than zero
    with weight=1 is a guaranteed violation."""
    spec = """
let servers = Server(1);
let software = Software(0);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


# Connection weight semantics


def test_no_violation_weight_below_one_does_not_trigger_underconnection(
    instantiate, multiplicityLang_path
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
    instantiate(spec, multiplicityLang_path)


def test_no_violation_multiple_rules_accumulate_within_upper_bound(
    instantiate, multiplicityLang_path
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
    instantiate(spec, multiplicityLang_path)


def test_no_violation_lower_bound_above_one_satisfied(
    instantiate, multiplicityLang_path
):
    """Connecting at least as many assets as a lower bound greater than 1
    requires passes."""
    spec = """
let servers = Server(6);

connect {
    1: servers --> [monitors] servers;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_over_upper_bound_multiple_rules_accumulated(
    instantiate, multiplicityLang_path
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
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


# Subsystem instantiation


def test_no_violation_within_bounds_inside_subsystem(
    instantiate, multiplicityLang_path
):
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
    instantiate(spec, multiplicityLang_path)


def test_no_violation_within_bounds_nested_subsystem(
    instantiate, multiplicityLang_path
):
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
    instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_over_upper_bound_inside_subsystem(
    instantiate, multiplicityLang_path
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
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_under_lower_bound_inside_subsystem(
    instantiate, multiplicityLang_path
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
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


# Distribution expressions


def test_no_violation_exact_upper_bound_with_distribution(
    instantiate, multiplicityLang_path
):
    """A distribution whose entire support fits within the multiplicity range
    passes."""
    spec = """
let servers = Server(1);
let software = Software(Uniform(1, 3));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_no_violation_distribution_with_uncertain_bounds(
    instantiate, multiplicityLang_path
):
    """A distribution whose bounds straddle the multiplicity limits cannot be
    statically guaranteed to violate, so no static error is raised.
    Runtime violations from maltoolbox are acceptable here."""
    spec = """
let servers = Server(1);
let software = Software(Binomial(5, 0.5));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    try:
        instantiate(spec, multiplicityLang_path)
    except ValueError:
        pass  # Probabilistic runtime violation, not a static analyzer error


def test_no_violation_certain_count_at_upper_bound_with_distribution(
    instantiate, multiplicityLang_path
):
    """A distribution that always yields exactly the upper bound passes."""
    spec = """
let servers = Server(1);
let software = Software(Binomial(3, 1.0));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_over_distribution_certain_above_upper_bound(
    instantiate, multiplicityLang_path
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
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_violation_guaranteed_over_distribution_always_max(
    instantiate, multiplicityLang_path
):
    """A distribution with p=1.0 that always yields its maximum, which exceeds
    the upper bound, is a guaranteed violation."""
    spec = """
let servers = Server(1);
let software = Software(Binomial(10, 1.0));

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


# Param expressions


def test_no_violation_param_constant_within_bounds(instantiate, multiplicityLang_path):
    """A param = constant used as asset count that stays within the
    multiplicity range passes the static check."""
    spec = """
param n = 2;

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_violation_param_constant_over_upper_bound(instantiate, multiplicityLang_path):
    """A param = constant that puts the asset count above the multiplicity
    upper bound is a guaranteed violation."""
    spec = """
param n = 5;

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_violation_param_constant_under_lower_bound(
    instantiate, multiplicityLang_path
):
    """A param = constant that puts the asset count below the multiplicity
    lower bound is a guaranteed violation."""
    spec = """
param n = 3;

let servers_a = Server(1);
let servers_b = Server(n);

connect {
    1: servers_a --> [monitors] servers_b;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_no_violation_param_distribution_within_bounds(
    instantiate, multiplicityLang_path
):
    """A param ~ distribution whose entire support stays within the
    multiplicity range passes the static check."""
    spec = """
param n ~ Uniform(1, 3);

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_violation_param_distribution_always_over_upper_bound(
    instantiate, multiplicityLang_path
):
    """A param ~ distribution whose entire support exceeds the multiplicity
    upper bound is a guaranteed violation."""
    spec = """
param n ~ Uniform(4, 6);

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_no_violation_param_arithmetic_within_bounds(
    instantiate, multiplicityLang_path
):
    """A param defined via arithmetic on another param evaluates correctly
    and passes when the result is within bounds."""
    spec = """
param base = 1;
param n = base + 1;

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_violation_param_arithmetic_over_upper_bound(
    instantiate, multiplicityLang_path
):
    """A param defined via arithmetic that evaluates above the multiplicity
    upper bound is a guaranteed violation."""
    spec = """
param base = 3;
param n = base + 2;

let servers = Server(1);
let software = Software(n);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)


def test_no_violation_param_chained_arithmetic_within_bounds(
    instantiate, multiplicityLang_path
):
    """A chain of params each referencing the previous evaluates correctly
    and does not produce a false violation."""
    spec = """
param a = 3;
param b = a / 3;
param c = b * 2;

let servers = Server(1);
let software = Software(c);

connect {
    1: servers --> [installedSoftware] software;
}
"""
    instantiate(spec, multiplicityLang_path)


def test_no_violation_param_used_in_subsystem_within_bounds(
    instantiate, multiplicityLang_path
):
    """A global param used inside a subsystem for asset count propagates
    through subsystem multiplication without causing a violation."""
    spec = """
param n = 2;

subsystem Unit {
    let server = Server(1);
    let software = Software(n);

    connect {
        1: server --> [installedSoftware] software;
    }
}

let units = Unit(1);
"""
    instantiate(spec, multiplicityLang_path)


def test_violation_param_used_in_subsystem_over_upper_bound(
    instantiate, multiplicityLang_path
):
    """A global param used inside a subsystem that causes an over-connection
    is detected after subsystem bounds are propagated upward."""
    spec = """
param n = 5;

subsystem Unit {
    let server = Server(1);
    let software = Software(n);

    connect {
        1: server --> [installedSoftware] software;
    }
}

let units = Unit(1);
"""
    with pytest.raises(Exception, match='(?i)multiplicity'):
        instantiate(spec, multiplicityLang_path)
