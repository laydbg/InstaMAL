"""
Defense control tests.

These tests verify both the semantic analysis of defense control directives
in asset instantiations and their runtime effect on the generated model.

trainingLang defenses (from the language definition):
  Host: notPresent
  Data: notPresent
  User: notPresent
  Network: (none)
"""

import pytest


# Semantic analysis: valid defense control


def test_no_exception_on_instantiation_without_defenses(instantiate, trainingLang_path):
    """Asset instantiation without defense controls should be unaffected."""
    spec = """
let hosts = Host(3);
"""
    instantiate(spec, trainingLang_path)


def test_no_exception_on_defense_control_literal(instantiate, trainingLang_path):
    """Setting a defense to a numeric literal should be valid."""
    spec = """
let host = Host(1, notPresent=0.7);
"""
    instantiate(spec, trainingLang_path)


def test_no_exception_on_defense_control_param(instantiate, trainingLang_path):
    """Setting a defense to a param expression should be valid."""
    spec = """
param b = 0.5;
let host = Host(1, notPresent=b);
"""
    instantiate(spec, trainingLang_path)


def test_no_exception_on_defense_control_distribution(instantiate, trainingLang_path):
    """Setting a defense to a distribution sample should be valid."""
    spec = """
let host = Host(1, notPresent=Uniform(0, 1));
"""
    instantiate(spec, trainingLang_path)


def test_no_exception_on_defense_control_multiple_assets(
    instantiate, trainingLang_path
):
    """Defense control applies uniformly to all instantiated assets when
    count > 1."""
    spec = """
let hosts = Host(5, notPresent=0.3);
"""
    instantiate(spec, trainingLang_path)


def test_no_exception_on_defense_control_zero_and_one_boundary(
    instantiate, trainingLang_path
):
    """Defense values of exactly 0 and 1 are valid boundary values."""
    spec = """
let h1 = Host(1, notPresent=0);
let h2 = Host(1, notPresent=1);
"""
    instantiate(spec, trainingLang_path)


def test_no_exception_on_multiple_assets_different_defenses(
    instantiate, trainingLang_path
):
    """Different asset instantiations may each set their own defenses
    independently."""
    spec = """
let hosts = Host(2, notPresent=0.8);
let users = User(2, notPresent=0.2);
"""
    instantiate(spec, trainingLang_path)


# Semantic analysis: invalid defense control


def test_exception_on_unknown_defense_name(instantiate, trainingLang_path):
    """A defense name that does not exist on the asset type should raise a
    semantic error pointing to the offending line."""
    spec = """
let host = Host(1, nonExistentDefense=0.5); // <- line 2
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, trainingLang_path)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_defense_on_asset_without_defenses(instantiate, trainingLang_path):
    """Applying a defense control to an asset type that has no defenses
    should raise a semantic error pointing to the offending line."""
    spec = """
let network = Network(1, anyDefense=0.5); // <- line 2
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, trainingLang_path)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_duplicate_defense_name(instantiate, trainingLang_path):
    """Setting the same defense twice in one instantiation should raise a
    semantic error pointing to the second occurrence."""
    spec = """
let host = Host(1, notPresent=0.3, notPresent=0.7); // <- line 2
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, trainingLang_path)

    assert 'line 2' in str(exc_info.value).lower()


def test_exception_on_defense_on_subsystem_instantiation(
    instantiate, trainingLang_path
):
    """Applying a defense control to a subsystem instantiation should raise
    a semantic error pointing to the offending line."""
    spec = """
subsystem HostGroup {
    let host = Host(1);
}

let groups = HostGroup(2, notPresent=0.5); // <- line 6
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, trainingLang_path)

    assert 'line 6' in str(exc_info.value).lower()


# Runtime: defense values are stored on model assets


def test_defense_value_is_stored_on_asset(instantiate_and_load, trainingLang_path):
    """The defense value set in the spec should appear on the corresponding
    model assets."""
    spec = """
let host = Host(1, notPresent=0.75);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    assert len(model.assets) == 1
    asset = next(iter(model.assets.values()))
    assert asset.defenses is not None
    assert 'notPresent' in asset.defenses
    assert asset.defenses['notPresent'] == pytest.approx(0.75)


def test_defense_value_applied_to_all_assets_in_set(
    instantiate_and_load, trainingLang_path
):
    """When multiple assets are instantiated with a defense control, every
    asset in the set should carry the specified defense value."""
    spec = """
let hosts = Host(4, notPresent=0.3);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    assert len(model.assets) == 4
    for asset in model.assets.values():
        assert asset.defenses is not None
        assert asset.defenses['notPresent'] == pytest.approx(0.3)


def test_no_defense_set_when_not_specified(instantiate_and_load, trainingLang_path):
    """Assets instantiated without defense controls should not have any
    explicitly set defense values (defenses dict is None or empty)."""
    spec = """
let host = Host(1);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    asset = next(iter(model.assets.values()))
    assert not asset.defenses


def test_defense_value_clamped_below_zero(instantiate_and_load, trainingLang_path):
    """A defense expression that evaluates below 0 should be clamped to 0."""
    spec = """
param v = -0.5;
let host = Host(1, notPresent=v);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    asset = next(iter(model.assets.values()))
    assert asset.defenses['notPresent'] == pytest.approx(0.0)


def test_defense_value_clamped_above_one(instantiate_and_load, trainingLang_path):
    """A defense expression that evaluates above 1 should be clamped to 1."""
    spec = """
param v = 1.5;
let host = Host(1, notPresent=v);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    asset = next(iter(model.assets.values()))
    assert asset.defenses['notPresent'] == pytest.approx(1.0)


def test_defense_value_within_range_not_clamped(
    instantiate_and_load, trainingLang_path
):
    """A defense expression within [0, 1] should not be altered."""
    spec = """
let host = Host(1, notPresent=0.42);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    asset = next(iter(model.assets.values()))
    assert asset.defenses['notPresent'] == pytest.approx(0.42)


def test_different_assets_carry_independent_defense_values(
    instantiate_and_load, trainingLang_path
):
    """Two asset sets with different defense values should each carry their
    own correct value, not bleed into each other."""
    spec = """
let hosts = Host(2, notPresent=0.9);
let users = User(2, notPresent=0.1);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    for asset in model.assets.values():
        if asset.type == 'Host':
            assert asset.defenses['notPresent'] == pytest.approx(0.9)
        elif asset.type == 'User':
            assert asset.defenses['notPresent'] == pytest.approx(0.1)


def test_defense_value_from_param_expression(instantiate_and_load, trainingLang_path):
    """A defense value derived from a param expression should evaluate
    correctly and be stored on the asset."""
    spec = """
param base = 0.4;
param defense_val = base + 0.2;
let host = Host(1, notPresent=defense_val);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    asset = next(iter(model.assets.values()))
    assert asset.defenses['notPresent'] == pytest.approx(0.6)


def test_defense_inside_subsystem_instantiation(
    instantiate_and_load, trainingLang_path
):
    """Defense controls inside a subsystem let declaration should be applied
    to the assets when the subsystem is instantiated."""
    spec = """
subsystem HostGroup {
    let host = Host(1, notPresent=0.55);
}

let groups = HostGroup(2);
"""
    model = instantiate_and_load(spec, trainingLang_path)
    host_assets = [a for a in model.assets.values() if a.type == 'Host']
    assert len(host_assets) == 2
    for asset in host_assets:
        assert asset.defenses['notPresent'] == pytest.approx(0.55)
