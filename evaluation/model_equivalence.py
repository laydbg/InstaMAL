"""
Utilities for checking equivalence and subgraph containment between
MAL model instances serialized as YAML by maltoolbox.

Two models are considered equivalent if their typed graphs are
isomorphic under node type and edge field name labels.

A model A is considered a sub-model of model B if there exists a
subgraph of B that is isomorphic to A under the same label constraints.
"""

import yaml
import networkx as nx
from networkx.algorithms import isomorphism
from collections import defaultdict


def load_model(path: str) -> dict:
    """Load a maltoolbox YAML model file and return the parsed dict."""
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def build_graph(model: dict) -> nx.DiGraph:
    """
    Serialize a maltoolbox model instance into a labeled DiGraph.

    Nodes are identified by integer asset ids and carry a 'type' attribute
    corresponding to the asset's type field in the YAML.

    Parallel edges between the same pair of nodes are collapsed into a
    single edge whose 'fields' attribute is a frozenset of all field names
    between that pair. This allows DiGraphMatcher to be used while still
    preserving full association information.
    """
    assets = model.get('assets', {})

    # Collect all edges first, grouping parallel edges by (src, dst)
    edge_fields = defaultdict(set)

    for asset_id, asset_data in assets.items():
        src = int(asset_id)
        for field_name, targets in asset_data.get('associated_assets', {}).items():
            for target_id in targets:
                dst = int(target_id)
                edge_fields[(src, dst)].add(field_name)

    G = nx.DiGraph()

    for asset_id, asset_data in assets.items():
        G.add_node(int(asset_id), type=asset_data['type'])

    for (src, dst), fields in edge_fields.items():
        G.add_edge(src, dst, fields=frozenset(fields))

    return G


def _node_match(n1_attrs: dict, n2_attrs: dict) -> bool:
    """Node label match function: asset types must be equal."""
    return n1_attrs['type'] == n2_attrs['type']


def _edge_match(e1_attrs: dict, e2_attrs: dict) -> bool:
    """
    Edge label match function: the sets of field names on both edges
    must be equal.
    """
    return e1_attrs['fields'] == e2_attrs['fields']


def are_equivalent(model_a: dict, model_b: dict) -> bool:
    """
    Return True if model_a and model_b are isomorphic as typed graphs.

    Two models are equivalent if there exists a bijection between their
    asset sets that preserves asset types and association field names.
    """
    G_a = build_graph(model_a)
    G_b = build_graph(model_b)

    if G_a.number_of_nodes() != G_b.number_of_nodes():
        return False
    if G_a.number_of_edges() != G_b.number_of_edges():
        return False

    matcher = isomorphism.DiGraphMatcher(
        G_a,
        G_b,
        node_match=_node_match,
        edge_match=_edge_match,
    )
    return matcher.is_isomorphic()


def is_submodel(model_a: dict, model_b: dict) -> bool:
    """
    Return True if model_a is isomorphic to a subgraph of model_b.

    Every asset and every association in model_a must appear in model_b
    under a type and field name preserving mapping. Asset types and
    association field names must match exactly.
    """
    G_a = build_graph(model_a)
    G_b = build_graph(model_b)

    if G_a.number_of_nodes() > G_b.number_of_nodes():
        return False
    if G_a.number_of_edges() > G_b.number_of_edges():
        return False

    matcher = isomorphism.DiGraphMatcher(
        G_b,
        G_a,
        node_match=_node_match,
        edge_match=_edge_match,
    )
    return matcher.subgraph_is_isomorphic()


def get_submodel_mapping(model_a: dict, model_b: dict) -> dict | None:
    """
    If model_a is a sub-model of model_b, return a dict mapping node ids
    in model_a to node ids in model_b that witnesses the isomorphism.
    Returns None if no such mapping exists.
    """
    G_a = build_graph(model_a)
    G_b = build_graph(model_b)

    matcher = isomorphism.DiGraphMatcher(
        G_a,
        G_b,
        node_match=_node_match,
        edge_match=_edge_match,
    )
    try:
        return next(matcher.subgraph_isomorphisms_iter())
    except StopIteration:
        return None


def are_equivalent_from_files(path_a: str, path_b: str) -> bool:
    """Load two YAML model files and check full equivalence."""
    return are_equivalent(load_model(path_a), load_model(path_b))


def is_submodel_from_files(path_a: str, path_b: str) -> bool:
    """
    Load two YAML model files and check if model_a is a sub-model of model_b.
    """
    return is_submodel(load_model(path_a), load_model(path_b))


def get_submodel_mapping_from_files(path_a: str, path_b: str) -> dict | None:
    """
    Load two YAML model files and return a witness mapping if model_a
    is a sub-model of model_b, or None otherwise.
    """
    return get_submodel_mapping(load_model(path_a), load_model(path_b))


if __name__ == '__main__':
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description='Check equivalence or subgraph containment between two MAL model instances.'
    )
    parser.add_argument(
        '-s',
        action='store_true',
        help='Check if model A is a sub-model of model B instead of full equivalence.',
    )
    parser.add_argument(
        '-w',
        action='store_true',
        help='Show witness mapping for the found match.',
    )
    parser.add_argument(
        'model_a',
        help='Path to model A YAML file, or a directory of YAML files to compare against model B.',
    )
    parser.add_argument('model_b', help='Path to model B YAML file.')

    args = parser.parse_args()

    if os.path.isdir(args.model_a):
        paths = [
            os.path.join(args.model_a, f)
            for f in sorted(os.listdir(args.model_a))
            if f.endswith('.yml') or f.endswith('.yaml')
        ]
        if not paths:
            print(f'No YAML files found in directory: {args.model_a}')
        else:
            for path in paths:
                if args.s:
                    result = is_submodel_from_files(args.model_b, path)
                    if not result:
                        print(
                            f'{os.path.basename(path)}: NOT a sub-model of {os.path.basename(args.model_b)}.'
                        )
                else:
                    result = are_equivalent_from_files(path, args.model_b)
                    if not result:
                        print(
                            f'{os.path.basename(path)}: NOT equivalent to {os.path.basename(args.model_b)}.'
                        )
                if result and args.w:
                    print(
                        f'{os.path.basename(path)} witness (A node -> B node): {get_submodel_mapping_from_files(path, args.model_b)}.'
                    )
            print('Done.')
    else:
        if args.s:
            result = is_submodel_from_files(args.model_a, args.model_b)
            if result:
                print('A is a sub-model of B.')
            else:
                print('A is NOT a sub-model of B.')
        else:
            result = are_equivalent_from_files(args.model_a, args.model_b)
            if result:
                print('A and B are equivalent.')
            else:
                print('A and B are NOT equivalent.')
        if result and args.w:
            mapping = get_submodel_mapping_from_files(args.model_a, args.model_b)
            print('Witness mapping (A node -> B node):', mapping)
