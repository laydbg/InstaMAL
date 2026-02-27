# InstaMal

## Installation

Clone this repository and run the following command in the project root directory:

```
python -m pip install .
```

## Usage

```
$ instamal -h
usage: instamal [-h] -s SPEC_PATH -l LANG_PATH [-n NUM_INSTANCES] [-o OUT_PATH] [-v VISUALIZE]

Generate model instances based on specified domain specifications.

options:
  -h, --help            show this help message and exit
  -s SPEC_PATH, --spec_path SPEC_PATH
                        path to the system domain specification
  -l LANG_PATH, --lang_path LANG_PATH
                        path to the MAL domain-specific language
  -n NUM_INSTANCES, --num_instances NUM_INSTANCES
                        number of model instances to generate (default: 1)
  -o OUT_PATH, --out_path OUT_PATH
                        output path for the generated model instances (default: "models")
  -v VISUALIZE, --visualize VISUALIZE
                        Generate visualizations for the first n model instances. Creates a "vis" directory with .png files
                        and a `visualization_summary.md` in the output path. Use -v 0 to disable (default: 0).
```

## Specification Language Overview

Use `let` statements to create variables containing sets of assets.

```
let networks = Network(2);
let hosts = Host(10);
```

Add variability using any of [the supported distributions](/instamal/instantiator/helpers/distributions.py).

```
let users = User(TruncatedNormal(15, 4));
let data = Data(8+Uniform(7-9, 2*2));
```

Add associations between specified assets using `connect` clauses, each containing a list of connection rules.

```
connect {
    1.0: networks --> [toNetworks] networks;
    0.5: hosts --> [networks] networks;
    0.5: users --> [hosts] hosts;
    0.7: data --> [hosts] hosts;
}
```

Each connection rule takes the form `<weight>: <left_asset_set> --> [<fieldname>] <right_asset_set>`. The `weight` is in range [0, 1]. A `weight` of `1` creates the specified association from each asset in the left asset set to all other assets in the right asset set, while `weight` of `0` creates no associations at all. The higher weight and the more assets in the sets, the more likely associations are to form.
