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

    def report(summary: dict) -> None:
        print(
            f"epoch={summary['epoch']:>8}  "
            f"unique_genomes={summary['unique_genomes']:>8}  "
            f"dominant_genome_freq={summary['dominant_genome_frequency']:.6f}"
        )

    run_bff_soup(config, on_report=report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="life", description="Computational Life Lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a bff_soup experiment from a YAML config")
    run_parser.add_argument("config", help="Path to an experiment YAML configuration file")
    run_parser.add_argument("--epochs", type=int, default=None, help="Override epochs from config")
    run_parser.add_argument("--seed", type=int, default=None, help="Override seed from config")
    run_parser.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
