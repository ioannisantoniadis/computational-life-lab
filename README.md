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
[`computational-life-lab-spec.md`](computational-life-lab-spec.md).

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

## Experiment configuration

A `bff_soup` experiment is one YAML file. `seed` is the only required
field; everything else has a default (shown below):

```yaml
experiment: bff_soup      # required, must be exactly this
name: my_experiment       # default: "bff_soup" -- becomes the stored run's experiment_name
seed: 12345                # required, no default

population:
  size: 131072              # default: 131072
  genome_length: 64          # default: 64

execution:
  max_steps: 8192            # default: 8192 -- BFF instructions per pairing, per epoch
  head_init: zero             # default: "zero" ("bff_noheads"); "from_tape" is the other supported variant

mutation:
  enabled: false               # default: false
  rate: 0.0                     # default: 0.0 -- per-byte replacement probability, only used if enabled

run:
  epochs: 1000                   # default: 1000
  report_interval: 100            # default: 100 -- epochs between metrics snapshots (and CLI progress lines)

interaction:
  strategy: random_pairing         # accepted for forward-compatibility with the spec's config
                                     # format, but not currently read -- random pairing is the
                                     # only strategy this engine implements (see spec section 9).
```

Shipped configs, all under `experiments/configs/`:

- `bff_dev.yaml` — small/fast, for local smoke-testing the CLI or the dashboard.
- `bff_baseline.yaml` — the canonical experiment (population 131,072, 20,000 epochs, no mutation).
- `bff_population_sweep.yaml` — a `bff_soup_sweep` config (see below), spec experiment 004.

### Sweep configuration

A `bff_soup_sweep` config cross-products one or more swept parameters
with a list of seeds, running one full `bff_soup` experiment per
combination:

```yaml
experiment: bff_soup_sweep
name: population_size_sweep

base:                        # same shape as a normal bff_soup config, minus `seed`
  population:
    genome_length: 64
  execution:
    max_steps: 4096
  run:
    epochs: 500
    report_interval: 100

sweep:
  population.size: [256, 1024, 4096]   # dotted keys addressing the same nested shape as `base`
  # mutation.rate: [0, 0.001]           # any number of parameters can be swept; they're cross-producted

seeds:
  count: 5      # seeds 0..4 -- or use `seeds: {list: [10, 20, 30]}` for an explicit list
  start: 0
```

Every sweep point runs like a normal experiment and, at the end, is
additionally scanned for candidate replicators
(`analysis.replication.replication_scores`, the same method used to
produce the "Computational Life" paper's own reported statistics) over
a sample of its final population — that scan result is what
`life sweep-report` aggregates.

## Running experiments

```bash
life run CONFIG.yaml [--epochs N] [--seed N]
```

`--epochs`/`--seed` override the config's own values. Add persistence
and checkpointing as needed (see "Run outputs" below):

```bash
life run CONFIG.yaml --db runs/x.db                                    # persist metrics + run metadata
life run CONFIG.yaml --save-checkpoint runs/final                       # save final state
life run CONFIG.yaml --checkpoint-dir runs/ckpts --checkpoint-interval 1000   # periodic checkpoints
life run CONFIG.yaml --resume-from runs/final                           # continue from a checkpoint
```

`--resume-from` and `--seed` can't be combined — a resumed run's RNG
state comes entirely from the checkpoint. The four flags above are
shown separately, but combine freely in one command; the one thing to
know when you do is that adding `--db` changes *where checkpoints
actually land* (see "Run outputs" below) — the exact path is always in
that run's `checkpoint_saved` events (`life analyze RUN_ID --db ...`),
so look it up there rather than guessing when passing it to
`--resume-from` later.

Parameter sweeps use a separate subcommand (a sweep config's `--db` is
required, since a sweep's value comes from comparing its many runs
afterward):

```bash
life sweep SWEEP_CONFIG.yaml --db runs/sweep.db
```

## Analyzing and comparing runs

Everything below reads from a `--db` SQLite file written by `life run
--db` or `life sweep --db`:

```bash
life list-runs --db runs/x.db [--experiment NAME]        # browse what's stored
life analyze RUN_ID --db runs/x.db                         # one run's config, latest metrics, events
life inspect RUN_ID --db runs/x.db --organism INDEX \      # one organism from a run's checkpoint
    [--replication-score]                                    # (population slot 0..population_size-1)
life sweep-report --db runs/sweep.db --experiment NAME \   # P(candidate replicator | swept parameter),
    --group-by population.size --genome-length 64            # with sample sizes, across a whole sweep
```

`life inspect` requires the run to have a saved checkpoint (`--db`
alone, with no `--save-checkpoint`/`--checkpoint-dir`, only persists
metrics — there's no population to inspect without one).

## Visualizing (the Streamlit dashboard)

```bash
streamlit run app/streamlit_app.py
```

The dashboard calls the exact same engine as the CLI (`BffSoupUniverse`,
`compute_metrics`, `analysis.*`) — a run started in one and inspected in
the other produces identical numbers. It has no simulation logic of its
own. Sections, top to bottom:

- **Experiment** (sidebar) — pick a config, override its seed, reset/reinitialize.
- **Load stored run** (sidebar) — open any `--db` file, list its runs, and
  load one: if it has a saved checkpoint, this restores the *actual*
  population/ancestry/RNG state and the run's full metrics history, so
  you can inspect a run that took hours to produce and continue
  stepping/playing it forward from exactly where it left off.
- **Time controls** (sidebar) — Step / Play / Pause, epochs-per-step.
- **Analysis → Track lineage** (sidebar) — opt-in, memory-heavy ancestry
  recording; only captures ancestry from the point it's enabled onward.
- **Population grid** — colored by genome identity (identical color within
  one snapshot means byte-identical genomes; colors carry no meaning
  across snapshots). Large populations are subsampled for display (a
  slider controls how many).
- **Population metrics** — genome diversity and dominant-genome-frequency
  history.
- **Diversity, entropy & complexity** — Simpson's diversity index; genome/
  byte/instruction-level entropy on one chart; compressed-bits-per-byte
  and structural-redundancy complexity proxies.
- **Genome inspector** — pick any organism by population index: id,
  generation, age, parent ids, the genome rendered with active
  instructions bolded and NOP bytes shown as hex, its instruction
  distribution, a lineage graph (ancestors/descendants, when lineage
  tracking is on), and an on-demand replication-consistency score.
- **Execution debugger** — pair any two organisms' current genomes into a
  128-byte tape and step through BFF execution by hand (Step / Run to
  halt / Reset), with head0/head1/pc highlighted in the same
  blue/red/green scheme the reference implementation's own debug output
  uses.
- **Scan for candidate replicators** — runs the replication-consistency
  check across a population sample, tables the top scorers, and can jump
  the genome inspector straight to the top result.
- **Compare stored runs** — open a `--db` file, pick several runs, overlay
  any one metric's full history across all of them on a single chart.

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
software version, status, a per-epoch metrics history, and an event
log — including a `checkpoint_saved` event per checkpoint, with its
file path, so a run's checkpoints are always traceable from its
database row) in the `runs`/`metrics`/`events` tables — see
[`storage/database.py`](src/computational_life/storage/database.py).
Checkpoints written with `--db` set are namespaced under
`<checkpoint_dir>/run_<id>/` so two runs sharing a directory never
collide.

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
stable across repeated epochs — not a leak), but see the checkpointing
support above if you need to run something multi-hour on a
memory-constrained machine.

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

- Agüera y Arcas, Alakuijala, Evans, Laurie, Mordvintsev, Niklasson,
  Randazzo, Versari. *Computational Life: How Well-formed,
  Self-replicating Programs Emerge from Simple Interaction* (2024),
  [arXiv:2406.19108](https://arxiv.org/abs/2406.19108). The primary
  source for BFF's semantics and the experiment design this project
  implements.
- [`paradigms-of-intelligence/cubff`](https://github.com/paradigms-of-intelligence/cubff) —
  the paper authors' own reference implementation; see
  [`docs/bff_semantics.md`](docs/bff_semantics.md) for exactly which
  parts of it were consulted and how.
- Historical artificial-life context for the broader research question
  (not consulted for BFF's own semantics): Ray, T. S., *"An Approach to
  the Synthesis of Life"* (Tierra, 1991); Ofria, C. & Wilke, C. O.,
  *"Avida: A Software Platform for Research in Computational
  Evolutionary Biology"* (2004).

## Limitations

- Reproducibility is guaranteed against this project's own RNG scheme
  (NumPy `Generator(PCG64)`), not bit-for-bit against `cubff`'s
  SplitMix64-based streams — see `docs/bff_semantics.md` for why that's
  expected and doesn't affect scientific validity.
- Replication detection is a heuristic (partner-independence under
  repeated random pairing), not proof of self-replication — see
  `analysis/replication.py`'s docstring for exactly what it does and
  doesn't establish.
- No experiment in this repository's history has yet been run at the
  full canonical scale for its full epoch count; every verification so
  far has been at reduced population/epoch counts. See "Performance"
  above.
