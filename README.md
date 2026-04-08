# InstaMal

## Installation

Clone this repository and run the following command in the project root directory:

```
python -m pip install .
```

## Usage

```
$ instamal -h
usage: instamal [-h] -s SPEC_PATH -l LANG_PATH [-n N] [-o OUT_PATH] [-v N]

Generate model instances based on specified domain specifications.

options:
  -h, --help            show this help message and exit
  -s SPEC_PATH, --spec_path SPEC_PATH
                        path to the system domain specification
  -l LANG_PATH, --lang_path LANG_PATH
                        path to the MAL domain-specific language
  -n N, --num_instances N
                        number of model instances to generate (default: 1)
  -o OUT_PATH, --out_path OUT_PATH
                        output path for the generated model instances (default:
                        "models")
  -v N, --visualize N   generate visualizations for the first N model instances.
                        Creates a "vis" subdirectory with .svg files and a summary.pdf
                        in the output path. Use 0 to disable (default: 0).
```

## Specification Language Overview

Use `let` statements to create variables containing sets of assets.

```
let networks = Network(2);
let hosts    = Host(10);
```

Add variability using any of [the supported distributions](src/instamal/instantiator/helpers/distributions.py).

```
let users = User(TruncatedNormal(15, 4));
let data  = Data(8+Uniform(7-9, 2*2));
```

Use `param` to declare named values that can be referenced in expressions. A `param =` evaluates its expression once per model instance and reuses that value everywhere the name appears. A `param ~` re-evaluates its expression each time the name is used, drawing a fresh sample on every reference.

```
param numNetworks     = 3;
param hostsPerNetwork ~ TruncatedNormal(8, 2);

let networks = Network(numNetworks);
let hosts    = Host(hostsPerNetwork);
```

Add associations between specified assets using `connect` clauses, each containing a list of connection rules.

```
connect {
  1.0: networks --> [toNetworks] networks;
  0.5: hosts    --> [networks]   networks;
  0.5: users    --> [hosts]      hosts;
  0.7: data     --> [hosts]      hosts;
}
```

Each connection rule takes the form `<weight>: <left_asset_set> --> [<fieldname>] <right_asset_set>`. The `weight` is in range [0, 1]. A `weight` of `1` creates the specified association from each asset in the left asset set to all other assets in the right asset set, while `weight` of `0` creates no associations at all. The higher weight and the more assets in the sets, the more likely associations are to form.

---

Define named `subsystem`s to instantiate later.

```
subsystem NetworkWithHosts {
  let network = Network();            // NetworkWithHosts.network
  let hosts   = Host(Uniform(4, 12)); // NetworkWithHosts.hosts

  connect {
    1: network --> [hosts] hosts;
  }
}
```

Access all variables defined within the subset using the `.` access syntax. This way you can use assets belonging to a set of subsystems within `connect` clauses.

```
let networks = NetworkWithHosts(Uniform(2, 4));
let users    = User(TruncatedNormal(20, 8));

connect {
  0.2: users            --> [hosts]      networks.hosts;
  1.0: networks.network --> [toNetworks] networks.network;
}
```

In the above example, the `networks` variable holds a collection of instantiated `NetworkWithHosts` subsystems. `networks.hosts` accesses the union of all `NetworkWithHosts.hosts` assets in `networks`. The `connect` clause thus contains a rule to connect users to the hosts on the networks, and a rule to connect all networks.

---

Use `prune` at the end of the specification to remove disconnected assets after wiring.

```
prune;
```

With no arguments, `prune` retains only the assets in the largest connected component of the model graph, discarding all isolated assets and smaller disconnected fragments. This is useful when connection rules are probabilistic and you want to guarantee that the generated model is a single coherent network.

```
prune(data, networks.network);
```

With arguments, each argument must be a declared asset set or a subsystem member access. A connected component is retained if and only if it contains at least one asset from any of the supplied sets, while components with no overlap are discarded. This lets you anchor the model around a known structural core while pruning isolated fragments.

---

Assign defense values to assets on instantiation by supplying named defense controls after the asset count.

```
let hosts = Host(5, notPresent=0.8);
```

Each defense control takes the form `<defenseName>=<expr>` where `expr` evaluates to a Bernoulli probability in `[0, 1]`. Values outside this range are clamped automatically. Defense names must match defenses defined on the asset type in the DSL. Multiple defenses can be set in a single instantiation, separated by commas.

```
param pNotPresent ~ Uniform(0.6, 1.0);

let hosts = Host(Uniform(4, 12), notPresent=pNotPresent);
```

Defense controls can appear on any asset instantiation, including those inside subsystem bodies, and expressions may reference any previously declared `param`.