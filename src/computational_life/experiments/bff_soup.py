"""The bff_soup experiment: run a BffSoupUniverse for a number of epochs,
reporting a minimal, purely descriptive summary at intervals.

This module wires the mechanism (BffSoupUniverse) together with a run
loop; it does not add any selection, fitness, or replication logic of
its own (spec section 3.1/3.2).
"""

from __future__ import annotations

from collections.abc import Callable

from ..substrates.bff.universe import BffSoupUniverse
from .base import BffSoupExperimentConfig


def run_bff_soup(
    config: BffSoupExperimentConfig,
    *,
    on_report: Callable[[dict], None] | None = None,
) -> BffSoupUniverse:
    """Run the bff_soup experiment to completion and return the universe."""
    universe = BffSoupUniverse(config.universe)

    if on_report is not None:
        on_report(universe.summary())

    for _ in range(config.epochs):
        universe.step_epoch()
        if on_report is not None and universe.epoch % config.report_interval == 0:
            on_report(universe.summary())

    return universe
