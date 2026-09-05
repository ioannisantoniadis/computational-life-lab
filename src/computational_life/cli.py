"""Headless CLI for the Computational Life Lab.

No dependency on Streamlit or any UI code (spec section 3.4 / 25).
"""

from __future__ import annotations

import argparse
import sys

from .experiments.base import load_bff_soup_config
from .experiments.bff_soup import run_bff_soup


def _cmd_run(args: argparse.Namespace) -> int:
    config = load_bff_soup_config(args.config)

    overrides = {}
    if args.epochs is not None:
        overrides["epochs"] = args.epochs
    if args.seed is not None:
        overrides["seed"] = args.seed
    if overrides:
        import dataclasses

        universe = config.universe
        if "seed" in overrides:
            universe = dataclasses.replace(universe, seed=overrides.pop("seed"))
        config = dataclasses.replace(config, universe=universe, **overrides)

    store = None
    run_id = None
    if args.db:
        from pathlib import Path

        from .storage.database import RunStore

        store = RunStore(args.db)
        run_id = store.start_run(
            experiment_name=config.name,
            config_text=Path(args.config).read_text(),
            seed=config.universe.seed,
        )

    def report(metrics: dict) -> None:
        print(
            f"epoch={metrics['epoch']:>8}  "
            f"unique_genomes={metrics['unique_genomes']:>8}  "
            f"dominant_genome_freq={metrics['dominant_genome_frequency']:.6f}"
        )
        if store is not None:
            store.record_metrics(run_id, metrics["epoch"], metrics)

    try:
        universe = run_bff_soup(config, on_report=report)
    except BaseException:
        if store is not None:
            store.finish_run(run_id, final_epoch=0, status="failed")
            store.close()
        raise

    if store is not None:
        store.finish_run(run_id, final_epoch=universe.epoch)
        print(f"Run {run_id} saved to {args.db}")
        store.close()
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from .storage.database import RunStore

    with RunStore(args.db) as store:
        run = store.get_run(args.run_id)
        print(f"Run {run['id']}: {run['experiment_name']}  (status: {run['status']})")
        print(f"  seed: {run['seed']}")
        print(f"  software version: {run['software_version']}")
        print(f"  final epoch: {run['final_epoch']}")

        latest = store.latest_metrics(args.run_id)
        if latest is None:
            print("  no metrics recorded")
        else:
            print(f"  latest metrics (epoch {latest['epoch']}):")
            for name, value in sorted(latest.items()):
                if name == "epoch":
                    continue
                print(f"    {name}: {value}")

        events = store.get_events(args.run_id)
        if events:
            print(f"  events ({len(events)}):")
            for event in events:
                print(f"    epoch {event['epoch']}: {event['kind']} {event['payload'] or ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="life", description="Computational Life Lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a bff_soup experiment from a YAML config")
    run_parser.add_argument("config", help="Path to an experiment YAML configuration file")
    run_parser.add_argument("--epochs", type=int, default=None, help="Override epochs from config")
    run_parser.add_argument("--seed", type=int, default=None, help="Override seed from config")
    run_parser.add_argument(
        "--db", default=None, help="SQLite database path to persist this run's metrics to"
    )
    run_parser.set_defaults(func=_cmd_run)

    analyze_parser = subparsers.add_parser("analyze", help="Summarize a stored run")
    analyze_parser.add_argument("run_id", type=int, help="Run id to summarize")
    analyze_parser.add_argument("--db", required=True, help="SQLite database path to read from")
    analyze_parser.set_defaults(func=_cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
