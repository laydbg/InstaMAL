import argparse
from collections import defaultdict
from pathlib import Path
from maltoolbox.language import LanguageGraph
from maltoolbox.model import Model


def iter_model_files(models_dir: str):
    for path in sorted(Path(models_dir).iterdir()):
        if path.suffix in {'.json', '.yml', '.yaml'}:
            yield path


def get_or_assign_id(name: str, mapping: dict[str, int]) -> int:
    if name not in mapping:
        mapping[name] = len(mapping) + 1  # Fanmod edge colors must be >=1
    return mapping[name]


def get_assoc_name(asset, fieldname: str) -> str:
    return asset.lg_asset.associations[fieldname].name


def write_associations_from_models_dir(
    models_dir: str,
    output_path: str,
    lang_graph,
):
    type_to_id: dict[str, int] = {}
    assoc_to_id: dict[str, int] = {}

    asset_id_offset = 0

    with open(output_path, 'w', encoding='utf-8') as out:
        # Asset and associations types are globally static across models
        # Asset instanciations are globally unique across models
        for model_path in iter_model_files(models_dir):
            model = Model.load_from_file(str(model_path), lang_graph)

            edge_counter = defaultdict(int)

            for from_asset in model.assets.values():
                global_from_id = from_asset.id + asset_id_offset
                from_type_id = get_or_assign_id(from_asset.type, type_to_id)

                for fieldname, to_assets in from_asset.associated_assets.items():
                    assoc = from_asset.lg_asset.associations[fieldname]
                    assoc_name = assoc.name
                    assoc_id = get_or_assign_id(assoc_name, assoc_to_id)

                    for to_asset in to_assets:
                        global_to_id = to_asset.id + asset_id_offset
                        to_type_id = get_or_assign_id(to_asset.type, type_to_id)

                        key = (
                            global_from_id,
                            global_to_id,
                            from_type_id,
                            to_type_id,
                            assoc_id,
                        )
                        edge_counter[key] += 1

            # Use association names as undirectional edges between assets, rather
            # than a pair of directed edges using fieldnames.
            processed = set()
            for (a, b, a_type, b_type, assoc_id), count_ab in edge_counter.items():
                if (a, b, assoc_id) in processed:
                    continue

                count_ba = edge_counter.get((b, a, b_type, a_type, assoc_id), 0)

                undirected_count = min(count_ab, count_ba)
                for _ in range(undirected_count):
                    out.write(f'{a} {b} {a_type} {b_type} {assoc_id}\n')

                processed.add((a, b, assoc_id))
                processed.add((b, a, assoc_id))

            max_local_id = max(asset.id for asset in model.assets.values())
            asset_id_offset += max_local_id + 1

    return type_to_id, assoc_to_id


def write_id_maps(type_to_id, assoc_to_id, output_dir: Path, prefix: str):
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / f'{prefix}_types.txt', 'w', encoding='utf-8') as f:
        for name, i in sorted(type_to_id.items(), key=lambda x: x[1]):
            f.write(f'{i} {name}\n')

    with open(output_dir / f'{prefix}_assocs.txt', 'w', encoding='utf-8') as f:
        for name, i in sorted(assoc_to_id.items(), key=lambda x: x[1]):
            f.write(f'{i} {name}\n')


def main():
    parser = argparse.ArgumentParser(
        description='Export associations from multiple MAL models using global IDs'
    )
    parser.add_argument(
        'models_dir',
        help='Directory containing model files (.json/.yml/.yaml)',
    )
    parser.add_argument(
        'output_dir',
        help='Directory to write output files (edge list + ID maps)',
    )
    parser.add_argument(
        '--lang',
        required=True,
        help='Path to the MAL language file',
    )
    parser.add_argument(
        '--dict-prefix',
        default='ids',
        help='Prefix for ID mapping files',
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_file = output_dir / 'edges.txt'

    lang_graph = LanguageGraph.load_from_file(args.lang)

    type_to_id, assoc_to_id = write_associations_from_models_dir(
        args.models_dir,
        output_file,
        lang_graph,
    )

    write_id_maps(type_to_id, assoc_to_id, output_dir, args.dict_prefix)


if __name__ == '__main__':
    main()
