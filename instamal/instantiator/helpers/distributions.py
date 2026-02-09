import random


def bernoulli(p):
    """Generate a sample from a Bernoulli distribution with probability p."""
    return 1 if random.random() < p else 0


def binomial(n, p):
    """Generate a sample from a Binomial distribution with n trials and probability p."""
    return sum(bernoulli(p) for _ in range(n))


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
        if 0 <= sample:
            return sample


def uniform(a, b):
    """Generate a sample from a Uniform distribution between a and b."""
    return random.uniform(a, b)
