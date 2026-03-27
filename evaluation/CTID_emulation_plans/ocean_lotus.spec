/* Ocean Lotus scenario - direct 1-to-1 translation, no variability
   coreLang 1.0.0 / org.mal-lang.coreLang */

subsystem MacWorkstation {
    let macos_workstation = Application(1);
    let hpotter_mac       = Identity(1);
    let ssh               = Data(1);        // .ssh
    connect {
        1: macos_workstation --> [containedData] ssh;
        1: hpotter_mac       --> [readPrivData]  ssh;
        1: hpotter_mac       --> [lowPrivApps]   macos_workstation;
    }
}

subsystem LinuxServerUnit {
    let linux_server  = Application(1);
    let hpotter_linux = Identity(1);
    let pdf_files     = Data(1);
    connect {
        1: linux_server  --> [containedData] pdf_files;
        1: hpotter_linux --> [readPrivData]  pdf_files;
        1: hpotter_linux --> [lowPrivApps]   linux_server;
    }
}

subsystem NetworkSegment {
    let lan      = Network(1);
    let wan      = Network(1);
    let local    = ConnectionRule(1);
    let outbound = ConnectionRule(1);
    connect {
        1: lan --> [netConnections] local;
        1: wan --> [netConnections] outbound;
    }
}

let hope_potter = User(1);
let id_rsa      = Credentials(1);
let mac         = MacWorkstation(1);
let linux       = LinuxServerUnit(1);
let net         = NetworkSegment(1);

connect {
    1: hope_potter --> [userIds] mac.hpotter_mac;

    1: mac.ssh --> [information] id_rsa;
    1: id_rsa  --> [identities]  linux.hpotter_linux;

    1: mac.macos_workstation --> [appConnections] net.local;
    1: linux.linux_server    --> [appConnections] net.local;

    1: mac.macos_workstation --> [outgoingAppConnections] net.outbound;
    1: linux.linux_server    --> [outgoingAppConnections] net.outbound;
}
