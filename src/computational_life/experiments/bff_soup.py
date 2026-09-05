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
    universe: BffSoupUniverse | None = None,
    on_checkpoint: Callable[[BffSoupUniverse], None] | None = None,
    checkpoint_interval: int | None = None,
) -> BffSoupUniverse:
    """Run the bff_soup experiment for ``config.epochs`` more epochs.

    ``universe``, if given, is used as the starting point instead of a
    fresh random population -- this is how resuming from a checkpoint
    works (spec section 24): load one with
    ``storage.checkpoints.load_checkpoint`` and pass it in here.
    """
    if universe is None:
        universe = BffSoupUniverse(config.universe)

    if on_report is not None:
        on_report(compute_metrics(universe))

    for _ in range(config.epochs):
        universe.step_epoch()
        if on_report is not None and universe.epoch % config.report_interval == 0:
            on_report(compute_metrics(universe))
        if (
            on_checkpoint is not None
            and checkpoint_interval
            and universe.epoch % checkpoint_interval == 0
        ):
            on_checkpoint(universe)

    return universe
