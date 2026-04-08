"""
Prune functionality tests.

These tests verify both the semantic analysis of prune directives and the
runtime behaviour of pruning during model instantiation. Tests use pruneLang,
a simple language with no mandatory multiplicity constraints, so that the
shape of the pruned model can be reasoned about precisely without rejection
sampling interference.
"""

import pytest


# Semantic analysis: valid prune directives


def test_no_exception_on_prune_no_args(instantiate, pruneLang_path):
    """A bare prune; with no arguments should be semantically valid."""
    spec = """
let nodes = Node(5);

connect {
    0.5: nodes --> [rightNodes] nodes;
}

prune;
"""
    instantiate(spec, pruneLang_path)


def test_no_exception_on_prune_empty_parens(instantiate, pruneLang_path):
    """prune(); with empty parentheses should be semantically valid."""
    spec = """
let nodes = Node(5);

connect {
    0.5: nodes --> [rightNodes] nodes;
}

prune();
"""
    instantiate(spec, pruneLang_path)


def test_no_exception_on_prune_single_argument(instantiate, pruneLang_path):
    """prune with a single named variable argument should be valid."""
    spec = """
let nodes = Node(5);

connect {
    0.5: nodes --> [rightNodes] nodes;
}

prune(nodes);
"""
    instantiate(spec, pruneLang_path)


def test_no_exception_on_prune_multiple_arguments(instantiate, pruneLang_path):
    """prune with multiple named variable arguments should be valid."""
    spec = """
let nodes = Node(5);
let satellites = Satellite(3);

connect {
    0.5: nodes --> [rightNodes] nodes;
    0.5: nodes --> [satellites] satellites;
}

prune(nodes, satellites);
"""
    instantiate(spec, pruneLang_path)


def test_no_exception_on_prune_subsystem_access_argument(instantiate, pruneLang_path):
    """prune with a subsystem dot-access argument should be valid."""
    spec = """
subsystem Cluster {
    let hub = Node(1);
    let members = Node(3);

    connect {
        1: hub --> [rightNodes] members;
    }
}

let clusters = Cluster(2);

prune(clusters.hub);
"""
    instantiate(spec, pruneLang_path)


# Semantic analysis: invalid prune directives


def test_exception_on_prune_undeclared_variable(instantiate, pruneLang_path):
    """prune referencing an undeclared variable should raise a semantic error
    pointing to the offending line."""
    spec = """
let nodes = Node(5);

prune(undeclared); // <- line 4
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, pruneLang_path)

    assert 'line 4' in str(exc_info.value).lower()


def test_exception_on_prune_invalid_subsystem_member(instantiate, pruneLang_path):
    """prune referencing a non-existent subsystem member should raise a
    semantic error pointing to the offending line."""
    spec = """
subsystem Cluster {
    let hub = Node(1);
}

let clusters = Cluster(2);

prune(clusters.invalid); // <- line 8
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, pruneLang_path)

    assert 'line 8' in str(exc_info.value).lower()


def test_exception_on_prune_bare_subsystem_variable(instantiate, pruneLang_path):
    """Passing a bare subsystem variable (not a dot-access into it) should
    raise a semantic error pointing to the offending line. A subsystem name
    is not an asset set."""
    spec = """
subsystem Cluster {
    let hub = Node(1);
    let members = Node(3);
}

let clusters = Cluster(2); // <- 'clusters' is a subsystem, not an asset set

prune(clusters); // <- line 9
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, pruneLang_path)

    assert 'line 9' in str(exc_info.value).lower()


def test_exception_on_prune_bare_subsystem_one_of_multiple_args(
    instantiate, pruneLang_path
):
    """A bare subsystem variable among otherwise valid arguments should still
    raise an error pointing to the offending name."""
    spec = """
subsystem Cluster {
    let hub = Node(1);
}

let nodes = Node(3);
let clusters = Cluster(2);

prune(nodes, clusters); // <- line 9, 'clusters' is a subsystem
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, pruneLang_path)

    assert 'line 9' in str(exc_info.value).lower()


def test_no_exception_on_prune_member_of_subsystem_not_bare(
    instantiate, pruneLang_path
):
    """Using dot-access into a subsystem should be valid even though the bare
    subsystem variable itself would be rejected."""
    spec = """
subsystem Cluster {
    let hub = Node(1);
    let members = Node(3);

    connect {
        1: hub --> [rightNodes] members;
    }
}

let clusters = Cluster(2);

prune(clusters.hub);
"""
    instantiate(spec, pruneLang_path)


# Semantic analysis: bare subsystem check with inheritanceLang


def test_exception_on_prune_bare_subsystem_with_child_asset_type(
    instantiate, inheritanceLang_path
):
    """The bare-subsystem check should work correctly even when the subsystem
    contains assets of a child type that extends a parent with associations.
    The subsystem variable itself must still be rejected."""
    spec = """
subsystem Group {
    let children = Child(3);
    let others = Other(2);

    connect {
        1: children --> [others] others;
    }
}

let groups = Group(2); // <- 'groups' is a subsystem, not an asset set

prune(groups); // <- line 13
"""
    with pytest.raises(Exception) as exc_info:
        instantiate(spec, inheritanceLang_path)

    assert 'line 13' in str(exc_info.value).lower()


def test_no_exception_on_prune_member_of_subsystem_with_child_asset_type(
    instantiate, inheritanceLang_path
):
    """Dot-access into a subsystem containing child-typed assets should be
    accepted even though the bare subsystem variable would be rejected."""
    spec = """
subsystem Group {
    let children = Child(3);
    let others = Other(2);

    connect {
        1: children --> [others] others;
    }
}

let groups = Group(2);

prune(groups.children);
"""
    instantiate(spec, inheritanceLang_path)


# Runtime: giant component pruning


def test_giant_component_prune_removes_isolated_nodes(
    instantiate_and_load, pruneLang_path
):
    """With weight=1 on a fully connected set, prune; should retain all
    nodes since they form a single component."""
    spec = """
let nodes = Node(5);

connect {
    1: nodes --> [rightNodes] nodes;
}

prune;
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 5


def test_giant_component_prune_removes_isolated_nodes_with_zero_weight(
    instantiate_and_load, pruneLang_path
):
    """With weight=0 no connections are formed, so every node is its own
    component. prune; retains only one node (the giant component when all
    components are size 1, broken arbitrarily)."""
    spec = """
let nodes = Node(5);

connect {
    0: nodes --> [rightNodes] nodes;
}

prune;
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 1


def test_giant_component_prune_retains_largest_component(
    instantiate_and_load, pruneLang_path
):
    """Two groups with internal weight=1 but no inter-group connections form
    two separate components. prune; retains only the larger one."""
    spec = """
let big = Node(4);
let small = Node(2);

connect {
    1: big --> [rightNodes] big;
    1: small --> [rightNodes] small;
}

prune;
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 4


def test_giant_component_prune_when_all_components_equal_size(
    instantiate_and_load, pruneLang_path
):
    """When all components are the same size, prune; retains exactly one
    component."""
    spec = """
let a = Node(3);
let b = Node(3);

connect {
    1: a --> [rightNodes] a;
    1: b --> [rightNodes] b;
}

prune;
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 3


def test_giant_component_prune_mixed_asset_types(instantiate_and_load, pruneLang_path):
    """Satellites attached to the largest node cluster should be retained
    along with their connected nodes."""
    spec = """
let big_nodes = Node(4);
let big_sats = Satellite(2);
let isolated = Node(1);

connect {
    1: big_nodes --> [rightNodes] big_nodes;
    1: big_nodes --> [satellites] big_sats;
}

prune;
"""
    model = instantiate_and_load(spec, pruneLang_path)
    # 4 nodes + 2 satellites in the giant component; 1 isolated node removed
    assert len(model.assets) == 6


# Runtime: anchor-set pruning


def test_anchor_prune_retains_component_containing_anchor(
    instantiate_and_load, pruneLang_path
):
    """With two disconnected groups, prune(anchor) retains only the component
    containing assets from the anchor set."""
    spec = """
let anchors = Node(3);
let others = Node(3);

connect {
    1: anchors --> [rightNodes] anchors;
    1: others --> [rightNodes] others;
}

prune(anchors);
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 3
    for asset in model.assets.values():
        assert asset.type == 'Node'


def test_anchor_prune_retains_multiple_components_when_multiple_anchors(
    instantiate_and_load, pruneLang_path
):
    """With three disconnected groups and anchors in two of them, prune
    retains both anchored components and discards the third."""
    spec = """
let a = Node(3);
let b = Node(3);
let c = Node(3);

connect {
    1: a --> [rightNodes] a;
    1: b --> [rightNodes] b;
    1: c --> [rightNodes] c;
}

prune(a, b);
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 6


def test_anchor_prune_retains_whole_component_not_just_anchor_assets(
    instantiate_and_load, pruneLang_path
):
    """When an anchor is connected to other nodes, the entire component
    is retained, not just the anchor assets themselves."""
    spec = """
let anchors = Node(1);
let connected = Node(4);
let isolated = Node(2);

connect {
    1: anchors --> [rightNodes] connected;
    1: isolated --> [rightNodes] isolated;
}

prune(anchors);
"""
    model = instantiate_and_load(spec, pruneLang_path)
    # The anchor's component contains anchor (1) + connected (4) = 5 assets.
    # The isolated group (2) has no anchor so it is removed.
    assert len(model.assets) == 5


def test_anchor_prune_with_mixed_asset_types(instantiate_and_load, pruneLang_path):
    """Satellites in the same component as the anchor are retained along with
    their connected nodes."""
    spec = """
let anchors = Node(2);
let sats = Satellite(3);
let isolated = Node(2);

connect {
    1: anchors --> [rightNodes] anchors;
    1: anchors --> [satellites] sats;
    1: isolated --> [rightNodes] isolated;
}

prune(anchors);
"""
    model = instantiate_and_load(spec, pruneLang_path)
    # 2 anchor nodes + 3 satellites retained; 2 isolated nodes removed
    assert len(model.assets) == 5


def test_anchor_prune_subsystem_access(instantiate_and_load, pruneLang_path):
    """prune can be given a subsystem member as anchor, retaining the
    component reachable from those assets."""
    spec = """
subsystem Cluster {
    let hub = Node(1);
    let spokes = Node(3);

    connect {
        1: hub --> [rightNodes] spokes;
    }
}

let clusters = Cluster(1);
let isolated = Node(2);

connect {
    1: isolated --> [rightNodes] isolated;
}

prune(clusters.hub);
"""
    model = instantiate_and_load(spec, pruneLang_path)
    # hub (1) + spokes (3) retained; isolated (2) removed
    assert len(model.assets) == 4


def test_anchor_prune_all_components_anchored_retains_all(
    instantiate_and_load, pruneLang_path
):
    """When every component has an anchor, no assets are removed."""
    spec = """
let a = Node(3);
let b = Node(3);

connect {
    1: a --> [rightNodes] a;
    1: b --> [rightNodes] b;
}

prune(a, b);
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 6


def test_anchor_prune_no_anchored_components_removes_all(
    instantiate_and_load, pruneLang_path
):
    """When the anchor set is empty (weight=0 so no assets reach the anchor
    variables), all components that contain no anchor assets are removed.
    Here anchors is an empty set due to zero instantiation, so all nodes
    are removed."""
    spec = """
let nodes = Node(4);
let anchors = Node(0);

connect {
    0: nodes --> [rightNodes] nodes;
}

prune(anchors);
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 0


# Runtime: prune interacts correctly with subsystem instantiation


def test_giant_component_prune_across_subsystem_instances(
    instantiate_and_load, pruneLang_path
):
    """Multiple subsystem instances connected at weight=1 should all belong
    to the same component and all be retained by prune;."""
    spec = """
subsystem Unit {
    let node = Node(2);
}

let units = Unit(3);

connect {
    1: units.node --> [rightNodes] units.node;
}

prune;
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 6


def test_giant_component_prune_disconnected_subsystem_instances(
    instantiate_and_load, pruneLang_path
):
    """Multiple subsystem instances with no inter-instance connections form
    separate components. prune; retains only the largest."""
    spec = """
subsystem Unit {
    let node = Node(1);
}

let big = Unit(4);
let small = Unit(2);

connect {
    1: big.node --> [rightNodes] big.node;
    1: small.node --> [rightNodes] small.node;
}

prune;
"""
    model = instantiate_and_load(spec, pruneLang_path)
    assert len(model.assets) == 4
