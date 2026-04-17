let networks = Network(2);
let hosts    = Host(10);
let users    = User(TruncatedNormal(15, 4)); // Use distributions for variability in asset numbers
let data     = Data(8+Uniform(7-9, 2*2));    // Expressions are evaluated as expected

connect {
  1.0: networks --> [toNetworks] networks;
  0.5: hosts    --> [networks]   networks;
  0.5: users    --> [hosts]      hosts;
  0.7: data     --> [hosts]      hosts;
}

prune; // Retain only the giant component

/*
 * If some asset sets will not be reused you could equivalently choose to instantiate
 * them in the connect clause directly, like so:
 * 
 * 
 * let networks = Network(2);
 * let hosts    = Host(10);
 *
 * connect {
 *   1.0: networks                     --> [toNetworks] networks;
 *   0.5: hosts                        --> [networks]   networks;
 *   0.5: User(TruncatedNormal(15, 4)) --> [hosts]      hosts;
 *   0.7: Data(8+Uniform(7-9, 2*2))    --> [hosts]      hosts;
 * }
 *
 * prune;
 *
 */
