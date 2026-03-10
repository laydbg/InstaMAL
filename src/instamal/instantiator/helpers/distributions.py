import random
import math


def bernoulli(p):
    """Generate a sample from a Bernoulli distribution with probability p."""
    return 1 if random.random() < p else 0


def binomial(n, p):
    """Generate a sample from a Binomial distribution with n trials and probability p."""
    return sum(bernoulli(p) for _ in range(int(n)))


def exponential(lam):
    """Generate a sample from an Exponential distribution with rate lambda."""
    return random.expovariate(lam)


def gamma(k, theta):
    """Generate a sample from a Gamma distribution with shape k and scale theta."""
    return random.gammavariate(k, theta)


def lognormal(mu, sigma):
    """Generate a sample from a Log-Normal distribution given mu and sigma."""
    return random.lognormvariate(mu, sigma)


def pareto(x_m, alpha):
    """Generate a sample from a Pareto distribution with scale x_m and shape alpha."""
    return x_m / (random.random() ** (1 / alpha))


def truncated_normal(mu, sigma):
    """Generate a sample from a Truncated Normal distribution between 0 and infinity."""
    while True:
        sample = random.normalvariate(mu, sigma)
        if sample >= 0:
            return sample


def uniform(a, b):
    """Generate a sample from a Uniform distribution between a and b."""
    return random.uniform(a, b)


# Practical upper bound for distributions with no finite maximum.
PRACTICAL_MAX = 10000


def bernoulli_bounds(p: float) -> tuple[int, int]:
    """Bernoulli(p) in {0, 1}."""
    lo = 0 if p < 1.0 else 1
    hi = 1 if p > 0.0 else 0
    return lo, hi


def binomial_bounds(n: float, p: float) -> tuple[int, int]:
    """Binomial(n, p) in [0, floor(n)]."""
    n_int = math.floor(n)
    lo = 0 if p < 1.0 else n_int
    hi = n_int if p > 0.0 else 0
    return lo, hi


def exponential_bounds(lam: float) -> tuple[int, int]:
    """Exponential on (0, inf); floor in [0, PRACTICAL_MAX]."""
    return 0, PRACTICAL_MAX


def gamma_bounds(k: float, theta: float) -> tuple[int, int]:
    """Gamma on (0, inf); floor in [0, PRACTICAL_MAX]."""
    return 0, PRACTICAL_MAX


def lognormal_bounds(mu: float, sigma: float) -> tuple[int, int]:
    """LogNormal on (0, inf); floor in [0, PRACTICAL_MAX]."""
    return 0, PRACTICAL_MAX


def pareto_bounds(x_m: float, alpha: float) -> tuple[int, int]:
    """Pareto on [x_m, inf); floor in [floor(x_m), PRACTICAL_MAX]."""
    return math.floor(x_m), PRACTICAL_MAX


def truncated_normal_bounds(mu: float, sigma: float) -> tuple[int, int]:
    """TruncatedNormal on [0, inf); floor in [0, PRACTICAL_MAX]."""
    return 0, PRACTICAL_MAX


def uniform_bounds(a: float, b: float) -> tuple[int, int]:
    """Uniform(a, b); floor in [floor(a), floor(b)]."""
    return math.floor(a), math.floor(b)


distribution_functions = {
    "Bernoulli": bernoulli,
    "Binomial": binomial,
    "Exponential": exponential,
    "Gamma": gamma,
    "LogNormal": lognormal,
    "Pareto": pareto,
    "TruncatedNormal": truncated_normal,
    "Uniform": uniform,
}

distribution_bounds_functions = {
    "Bernoulli": bernoulli_bounds,
    "Binomial": binomial_bounds,
    "Exponential": exponential_bounds,
    "Gamma": gamma_bounds,
    "LogNormal": lognormal_bounds,
    "Pareto": pareto_bounds,
    "TruncatedNormal": truncated_normal_bounds,
    "Uniform": uniform_bounds,
}
