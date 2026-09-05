"""The bff_soup experiment: run a BffSoupUniverse for a number of epochs,
reporting a minimal, purely descriptive summary at intervals.

This module wires the mechanism (BffSoupUniverse) together with a run
loop; it does not add any selection, fitness, or replication logic of
its own (spec section 3.1/3.2).
"""

from __future__ import annotations

from collections.abc import Callable

from ..analysis import complexity, diversity, entropy
from ..substrates.bff.universe import BffSoupUniverse
from .base import BffSoupExperimentConfig


def compute_metrics(universe: BffSoupUniverse) -> dict:
    """One dashboard/storage-friendly metrics record for the current epoch.

    Shared by the CLI's periodic reporting, SQLite persistence, and the
    Streamlit dashboard, so all three see identical numbers. This is
    still purely observational (spec section 3.2): it only reads
    ``universe.population`` and calls into the analysis layer.
    """
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


def run_bff_soup(
    config: BffSoupExperimentConfig,
    *,
    on_report: Callable[[dict], None] | None = None,
) -> BffSoupUniverse:
    """Run the bff_soup experiment to completion and return the universe."""
    universe = BffSoupUniverse(config.universe)

    if on_report is not None:
        on_report(compute_metrics(universe))

    for _ in range(config.epochs):
        universe.step_epoch()
        if on_report is not None and universe.epoch % config.report_interval == 0:
            on_report(compute_metrics(universe))

    return universe
