/* OilRig scenario - direct 1-to-1 translation, no variability
   coreLang 1.0.0 / org.mal-lang.coreLang */

subsystem SQLServerUnit {
    let sql_server = Application(1);
    let db_backup  = Data(1);
    connect {
        1: sql_server --> [containedData] db_backup;
    }
}

subsystem DomainControllerUnit {
    let domain_controller = Application(1);
}

subsystem ExchangeServerUnit {
    let exchange_server = Application(1);
    let lsass           = Data(1);
    connect {
        1: exchange_server --> [containedData] lsass;
    }
}

subsystem ExchangeAdminUnit {
    let exchange_admin_workstation = Application(1);
    let windows_credential_vault   = Data(1);
    let local_gosta                = Identity(1);
    connect {
        1: exchange_admin_workstation --> [containedData] windows_credential_vault;
        1: local_gosta --> [lowPrivApps]  exchange_admin_workstation;
        1: local_gosta --> [readPrivData] windows_credential_vault;
    }
}

subsystem NetworkSegment {
    let lan      = Network(1);
    let wan      = Network(1);
    let local    = ConnectionRule(1);
    let external = ConnectionRule(1);
    connect {
        1: lan --> [netConnections] local;
        1: wan --> [netConnections] external;
    }
}

let legitimate_user   = User(1);
let gosta_credentials = Credentials(1);
let tous_credentials  = Credentials(1);
let tous              = Identity(1);
let gosta             = Identity(1);
let sql               = SQLServerUnit(1);
let dc                = DomainControllerUnit(1);
let exchange          = ExchangeServerUnit(1);
let admin             = ExchangeAdminUnit(1);
let net               = NetworkSegment(1);

connect {
    1: legitimate_user --> [userIds] admin.local_gosta;

    1: admin.windows_credential_vault --> [information]  gosta_credentials;
    1: gosta_credentials              --> [identities]   admin.local_gosta;
    1: gosta_credentials              --> [identities]   gosta;

    1: exchange.lsass   --> [information]  tous_credentials;
    1: tous_credentials --> [identities]  tous;

    1: tous --> [highPrivApps] sql.sql_server;
    1: tous --> [highPrivApps] exchange.exchange_server;

    1: gosta --> [highPrivApps] exchange.exchange_server;
    1: gosta --> [lowPrivApps]  admin.exchange_admin_workstation;

    1: sql.sql_server                     --> [appConnections] net.local;
    1: dc.domain_controller               --> [appConnections] net.local;
    1: exchange.exchange_server           --> [appConnections] net.local;
    1: admin.exchange_admin_workstation   --> [appConnections] net.local;

    1: exchange.exchange_server           --> [appConnections] net.external;

    1: admin.exchange_admin_workstation   --> [outgoingAppConnections] net.external;
}
