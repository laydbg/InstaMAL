subsystem HostWithData {
    let host = Host();
    let users = User(Uniform(1, 3));
    let data = Data();
    connect {
        1: host --> [data] data;
        1: host --> [users] users;
    }
}

subsystem NetworkWithHosts {
    let network = Network();
    let hosts = HostWithData(TruncatedNormal(8, 3));
    connect {
        1: network --> [hosts] hosts.host;
    }
}

let networks = NetworkWithHosts(1+Binomial(7, 0.03));

connect {
    1: networks.network --> [toNetworks] networks.network;
}