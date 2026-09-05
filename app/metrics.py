"""Assembles one dashboard-friendly metrics record per snapshot.

This is UI glue, not analysis: it just calls into
computational_life.analysis and computational_life.substrates and
flattens the results into one dict per epoch for a history table. All
the actual computation lives in the analysis layer.
"""

from __future__ import annotations

from computational_life.analysis import complexity, diversity, entropy
from computational_life.substrates.bff.universe import BffSoupUniverse


def compute_metrics_record(universe: BffSoupUniverse) -> dict:
    population = universe.population
    return {
        "epoch": universe.epoch,
        "unique_genomes": diversity.unique_genome_count(population),
        "dominant_genome_frequency": diversity.dominant_genome_frequency(population),
        "simpson_diversity": diversity.simpson_diversity_index(population),
        "genome_entropy_bits": entropy.shannon_entropy_genomes(population),
        "byte_entropy_bits": entropy.byte_entropy(population),
        "instruction_entropy_bits": entropy.instruction_entropy(population),
        "compressed_bits_per_byte": complexity.compressed_bits_per_byte(population),
        "structural_redundancy_bits": complexity.structural_redundancy(population),
    }
