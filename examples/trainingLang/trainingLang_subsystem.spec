subsystem NetworkWithHosts {
  let network = Network();
  let hosts   = Host(Uniform(4, 12), notPresent=Uniform(0.7, 1.0));

  connect {
    1: network --> [hosts] hosts;
  }
}

let networks = NetworkWithHosts(Uniform(2, 4));
let users    = User(TruncatedNormal(20, 8), notPresent=Uniform(0.5, 1.0));

connect {
  1.0: networks.network --> [toNetworks] networks.network;
  0.2: users            --> [hosts]      networks.hosts;
}

prune(networks.network);
