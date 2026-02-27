# InstaMal

## Installation

Clone this repository and run the following command in the project root directory:

```
python -m pip install .
```

## Usage

```
$ instamal --help
usage: instamal [-h] -s SPEC_PATH -l LANG_PATH [-n NUM_INSTANCES] [-o OUT_PATH]

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

---

Define named `subsystem`s to instantiate later.

```
subsystem NetworkWithHosts {
    let network = Network();            // NetworkWithHosts.network
    let hosts = Host(Uniform(4, 12));   // NetworkWithHosts.hosts

    connect {
        1: network --> [hosts] hosts;
    }
}
```

Access all variables defined within the subset using the `.` access syntax. This way you can use assets belonging to a set of subsystems within `connect` clauses.

```
let networks = NetworkWithHosts(Uniform(2, 4));
let users = User(TruncatedNormal(20, 8));

connect {
    0.2: users --> [hosts] networks.hosts;
    1.0: networks.network --> [toNetworks] networks.network;
}
```

In the above example, the `networks` variable holds a collection of instantiated `NetworkWithHosts` subsystems. `networks.hosts` accesses the union of all `NetworkWithHosts.hosts` assets in `networks`. The `connect` clause thus contains a rule to connect users to the hosts on the networks, and a rule to connect all networks.
