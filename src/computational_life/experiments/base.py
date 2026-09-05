"""Loading experiment configuration from YAML (spec section 20).

Every experiment must be reproducible from (configuration, seed): this
module is the single place that turns a YAML file into the typed config
objects the substrates consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..substrates.bff.universe import BffSoupConfig


@dataclass(frozen=True)
class BffSoupExperimentConfig:
    """A parsed experiment configuration for the bff_soup experiment."""

    name: str
    seed: int
    universe: BffSoupConfig
    epochs: int
    report_interval: int


def parse_bff_soup_config(raw: dict) -> BffSoupExperimentConfig:
    """Turn an already-loaded raw config dict into a typed config.

    Shared by :func:`load_bff_soup_config` (one YAML file, one run) and
    ``experiments.sweep`` (one base dict, many per-point overrides) so
    both go through identical parsing/defaulting logic.
    """
    if raw.get("experiment") != "bff_soup":
        raise ValueError(f"Expected experiment: bff_soup, got {raw.get('experiment')!r}")

    seed = int(raw["seed"])
    population = raw.get("population", {})
    execution = raw.get("execution", {})
    mutation = raw.get("mutation", {})
    run = raw.get("run", {})

    universe_config = BffSoupConfig(
        population_size=int(population.get("size", 131_072)),
        genome_length=int(population.get("genome_length", 64)),
        max_steps=int(execution.get("max_steps", 8192)),
        mutation_enabled=bool(mutation.get("enabled", False)),
        mutation_rate=float(mutation.get("rate", 0.0)),
        head_init=str(execution.get("head_init", "zero")),
        seed=seed,
    )

    return BffSoupExperimentConfig(
        name=raw.get("name", "bff_soup"),
        seed=seed,
        universe=universe_config,
        epochs=int(run.get("epochs", 1000)),
        report_interval=int(run.get("report_interval", 100)),
    )


def load_bff_soup_config(path: str | Path) -> BffSoupExperimentConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    try:
        return parse_bff_soup_config(raw)
    except ValueError as exc:
        raise ValueError(f"{exc} (in {path})") from exc
