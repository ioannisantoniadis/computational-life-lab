"""Parameter sweeps: run many independent (parameter combination x seed)
points and store every result, so questions like "P(replicator |
population size)" can be answered from real data with an honest sample
size (spec section 22) rather than eyeballed from a single run.

Each sweep point is executed exactly like a normal bff_soup run (same
run_bff_soup, same metrics), so sweep results are directly comparable to
single-run results. At the end of each point's run, a real replication
scan (analysis.replication.replication_scores -- the same method used
for the paper's own reported statistics) is taken over a sample of the
final population; this is what actually answers "did a candidate
replicator emerge here," rather than a cheaper proxy standing in for it.
"""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from ..analysis.replication import DEFAULT_NUM_TRIALS, classify, replication_scores
from ..storage.database import RunStore
from .base import BffSoupExperimentConfig, parse_bff_soup_config
from .bff_soup import run_bff_soup

DEFAULT_REPLICATION_SAMPLE_SIZE = 200


@dataclass(frozen=True)
class SweepPoint:
    overrides: dict
    config: BffSoupExperimentConfig


@dataclass(frozen=True)
class SweepConfig:
    name: str
    base_raw: dict
    sweep_params: dict[str, list]
    seeds: list[int]

    def points(self) -> list[SweepPoint]:
        keys = list(self.sweep_params)
        value_lists = [self.sweep_params[k] for k in keys]
        combos = list(itertools.product(*value_lists)) if keys else [()]

        result = []
        for combo in combos:
            combo_overrides = dict(zip(keys, combo))
            for seed in self.seeds:
                raw = copy.deepcopy(self.base_raw)
                raw.setdefault("experiment", "bff_soup")
                for dotted_key, value in combo_overrides.items():
                    _set_dotted(raw, dotted_key, value)
                raw["seed"] = seed
                overrides = dict(combo_overrides, seed=seed)
                result.append(SweepPoint(overrides=overrides, config=parse_bff_soup_config(raw)))
        return result


def _set_dotted(raw: dict, dotted_key: str, value) -> None:
    parts = dotted_key.split(".")
    cursor = raw
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def load_sweep_config(path: str | Path) -> SweepConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw.get("experiment") != "bff_soup_sweep":
        raise ValueError(
            f"Expected experiment: bff_soup_sweep in {path}, got {raw.get('experiment')!r}"
        )

    base_raw = dict(raw.get("base", {}))

    seeds_spec = raw.get("seeds", {"count": 1})
    if "list" in seeds_spec:
        seeds = [int(s) for s in seeds_spec["list"]]
    else:
        start = int(seeds_spec.get("start", 0))
        count = int(seeds_spec.get("count", 1))
        seeds = list(range(start, start + count))

    return SweepConfig(
        name=raw.get("name", "sweep"),
        base_raw=base_raw,
        sweep_params=raw.get("sweep", {}),
        seeds=seeds,
    )


def run_sweep(
    sweep_config: SweepConfig,
    store: RunStore,
    *,
    replication_sample_size: int = DEFAULT_REPLICATION_SAMPLE_SIZE,
    on_point_done=None,
) -> list[int]:
    """Run every point in the sweep, persisting each as its own run.

    Returns the list of run ids, in the same order as
    ``sweep_config.points()``.
    """
    run_ids = []
    for point in sweep_config.points():
        config_text = yaml.safe_dump({"overrides": point.overrides, "seed": point.config.seed})
        run_id = store.start_run(
            experiment_name=sweep_config.name,
            config_text=config_text,
            seed=point.config.seed,
        )
        store.record_event(run_id, 0, "sweep_point", point.overrides)

        def report(metrics: dict, run_id=run_id) -> None:
            store.record_metrics(run_id, metrics["epoch"], metrics)

        universe = run_bff_soup(point.config, on_report=report)

        sample_size = min(replication_sample_size, point.config.universe.population_size)
        sample_rng = np.random.default_rng(point.config.seed)
        sample_idx = sample_rng.choice(
            point.config.universe.population_size, size=sample_size, replace=False
        )
        scores = replication_scores(
            universe.population[sample_idx],
            seed=point.config.seed,
            max_steps=point.config.universe.max_steps,
            num_trials=DEFAULT_NUM_TRIALS,
        )
        best_score = int(scores.max())
        genome_length = point.config.universe.genome_length
        store.record_metrics(
            run_id, universe.epoch, {"best_replication_score": float(best_score)}
        )
        store.record_event(
            run_id,
            universe.epoch,
            "replication_scan",
            {
                "best_score": best_score,
                "sample_size": sample_size,
                "classification": classify(best_score, genome_length),
            },
        )

        store.finish_run(run_id, universe.epoch)
        run_ids.append(run_id)
        if on_point_done is not None:
            on_point_done(point, run_id, universe, best_score)

    return run_ids


def collect_sweep_results(store: RunStore, experiment_name: str) -> list[dict]:
    """One row per completed sweep-point run: its parameter overrides plus
    whatever the end-of-run replication scan found.
    """
    results = []
    for run in store.list_runs():
        if run["experiment_name"] != experiment_name:
            continue
        events = store.get_events(run["id"])
        sweep_point = next((e for e in events if e["kind"] == "sweep_point"), None)
        if sweep_point is None:
            continue
        replication_scan = next((e for e in events if e["kind"] == "replication_scan"), None)

        row = dict(sweep_point["payload"])
        row["run_id"] = run["id"]
        row["status"] = run["status"]
        row["final_epoch"] = run["final_epoch"]
        if replication_scan is not None:
            row["best_replication_score"] = replication_scan["payload"]["best_score"]
            row["classification"] = replication_scan["payload"]["classification"]
        results.append(row)
    return results


def summarize_by_parameter(
    results: list[dict],
    group_by: str,
    *,
    genome_length: int,
    candidate_threshold: float = 0.5,
) -> list[dict]:
    """Group sweep results by one swept parameter and report the fraction
    of runs whose replication scan found a candidate replicator.

    Never reports a probability without also reporting the sample size it
    came from (spec section 22). ``genome_length`` is applied uniformly to
    every group: if the sweep varies genome length itself, pass a
    per-row-aware grouping instead of this convenience function, since a
    single threshold fraction wouldn't be comparable across lengths.
    """
    groups: dict = {}
    for row in results:
        if "best_replication_score" not in row:
            continue
        groups.setdefault(row.get(group_by), []).append(row)

    summary = []
    for key in sorted(groups, key=lambda k: (k is None, k)):
        rows = groups[key]
        n_runs = len(rows)
        n_found = sum(
            1
            for r in rows
            if genome_length and (r["best_replication_score"] / genome_length) >= candidate_threshold
        )
        summary.append(
            {
                group_by: key,
                "n_runs": n_runs,
                "n_with_candidate_replicator": n_found,
                "p_candidate_replicator": n_found / n_runs if n_runs else 0.0,
            }
        )
    return summary
