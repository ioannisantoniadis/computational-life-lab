"""Entropy measurements at three different levels of the population.

These are three genuinely different quantities that are easy to conflate
under the single word "entropy":

- genome-level: how evenly spread is the population across distinct
  64-byte genomes?
- byte-level: how evenly spread are raw byte *values* (0-255) across
  every position of every tape in the population? This mirrors the
  reference cubff implementation's own ``h0`` metric (see
  ``RunSimulation`` in ``common_language.h``).
- instruction-level: how evenly spread are *decoded* BFF operations
  (the ten instructions, NULL, and NOP as one pooled category) across
  the population?

All are Shannon entropy, base 2 (bits), of their respective frequency
distributions. Purely observational (spec section 3.2).
"""

from __future__ import annotations

import numpy as np

from ..substrates.bff.instruction_set import BYTE_TO_OP_TABLE, Op
from .diversity import genome_frequency_counts


def _shannon_entropy(counts: np.ndarray) -> float:
    total = counts.sum()
    if total == 0:
        return 0.0
    proportions = counts[counts > 0] / total
    return float(-np.sum(proportions * np.log2(proportions)))


def shannon_entropy_genomes(population: np.ndarray) -> float:
    """Entropy of the distribution over distinct genomes (bits)."""
    return _shannon_entropy(genome_frequency_counts(population))


def byte_entropy(population: np.ndarray) -> float:
    """Entropy of the raw byte-value distribution (0-255) across every
    position of every genome in the population (bits, max 8.0).
    """
    counts = np.bincount(population.reshape(-1), minlength=256)
    return _shannon_entropy(counts)


def instruction_entropy(population: np.ndarray) -> float:
    """Entropy of the decoded-instruction distribution across the
    population: the ten BFF instructions plus NULL and pooled NOP (bits,
    max log2(12)).
    """
    op_ids = BYTE_TO_OP_TABLE[population.reshape(-1)]
    counts = np.bincount(op_ids, minlength=len(Op))
    return _shannon_entropy(counts)
