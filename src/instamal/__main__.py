import argparse
from .instantiator import ModelInstantiator


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

    args = parser.parse_args()

    instantiator = ModelInstantiator(args.spec_path, args.lang_path)
    instantiator.instantiate(args.out_path, args.num_instances)


if __name__ == "__main__":
    main()
