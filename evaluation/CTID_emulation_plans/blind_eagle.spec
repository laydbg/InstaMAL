/* Blind Eagle scenario - direct 1-to-1 translation, no variability
   coreLang 1.0.0 / org.mal-lang.coreLang */

subsystem Workstation {
    let windows_workstation = Hardware(1);
    let windows_10_os       = Application(1);
    let user_account        = Identity(1);
    connect {
        1: windows_workstation --> [sysExecutedApps] windows_10_os;
        1: user_account        --> [lowPrivApps]     windows_10_os;
    }
}

subsystem BrowserSession {
    let edge_browser             = Application(1);
    let browser_credential_store = Data(1);
    let bank_credentials         = Credentials(1);
    connect {
        1: edge_browser             --> [containedData] browser_credential_store;
        1: browser_credential_store --> [information]   bank_credentials;
    }
}

subsystem LANSegment {
    let lan = Network(1);
    let cr  = ConnectionRule(1);
    connect {
        1: lan --> [netConnections] cr;
    }
}

let user            = User(1);
let workstation     = Workstation(1);
let browser_session = BrowserSession(1);
let lan_segment     = LANSegment(1);

connect {
    1: user --> [userIds] workstation.user_account;

    1: workstation.windows_10_os --> [appExecutedApps] browser_session.edge_browser;

    1: workstation.user_account --> [lowPrivApps]   browser_session.edge_browser;
    1: workstation.user_account --> [readPrivData]  browser_session.browser_credential_store;
    1: workstation.user_account --> [writePrivData] browser_session.browser_credential_store;

    1: workstation.windows_10_os    --> [outgoingAppConnections] lan_segment.cr;
    1: browser_session.edge_browser --> [outgoingAppConnections] lan_segment.cr;
}
