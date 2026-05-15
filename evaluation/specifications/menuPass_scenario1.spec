param numWorkstations         = 1 + TruncatedNormal(1, 0.7); // >=1
param numServers              = 1 + TruncatedNormal(1, 0.5); // >=1

param pMachineHasLocalAdmin   = 0.1;
param pMachineHasLsass        = 0.1;
param pMachineStoresDACreds   = 0.2;

param pMgmtHostExists         = 0.8;
param pMgmtHostStoresMspCreds = 0.6;

param pVpnExists              = 0.3;
param pVpnIsRestricted        = 0.98;
param wWanReachableServer     = 0.3;
param wVpnReachableServer     = 0.7;

// === R3, R7, R4 ===

subsystem ServerStandard {
    let machine          = Application(1);
    let sam              = Data(1);
    let userIdentity     = Identity(1);
    let userCreds        = Credentials(1);
    let hashedCredsLocal = Credentials(1);  // hash stored in local SAM
    let hashedCredsDC    = Credentials(1);  // hash stored in NTDS.dit

    let hashedDACreds    = Credentials(Bernoulli(pMachineStoresDACreds)); // For R6

    connect {
        // SAM and credential hash chain
        1: sam              --> [containingApp] machine;
        1: hashedCredsLocal --> [containerData] sam;
        1: userCreds        --> [identities]    userIdentity;
        1: hashedCredsLocal --> [origCreds]     userCreds;
        1: userIdentity     --> [lowPrivApps]   machine;      // Low privilege
        1: hashedCredsDC    --> [origCreds]     userCreds;

        // Association is only formed when hash exists
        1: hashedDACreds --> [containerData] sam;             // For R6
    }
}

subsystem ServerLocalAdmin {
    let machine          = Application(1);
    let sam              = Data(1);
    let userIdentity     = Identity(1);
    let userCreds        = Credentials(1);
    let hashedCredsLocal = Credentials(1);
    let hashedCredsDC    = Credentials(1);

    let hashedDACreds    = Credentials(Bernoulli(pMachineStoresDACreds));

    connect {
        1: sam              --> [containingApp] machine;
        1: hashedCredsLocal --> [containerData] sam;
        1: userCreds        --> [identities]    userIdentity;
        1: hashedCredsLocal --> [origCreds]     userCreds;
        1: userIdentity     --> [highPrivApps]  machine;      // Local admin
        1: hashedCredsDC    --> [origCreds]     userCreds;

        1: hashedDACreds --> [containerData] sam;
    }
}

subsystem WorkstationStandard {
    let machine          = Application(1);
    let sam              = Data(1);
    let lsass            = Data(Bernoulli(pMachineHasLsass));  // Probabilistic LSASS
    let userIdentity     = Identity(1);
    let userCreds        = Credentials(1);
    let hashedCredsLocal = Credentials(1);
    let hashedCredsDC    = Credentials(1);

    let hashedDACreds    = Credentials(Bernoulli(pMachineStoresDACreds));

    connect {
        // SAM always exists
        1: sam              --> [containingApp] machine;
        1: hashedCredsLocal --> [containerData] sam;
        1: userCreds        --> [identities]    userIdentity;
        1: hashedCredsLocal --> [origCreds]     userCreds;
        1: userIdentity     --> [lowPrivApps]   machine;
        1: hashedCredsDC    --> [origCreds]     userCreds;

        // LSASS associations only form when LSASS is present
        1: lsass --> [containingApp] machine;
        1: lsass --> [information]   userCreds;

        1: hashedDACreds --> [containerData] sam;
    }
}

subsystem WorkstationLocalAdmin {
    let machine          = Application(1);
    let sam              = Data(1);
    let lsass            = Data(Bernoulli(pMachineHasLsass));  // Probabilistic LSASS
    let userIdentity     = Identity(1);
    let userCreds        = Credentials(1);
    let hashedCredsLocal = Credentials(1);
    let hashedCredsDC    = Credentials(1);

    let hashedDACreds    = Credentials(Bernoulli(pMachineStoresDACreds));

    connect {
        1: sam              --> [containingApp] machine;
        1: hashedCredsLocal --> [containerData] sam;
        1: userCreds        --> [identities]    userIdentity;
        1: hashedCredsLocal --> [origCreds]     userCreds;
        1: userIdentity     --> [highPrivApps]  machine;
        1: hashedCredsDC    --> [origCreds]     userCreds;

        1: lsass --> [containingApp] machine;
        1: lsass --> [information]   userCreds;

        1: hashedDACreds --> [containerData] sam;
    }
}

subsystem WorkstationStandardLSASS {
    let machine          = Application(1);
    let sam              = Data(1);
    let lsass            = Data(1);         // Always LSASS
    let userIdentity     = Identity(1);
    let userCreds        = Credentials(1);
    let hashedCredsLocal = Credentials(1);
    let hashedCredsDC    = Credentials(1);

    let hashedDACreds    = Credentials(Bernoulli(pMachineStoresDACreds));

    connect {
        1: sam              --> [containingApp] machine;
        1: hashedCredsLocal --> [containerData] sam;
        1: userCreds        --> [identities]    userIdentity;
        1: hashedCredsLocal --> [origCreds]     userCreds;
        1: userIdentity     --> [lowPrivApps]   machine;
        1: hashedCredsDC    --> [origCreds]     userCreds;

        1: lsass --> [containingApp] machine;
        1: lsass --> [information]   userCreds;

        1: hashedDACreds --> [containerData] sam;
    }
}

subsystem WorkstationLocalAdminLSASS {
    let machine          = Application(1);
    let sam              = Data(1);
    let lsass            = Data(1);         // Always LSASS
    let userIdentity     = Identity(1);
    let userCreds        = Credentials(1);
    let hashedCredsLocal = Credentials(1);
    let hashedCredsDC    = Credentials(1);

    let hashedDACreds    = Credentials(Bernoulli(pMachineStoresDACreds));

    connect {
        1: sam              --> [containingApp] machine;
        1: hashedCredsLocal --> [containerData] sam;
        1: userCreds        --> [identities]    userIdentity;
        1: hashedCredsLocal --> [origCreds]     userCreds;
        1: userIdentity     --> [highPrivApps]  machine;
        1: hashedCredsDC    --> [origCreds]     userCreds;

        1: lsass --> [containingApp] machine;
        1: lsass --> [information]   userCreds;

        1: hashedDACreds --> [containerData] sam;
    }
}

param lsassHostIsLocalAdmin = Bernoulli(pMachineHasLocalAdmin);
param numAdditionalHosts    = numWorkstations - 1;
param numWorkstationsAdm    = Binomial(numAdditionalHosts, pMachineHasLocalAdmin);
param numWorkstationsStd    = numAdditionalHosts - numWorkstationsAdm;
let hostLsassStd = WorkstationStandardLSASS(1-lsassHostIsLocalAdmin); // Either standard or local admin,
let hostLsassAdm = WorkstationLocalAdminLSASS(lsassHostIsLocalAdmin); // never both.
let hostsStd     = WorkstationStandard(numWorkstationsStd);
let hostsAdm     = WorkstationLocalAdmin(numWorkstationsAdm);

param numServersAdm = Binomial(numServers, pMachineHasLocalAdmin);
param numServersStd = numServers - numServersAdm;
let serversStd = ServerStandard(numServersStd);
let serversAdm = ServerLocalAdmin(numServersAdm);

// === R1, R9, R2 ===

let dc                     = Application(1);
let ntdsDit                = Data(1);
let domainAdmin            = Identity(1);
let domainAdminCreds       = Credentials(1);
let hashedDomainAdminCreds = Credentials(1);

connect {
    1: ntdsDit                --> [containingApp] dc;
    1: hashedDomainAdminCreds --> [containerData] ntdsDit;
    1: domainAdminCreds       --> [identities]    domainAdmin;
    1: hashedDomainAdminCreds --> [origCreds]     domainAdminCreds;
    1: domainAdmin            --> [highPrivApps]  dc;

    1: ntdsDit --> [information] hostLsassStd.hashedCredsDC;
    1: ntdsDit --> [information] hostLsassAdm.hashedCredsDC;
    1: ntdsDit --> [information] hostsStd.hashedCredsDC;
    1: ntdsDit --> [information] hostsAdm.hashedCredsDC;
    1: ntdsDit --> [information] serversStd.hashedCredsDC;
    1: ntdsDit --> [information] serversAdm.hashedCredsDC;
}


param mgmtHostExists         = Bernoulli(pMgmtHostExists);
param mgmtHostStoresMspCreds = Bernoulli(pMgmtHostStoresMspCreds);

subsystem ManagementHost {
    let machine          = Application(mgmtHostExists);
    let sam              = Data(mgmtHostExists*mgmtHostStoresMspCreds);
    let mspAdmin         = Identity(1);
    let mspAdminCreds    = Credentials(1);
    let hashedCredsLocal = Credentials(mgmtHostExists*mgmtHostStoresMspCreds);
    let hashedCredsDC    = Credentials(1);

    connect {
        1: sam              --> [containingApp] machine;
        1: hashedCredsLocal --> [containerData] sam;
        1: mspAdminCreds    --> [identities]    mspAdmin;
        1: hashedCredsLocal --> [origCreds]     mspAdminCreds;
        1: mspAdmin         --> [highPrivApps]  machine;
        1: hashedCredsDC    --> [origCreds]     mspAdminCreds;
    }
}

let mgmtHost = ManagementHost(1);

connect {
    1: mgmtHost.hashedCredsDC --> [containerData] ntdsDit;

    1: mgmtHost.mspAdmin --> [highPrivApps] dc;
    1: mgmtHost.mspAdmin --> [highPrivApps] hostLsassStd.machine;
    1: mgmtHost.mspAdmin --> [highPrivApps] hostLsassAdm.machine;
    1: mgmtHost.mspAdmin --> [highPrivApps] hostsStd.machine;
    1: mgmtHost.mspAdmin --> [highPrivApps] hostsAdm.machine;
    1: mgmtHost.mspAdmin --> [highPrivApps] serversStd.machine;
    1: mgmtHost.mspAdmin --> [highPrivApps] serversAdm.machine;
}

// === R6 ===

connect {
    // Only forms associations when the hashes exist on the machines
    1: domainAdminCreds --> [hashes] hostLsassStd.hashedDACreds;
    1: domainAdminCreds --> [hashes] hostLsassAdm.hashedDACreds;
    1: domainAdminCreds --> [hashes] hostsStd.hashedDACreds;
    1: domainAdminCreds --> [hashes] hostsAdm.hashedDACreds;
    1: domainAdminCreds --> [hashes] serversStd.hashedDACreds;
    1: domainAdminCreds --> [hashes] serversAdm.hashedDACreds;
}

// === R5, R8 ===

let wan         = Network(1);
let wanOutbound = ConnectionRule(1);
let wanInbound  = ConnectionRule(1);

let msp       = Network(1);
let localMesh = ConnectionRule(1);

param vpnExists = Bernoulli(pVpnExists);
let vpn        = Network(vpnExists);
let vpnInbound = ConnectionRule(vpnExists);
let wanToVpn   = ConnectionRule(vpnExists, restricted=pVpnIsRestricted);

connect { // vpn
    1: msp --> [netConnections] localMesh;
    // All machines have bidirectional connections on local network
    1: localMesh --> [applications] dc;
    1: localMesh --> [applications] mgmtHost.machine;
    1: localMesh --> [applications] hostLsassStd.machine;
    1: localMesh --> [applications] hostLsassAdm.machine;
    1: localMesh --> [applications] hostsStd.machine;
    1: localMesh --> [applications] hostsAdm.machine;
    1: localMesh --> [applications] serversStd.machine;
    1: localMesh --> [applications] serversAdm.machine;

    1: wan --> [netConnections] wanOutbound;
    1: wan --> [netConnections] wanInbound;
    // All workstations have outboud connections to the external network
    1: wanOutbound --> [outApplications] hostLsassStd.machine;
    1: wanOutbound --> [outApplications] hostLsassAdm.machine;
    1: wanOutbound --> [outApplications] hostsStd.machine;
    1: wanOutbound --> [outApplications] hostsAdm.machine;

    // Some servers have inbound connection from the external network
    wWanReachableServer: wanInbound --> [inApplications] serversStd.machine;
    wWanReachableServer: wanInbound --> [inApplications] serversAdm.machine;

    1: wan --> [outgoingNetConnections] wanToVpn;
    1: vpn --> [ingoingNetConnections]  wanToVpn;
    1: vpn --> [netConnections]          vpnInbound;
    // Some servers have inbound connection from the vpn (when present)
    wVpnReachableServer: vpnInbound --> [inApplications] serversStd.machine;
    wVpnReachableServer: vpnInbound --> [inApplications] serversAdm.machine;
}
