"""Headless CLI for the Computational Life Lab.

No dependency on Streamlit or any UI code (spec section 3.4 / 25).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .experiments.base import load_bff_soup_config
from .experiments.bff_soup import run_bff_soup


def _cmd_run(args: argparse.Namespace) -> int:
    if args.resume_from and args.seed is not None:
        print("--seed has no effect with --resume-from (the checkpoint's RNG state is used)")
        return 1

    config = load_bff_soup_config(args.config)

    overrides = {}
    if args.epochs is not None:
        overrides["epochs"] = args.epochs
    if args.seed is not None:
        overrides["seed"] = args.seed
    if overrides:
        import dataclasses

        universe_config = config.universe
        if "seed" in overrides:
            universe_config = dataclasses.replace(universe_config, seed=overrides.pop("seed"))
        config = dataclasses.replace(config, universe=universe_config, **overrides)

    resumed_universe = None
    if args.resume_from:
        from .storage.checkpoints import load_checkpoint

        resumed_universe = load_checkpoint(args.resume_from)
        print(f"Resumed from checkpoint at epoch {resumed_universe.epoch}")

    run_seed = resumed_universe.config.seed if resumed_universe is not None else config.universe.seed

    store = None
    run_id = None
    if args.db:
        from .storage.database import RunStore

        store = RunStore(args.db)
        run_id = store.start_run(
            experiment_name=config.name,
            config_text=Path(args.config).read_text(),
            seed=run_seed,
        )

    def report(metrics: dict) -> None:
        print(
            f"epoch={metrics['epoch']:>8}  "
            f"unique_genomes={metrics['unique_genomes']:>8}  "
            f"dominant_genome_freq={metrics['dominant_genome_frequency']:.6f}"
        )
        if store is not None:
            store.record_metrics(run_id, metrics["epoch"], metrics)

    # When persisting to a database, namespace checkpoints under runs/<id>/
    # so two runs sharing a --checkpoint-dir never collide on filenames,
    # and record each save as an event so a checkpoint's provenance (which
    # run, which epoch) is queryable from the database rather than only
    # inferable from a filename.
    def checkpoint_subdir(base: Path) -> Path:
        return base / f"run_{run_id}" if store is not None else base

    on_checkpoint = None
    if args.checkpoint_dir:
        from .storage.checkpoints import checkpoint_file_path, save_checkpoint

        checkpoint_dir = checkpoint_subdir(Path(args.checkpoint_dir))
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        def on_checkpoint(universe) -> None:
            checkpoint_path = checkpoint_dir / f"epoch_{universe.epoch:010d}"
            save_checkpoint(universe, checkpoint_path)
            saved_path = checkpoint_file_path(checkpoint_path)
            print(f"Checkpoint saved: {saved_path}")
            if store is not None:
                store.record_event(
                    run_id, universe.epoch, "checkpoint_saved", {"path": str(saved_path)}
                )

    try:
        universe = run_bff_soup(
            config,
            on_report=report,
            universe=resumed_universe,
            on_checkpoint=on_checkpoint,
            checkpoint_interval=args.checkpoint_interval,
        )
    except BaseException:
        if store is not None:
            store.finish_run(run_id, final_epoch=0, status="failed")
            store.close()
        raise

    if args.save_checkpoint:
        from .storage.checkpoints import checkpoint_file_path, save_checkpoint

        final_checkpoint_path = Path(args.save_checkpoint)
        if store is not None:
            final_dir = checkpoint_subdir(final_checkpoint_path.parent)
            final_dir.mkdir(parents=True, exist_ok=True)
            final_checkpoint_path = final_dir / final_checkpoint_path.name
        save_checkpoint(universe, final_checkpoint_path)
        saved_path = checkpoint_file_path(final_checkpoint_path)
        print(f"Final checkpoint saved to {saved_path}")
        if store is not None:
            store.record_event(run_id, universe.epoch, "checkpoint_saved", {"path": str(saved_path)})

    if store is not None:
        store.finish_run(run_id, final_epoch=universe.epoch)
        print(f"Run {run_id} saved to {args.db}")
        store.close()
    return 0


def _cmd_list_runs(args: argparse.Namespace) -> int:
    from datetime import datetime

    from .storage.database import RunStore

    with RunStore(args.db) as store:
        runs = store.list_runs()
        if args.experiment:
            runs = [r for r in runs if r["experiment_name"] == args.experiment]

    if not runs:
        print(f"No runs found in {args.db}" + (f" for experiment '{args.experiment}'" if args.experiment else ""))
        return 0

    print(f"{'id':>4}  {'experiment_name':<28}  {'seed':>8}  {'status':<10}  {'final_epoch':>11}  started_at")
    for run in runs:
        started = datetime.fromtimestamp(run["started_at"]).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{run['id']:>4}  {run['experiment_name']:<28}  {run['seed']:>8}  "
            f"{run['status']:<10}  {str(run['final_epoch']):>11}  {started}"
        )
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


def _cmd_sweep(args: argparse.Namespace) -> int:
    from .experiments.sweep import load_sweep_config, run_sweep
    from .storage.database import RunStore

    sweep_config = load_sweep_config(args.config)
    points = sweep_config.points()
    print(f"Sweep '{sweep_config.name}': {len(points)} points "
          f"({len(sweep_config.seeds)} seeds each)")

    def on_point_done(point, run_id, universe, best_score) -> None:
        genome_length = point.config.universe.genome_length
        overrides = {k: v for k, v in point.overrides.items() if k != "seed"}
        print(
            f"  run {run_id:>4}  {overrides}  seed={point.overrides['seed']}  "
            f"epoch={universe.epoch}  best_replication_score={best_score}/{genome_length}"
        )

    with RunStore(args.db) as store:
        run_ids = run_sweep(sweep_config, store, on_point_done=on_point_done)

    print(f"Sweep complete: {len(run_ids)} runs saved to {args.db}")
    return 0


def _cmd_sweep_report(args: argparse.Namespace) -> int:
    from .experiments.sweep import collect_sweep_results, summarize_by_parameter
    from .storage.database import RunStore

    with RunStore(args.db) as store:
        results = collect_sweep_results(store, args.experiment)

    if not results:
        print(f"No sweep results found for experiment '{args.experiment}' in {args.db}")
        return 1

    summary = summarize_by_parameter(results, args.group_by, genome_length=args.genome_length)
    print(f"P(candidate replicator | {args.group_by}), genome_length={args.genome_length}:")
    for row in summary:
        print(
            f"  {args.group_by}={row[args.group_by]!r}: "
            f"{row['n_with_candidate_replicator']}/{row['n_runs']} runs "
            f"(p={row['p_candidate_replicator']:.2f})"
        )
    total_runs = sum(row["n_runs"] for row in summary)
    if total_runs < 10:
        print(
            f"Note: only {total_runs} total runs -- too few to draw statistical "
            "conclusions from (spec section 22)."
        )
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
    run_parser.add_argument(
        "--resume-from", default=None, help="Resume from a checkpoint instead of a fresh population"
    )
    run_parser.add_argument(
        "--save-checkpoint", default=None, help="Save a checkpoint of the final state to this path"
    )
    run_parser.add_argument(
        "--checkpoint-dir", default=None, help="Directory to save periodic checkpoints into"
    )
    run_parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=1000,
        help="Epochs between periodic checkpoints (only used with --checkpoint-dir)",
    )
    run_parser.set_defaults(func=_cmd_run)

    list_runs_parser = subparsers.add_parser("list-runs", help="List runs stored in a database")
    list_runs_parser.add_argument("--db", required=True, help="SQLite database path to read from")
    list_runs_parser.add_argument(
        "--experiment", default=None, help="Only show runs with this experiment name"
    )
    list_runs_parser.set_defaults(func=_cmd_list_runs)

    analyze_parser = subparsers.add_parser("analyze", help="Summarize a stored run")
    analyze_parser.add_argument("run_id", type=int, help="Run id to summarize")
    analyze_parser.add_argument("--db", required=True, help="SQLite database path to read from")
    analyze_parser.set_defaults(func=_cmd_analyze)

    sweep_parser = subparsers.add_parser(
        "sweep", help="Run a parameter sweep (many population/mutation/seed combinations)"
    )
    sweep_parser.add_argument("config", help="Path to a bff_soup_sweep YAML configuration file")
    sweep_parser.add_argument(
        "--db", required=True, help="SQLite database path to persist every sweep run to"
    )
    sweep_parser.set_defaults(func=_cmd_sweep)

    sweep_report_parser = subparsers.add_parser(
        "sweep-report", help="Summarize P(candidate replicator | parameter) from a stored sweep"
    )
    sweep_report_parser.add_argument("--db", required=True, help="SQLite database path to read from")
    sweep_report_parser.add_argument(
        "--experiment", required=True, help="Sweep name (matches the sweep config's `name:`)"
    )
    sweep_report_parser.add_argument(
        "--group-by", required=True, help="Swept parameter key to group by, e.g. population.size"
    )
    sweep_report_parser.add_argument(
        "--genome-length",
        type=int,
        default=64,
        help="Genome length used to normalize replication scores (must be constant across the "
        "sweep for this report to be meaningful)",
    )
    sweep_report_parser.set_defaults(func=_cmd_sweep_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
