"""Population diversity measurements.

These are purely observational: they read a population snapshot and
report a number, never feeding back into simulation dynamics (spec
section 3.2). Every function here operates on a plain ``(n, genome_length)``
uint8 array, so it works identically on a live BffSoupUniverse.population
or on a snapshot loaded from a checkpoint.
"""

from __future__ import annotations

import numpy as np


def genome_frequency_counts(population: np.ndarray) -> np.ndarray:
    """Count of each distinct genome present, in no particular order."""
    if population.ndim != 2:
        raise ValueError("population must be a 2D (n_organisms, genome_length) array")
    _, counts = np.unique(population, axis=0, return_counts=True)
    return counts


def unique_genome_count(population: np.ndarray) -> int:
    return int(len(genome_frequency_counts(population)))


def dominant_genome_frequency(population: np.ndarray) -> float:
    """Fraction of the population occupied by the single most common genome."""
    counts = genome_frequency_counts(population)
    if len(counts) == 0:
        return 0.0
    return float(counts.max()) / population.shape[0]


def simpson_diversity_index(population: np.ndarray) -> float:
    """Simpson's diversity index: 1 - sum(p_i^2) over genome frequencies.

    0 means every organism shares one genome (no diversity); approaches 1
    as genomes become more evenly spread across many distinct values.
    This is a genotype-level diversity measure, distinct from Shannon
    entropy (see analysis.entropy.shannon_entropy_genomes) -- reported
    separately per spec section 14's "genotype diversity" metric, with the
    exact formula documented here since "diversity index" is not a single
    universally agreed-upon quantity.
    """
    counts = genome_frequency_counts(population)
    n = population.shape[0]
    if n == 0:
        return 0.0
    proportions = counts / n
    return float(1.0 - np.sum(proportions**2))
