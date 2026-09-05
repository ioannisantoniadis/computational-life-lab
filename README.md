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
to discover (see `computational-life-lab-spec.md`).

## Status

**Phase 1 (core + BFF, headless)** is implemented: a deterministic,
tested, UI-independent BFF interpreter and soup experiment, runnable
from the CLI. Visualization, replication detection, lineage tracking,
and persistence are later phases (see `computational-life-lab-spec.md`
section 31) and are not yet built.

## Running the baseline experiment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Fast local smoke test (small population, few epochs):
life run experiments/configs/bff_dev.yaml --epochs 200

# The canonical baseline (population 131,072, per the spec defaults):
life run experiments/configs/bff_baseline.yaml
```

Every run is deterministic given its configuration and seed:

```bash
life run experiments/configs/bff_dev.yaml --epochs 20 --seed 1  # always identical output
life run experiments/configs/bff_dev.yaml --epochs 20 --seed 1
```

## Run outputs (databases, checkpoints)

`life run --db ...`, `life sweep --db ...`, and `--save-checkpoint` /
`--checkpoint-dir` write SQLite databases and `.npz` checkpoint files.
These are regenerable data, not source, so they're gitignored — the
convention is to keep them locally under `runs/` (created on demand,
never committed):

```bash
life sweep experiments/configs/bff_population_sweep.yaml --db runs/population_sweep.db
life sweep-report --db runs/population_sweep.db --experiment population_size_sweep \
    --group-by population.size --genome-length 64

life run experiments/configs/bff_dev.yaml --db runs/dev.db \
    --checkpoint-dir runs/checkpoints --checkpoint-interval 1000
life analyze 1 --db runs/dev.db
```

Every run gets a stable integer id and full metadata (config text, seed,
software version, status, a per-epoch metrics history, and an event log)
in the `runs`/`metrics`/`events` tables -- see
[`storage/database.py`](src/computational_life/storage/database.py).
Query them with `life analyze` / `life sweep-report`, or open the
`.db` file directly (it's plain SQLite) for anything more ad hoc.

## Running the tests

```bash
pytest
```

## BFF semantics

The exact instruction set, byte encoding, loop/control-flow rules, and
default parameters are derived from the primary reference implementation
behind the "Computational Life" paper, not guessed. See
[`docs/bff_semantics.md`](docs/bff_semantics.md) for the full derivation,
citations, and every place this implementation had to resolve an
ambiguity or omission in `computational-life-lab-spec.md`.

## Architecture

- `src/computational_life/core/` — substrate-agnostic pieces (seeded RNG,
  organism snapshot type).
- `src/computational_life/substrates/bff/` — the BFF instruction set, a
  scalar single-tape interpreter (the correctness oracle and future
  debugger backend), a vectorized batch interpreter (NumPy, many tapes in
  lockstep — validated against the scalar interpreter via differential
  tests), and the soup universe (population state + the per-epoch
  pairing/execution/replacement loop).
- `src/computational_life/experiments/` — YAML configuration loading and
  the `bff_soup` experiment run loop.
- `src/computational_life/cli.py` — the `life` command-line tool. No
  Streamlit or UI dependency.

## References

- Agüera y Arcas et al., *Computational Life: How Well-formed,
  Self-replicating Programs Emerge from Simple Interaction*,
  [arXiv:2406.19108](https://arxiv.org/abs/2406.19108).
- [`paradigms-of-intelligence/cubff`](https://github.com/paradigms-of-intelligence/cubff) —
  the paper's reference implementation.
