import argparse
import logging

from instamal.instantiation import ModelInstantiator
from instamal.visualization import ModelVisualizer


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s',
    )

    parser = argparse.ArgumentParser(
        description='Generate model instances based on specified domain specifications.'
    )
    parser.add_argument(
        '-s',
        '--spec_path',
        type=str,
        required=True,
        help='path to the system domain specification',
    )
    parser.add_argument(
        '-l',
        '--lang_path',
        type=str,
        required=True,
        help='path to the MAL domain-specific language',
    )
    parser.add_argument(
        '-n',
        '--num_instances',
        type=int,
        default=1,
        metavar='N',
        help='number of model instances to generate (default: 1)',
    )
    parser.add_argument(
        '-o',
        '--out_path',
        type=str,
        default='out_dir',
        help='output path for the generated model instances (default: "models")',
    )
    parser.add_argument(
        '-v',
        '--visualize',
        type=int,
        default=0,
        metavar='N',
        help=(
            'generate visualizations for the first N model instances. '
            'Creates a "vis" subdirectory with .svg files and a summary.pdf '
            'in the output path. Use 0 to disable (default: 0).'
        ),
    )

    args = parser.parse_args()

    instantiator = ModelInstantiator(args.spec_path, args.lang_path)
    instantiator.instantiate(args.out_path, args.num_instances)

    if args.visualize > 0:
        visualizer = ModelVisualizer(args.out_path, args.visualize, args.lang_path)
        visualizer.render()


if __name__ == '__main__':
    main()
