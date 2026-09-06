# Computational Life Lab

An experimental laboratory for studying emergence, evolution, and
self-replication in minimal computational universes.

```text
random computation
        |
    interaction
        |
  self-modification
        |
structured computation
        |
  self-replication
        |
evolutionary dynamics
        |
        ?
```

The first experiment is the **BFF primordial soup**: start with a
population of random 64-byte programs, repeatedly pick random pairs,
concatenate them into a 128-byte tape, run it as a self-modifying BFF
program, split the result back into two genomes, and replace the
originals. No fitness function, no selection, no hard-coded notion of
"replicator" — the simulator does not know what the experimenter hopes
to discover. The full design intent and phased build-out plan lives in
[`computational-life-lab-spec.md`](computational-life-lab-spec.md); the
research tradition this sits in (von Neumann, Tierra, Avida, and the
"Computational Life" paper this project implements) is in
[`docs/artificial_life_background.md`](docs/artificial_life_background.md).

## Status

Phases 1-4 of the spec's section 31 are implemented: a deterministic,
tested, UI-independent BFF engine (CLI + Streamlit dashboard), an
analysis layer (diversity, entropy, complexity proxies, replication
detection, lineage tracking), and reproducibility infrastructure
(SQLite run storage, checkpointing, parameter sweeps, run comparison).

Not yet built: population coloring by lineage in the grid view (ancestry
is a DAG since every organism has two parents, so a single "founder
color" per organism usually isn't well-defined beyond a couple of
generations — the lineage graph for one selected organism is drawn
instead, honestly, rather than inventing a per-organism founder color),
automatic "candidate replicator detected" event flagging during a live
run (detection exists but is on-demand/end-of-run only), and Phase 5
(generic substrates beyond BFF) — deliberately deferred until the BFF
system has been pushed further.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"       # core + CLI + test tooling
pip install -e ".[ui]"        # also needed for the Streamlit dashboard
```

## Quickstart

```bash
# Fast local smoke test (small population, few epochs):
life run experiments/configs/bff_dev.yaml --epochs 200

# The canonical baseline (population 131,072, per the spec defaults --
# expect this to take a couple of days; see "Performance" below):
life run experiments/configs/bff_baseline.yaml

# Watch it live instead:
streamlit run app/streamlit_app.py
```

Every run is deterministic given its configuration and seed:

```bash
life run experiments/configs/bff_dev.yaml --epochs 20 --seed 1  # always identical output
life run experiments/configs/bff_dev.yaml --epochs 20 --seed 1
```

## Documentation

This file covers installation and the two commands above; everything
else — experiment/sweep configuration, the full CLI reference, the
dashboard walkthrough, how each analysis method actually works, and
domain background — lives in **[`docs/`](docs/README.md)**:

| Doc | Covers |
|---|---|
| [`docs/artificial_life_background.md`](docs/artificial_life_background.md) | The research tradition this project sits in, and where it's headed |
| [`docs/bff_semantics.md`](docs/bff_semantics.md) | BFF's exact instruction set and semantics, derived from the primary reference implementation |
| [`docs/configuration.md`](docs/configuration.md) | Every YAML config field, its default, and why |
| [`docs/cli_reference.md`](docs/cli_reference.md) | Every `life` subcommand with worked examples |
| [`docs/dashboard_guide.md`](docs/dashboard_guide.md) | Every section of the Streamlit dashboard |
| [`docs/analysis_methods.md`](docs/analysis_methods.md) | How diversity, entropy, complexity, replication detection, and lineage tracking work |

## Run outputs (databases, checkpoints)

`life run --db ...`, `life sweep --db ...`, and `--save-checkpoint` /
`--checkpoint-dir` write SQLite databases and `.npz` checkpoint files
(see [`docs/cli_reference.md`](docs/cli_reference.md)). These are
regenerable data, not source, so they're gitignored — the convention is
to keep them locally under `runs/` (created on demand, never
committed). Every run gets a stable integer id and full metadata
(config text, seed, software version, status, a per-epoch metrics
history, and an event log) — see
[`storage/database.py`](src/computational_life/storage/database.py).

## Performance

The vectorized batch interpreter (many tapes in lockstep, NumPy) is
what makes the canonical population size tractable at all, but it's
still real compute: measured on one development machine, a single
epoch at population 131,072 takes roughly 10-11 seconds, so
`bff_baseline.yaml`'s full 20,000 epochs is on the order of 2-2.5 days.
Smaller populations are proportionally faster (roughly 0.2-0.4s/epoch
at population 256-4096) but also — plausibly, since population size is
itself one of the things this instrument is meant to let you study —
have worse odds of producing a candidate replicator in a given number
of epochs. Peak memory at full population is modest (~90MB measured,
stable across repeated epochs — not a leak), but see
[`docs/cli_reference.md`](docs/cli_reference.md) for checkpointing if
you need to run something multi-hour on a memory-constrained machine.

## Running the tests

```bash
pytest
```

## Architecture

- `src/computational_life/core/` — substrate-agnostic pieces (seeded RNG,
  organism snapshot type).
- `src/computational_life/substrates/bff/` — the BFF instruction set, a
  scalar single-tape interpreter (the correctness oracle and the
  dashboard's execution-debugger backend), a vectorized batch
  interpreter (NumPy, many tapes in lockstep — validated against the
  scalar interpreter via differential tests), and the soup universe
  (population state + the per-epoch pairing/execution/replacement loop).
- `src/computational_life/experiments/` — YAML configuration loading, the
  `bff_soup` run loop, and parameter sweeps.
- `src/computational_life/analysis/` — purely observational: diversity,
  entropy, complexity proxies, replication detection, lineage tracking.
  Never imported by `substrates/` or fed back into simulation dynamics.
- `src/computational_life/storage/` — SQLite run/metrics/event
  persistence and checkpoint save/restore.
- `src/computational_life/cli.py` — the `life` command-line tool. No
  Streamlit or UI dependency.
- `app/` — the Streamlit dashboard and its presentation-only helpers
  (`rendering.py`); calls the same engine as the CLI, adds no
  simulation logic of its own.

## References

- Agüera y Arcas, B. et al. (2024). *Computational Life: How
  Well-formed, Self-replicating Programs Emerge from Simple
  Interaction.* [arXiv:2406.19108](https://arxiv.org/abs/2406.19108) —
  the primary source for BFF's semantics and the experiment design this
  project implements.
- [`paradigms-of-intelligence/cubff`](https://github.com/paradigms-of-intelligence/cubff)
  — the paper authors' own reference implementation.

See [`docs/artificial_life_background.md`](docs/artificial_life_background.md)
for the fuller reading list (von Neumann, Core War, Tierra, Avida) and
how this project relates to each.

## Limitations

- Reproducibility is guaranteed against this project's own RNG scheme
  (NumPy `Generator(PCG64)`), not bit-for-bit against `cubff`'s
  SplitMix64-based streams — see
  [`docs/bff_semantics.md`](docs/bff_semantics.md) for why that's
  expected and doesn't affect scientific validity.
- Replication detection is a heuristic (partner-independence under
  repeated random pairing), not proof of self-replication — see
  [`docs/analysis_methods.md`](docs/analysis_methods.md) for exactly
  what it does and doesn't establish.
- No experiment in this repository's history has yet been run at the
  full canonical scale for its full epoch count; every verification so
  far has been at reduced population/epoch counts. See "Performance"
  above.
