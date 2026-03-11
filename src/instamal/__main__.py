import argparse
from .instantiator import ModelInstantiator
from .visualizer import ModelVisualizer


def main():
    parser = argparse.ArgumentParser(
        description="Generate model instances based on specified domain specifications."
    )

    parser.add_argument(
        "-s",
        "--spec_path",
        type=str,
        required=True,
        help="path to the system domain specification",
    )
    parser.add_argument(
        "-l",
        "--lang_path",
        type=str,
        required=True,
        help="path to the MAL domain-specific language",
    )
    parser.add_argument(
        "-n",
        "--num_instances",
        type=int,
        default=1,
        help="number of model instances to generate (default: 1)",
    )
    parser.add_argument(
        "-o",
        "--out_path",
        type=str,
        default="models",
        help='output path for the generated model instances (default: "models")',
    )
    parser.add_argument(
        "-v",
        "--visualize",
        type=int,
        default=0,
        help='Generate visualizations for the first n model instances (-v n). Creates a "vis" directory with .png files and a `visualization_summary.pdf` in the output path. Use -v 0 to disable (default: 0).',
    )

    args = parser.parse_args()

    instantiator = ModelInstantiator(args.spec_path, args.lang_path)
    instantiator.instantiate(args.out_path, args.num_instances)
    if args.visualize > 0:
        ModelVisualizer(args.out_path, args.visualize, args.lang_path)


if __name__ == "__main__":
    main()
