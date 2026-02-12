subsystem HostWithData {
    let host = Host(1);
    let data = Data(Uniform(0, 4));

    connect {
        1: host --> [data] data;
    }
}

let networks = Network(2);
let hosts = HostWithData(10);
let users = User(TruncatedNormal(15, 4));

connect {
    1.0: networks --> [toNetworks] networks;
    0.5: hosts.host --> [networks] networks;
    0.5: users --> [hosts] hosts.host;
}