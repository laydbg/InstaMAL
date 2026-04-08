// Enterprise network model

// Global parameters

param numSites     = Binomial(4, 0.7);      // Number of office sites, sampled once
param usersPerHost ~ TruncatedNormal(3, 1); // Resampled for each host group
param dataPerHost  ~ Uniform(2, 8);         // Resampled for each host group

// Defense posture parameters

param serverHardening      ~ Uniform(0.8, 1.0); // Servers are well-maintained
param workstationHardening ~ Uniform(0.5, 0.9); // Workstations vary more

// Subsystem definitions

subsystem HostGroup {
  let host  = Host(1,            notPresent=serverHardening);
  let users = User(usersPerHost, notPresent=Uniform(0.6, 1.0));
  let data  = Data(dataPerHost,  notPresent=Uniform(0.7, 1.0));

  connect {
    1: host --> [users] users;
    1: host --> [data]  data;
  }
}

subsystem Office {
  let externalNetwork = Network();
  let internalNetwork = Network();
  let servers         = HostGroup(TruncatedNormal(5, 2));
  let workstations    = HostGroup(TruncatedNormal(12, 4));

  connect {
    1:   externalNetwork   --> [toNetworks] internalNetwork;
    1:   servers.host      --> [networks]   internalNetwork;
    1:   workstations.host --> [networks]   internalNetwork;
    0.3: servers.host      --> [networks]   externalNetwork;
  }
}

// Top-level instantiation

let sites = Office(numSites);

// All internal networks are partially interconnected across sites
connect {
  0.4: sites.internalNetwork --> [toNetworks] sites.internalNetwork;
}

// A small pool of external users can reach exposed servers across all sites
let externalUsers = User(TruncatedNormal(8, 3));
connect {
  0.2: externalUsers --> [hosts] sites.servers.host;
}

// Do not retain lone external users in the model
prune(sites.internalNetwork);
