"""The bff_soup experiment: run a BffSoupUniverse for a number of epochs,
reporting a minimal, purely descriptive summary at intervals.

This module wires the mechanism (BffSoupUniverse) together with a run
loop; it does not add any selection, fitness, or replication logic of
its own (spec section 3.1/3.2).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from ..analysis import complexity, diversity, entropy
from ..analysis.replication import replication_scores
from ..substrates.bff.universe import BffSoupUniverse
from .base import BffSoupExperimentConfig

DEFAULT_REPLICATION_SCAN_SAMPLE_SIZE = 200


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
    on_replication_scan: Callable[[BffSoupUniverse, np.ndarray, np.ndarray], None] | None = None,
    replication_scan_interval: int | None = None,
    replication_sample_size: int = DEFAULT_REPLICATION_SCAN_SAMPLE_SIZE,
) -> BffSoupUniverse:
    """Run the bff_soup experiment for ``config.epochs`` more epochs.

    ``universe``, if given, is used as the starting point instead of a
    fresh random population -- this is how resuming from a checkpoint
    works (spec section 24): load one with
    ``storage.checkpoints.load_checkpoint`` and pass it in here.

    ``on_replication_scan``, if given, is called every
    ``replication_scan_interval`` epochs with (universe, scores,
    sample_idx) -- a real analysis.replication.replication_scores() scan
    over a deterministic sample of the current population, exactly like
    a sweep's end-of-run scan (see analysis_methods.md), just run
    periodically during a single long run instead of only once at the
    end. This is what lets a run flag "candidate replicator detected at
    epoch N" automatically rather than only via an on-demand scan --
    still purely observational (the callback decides what to do with the
    result; nothing here feeds back into ``universe``).
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
        if (
            on_replication_scan is not None
            and replication_scan_interval
            and universe.epoch % replication_scan_interval == 0
        ):
            population_size = config.universe.population_size
            sample_size = min(replication_sample_size, population_size)
            sample_rng = np.random.default_rng(config.universe.seed ^ universe.epoch)
            sample_idx = sample_rng.choice(population_size, size=sample_size, replace=False)
            scores = replication_scores(
                universe.population[sample_idx],
                seed=config.universe.seed ^ universe.epoch,
                max_steps=config.universe.max_steps,
            )
            on_replication_scan(universe, scores, sample_idx)

    return universe
