# CLI reference

The `life` command (`src/computational_life/cli.py`) has no Streamlit
or UI dependency — everything here works headless, over SSH, or in a
background/scheduled job. `life <command> --help` always reflects the
actual current flags; what follows adds the context and worked examples
`--help` doesn't.

## `life run`

```text
life run CONFIG.yaml [--epochs N] [--seed N] [--db PATH]
    [--resume-from PATH] [--save-checkpoint PATH]
    [--checkpoint-dir PATH] [--checkpoint-interval N]
```

Runs one `bff_soup` experiment (see [`configuration.md`](configuration.md)
for the config format). `--epochs`/`--seed` override the config's own
values without editing the file.

- **`--db PATH`** — persist run metadata and a `compute_metrics()`
  snapshot every `report_interval` epochs to a SQLite database (created
  if it doesn't exist). Without this, a run's results only ever exist
  as stdout.
- **`--save-checkpoint PATH`** — write one checkpoint (full population,
  ancestry, RNG state) after the run finishes.
- **`--checkpoint-dir PATH --checkpoint-interval N`** — write a
  checkpoint automatically every `N` epochs, named `epoch_<N>.npz`
  inside `PATH`.
- **`--resume-from PATH`** — load a checkpoint instead of starting a
  fresh random population, then run `epochs` *more* epochs from there.
  Cannot be combined with `--seed` (the checkpoint's own RNG state
  governs the resumed run; a seed override would silently do nothing).

When `--db` is set, checkpoint paths from `--checkpoint-dir` and
`--save-checkpoint` are both namespaced under `<path>/run_<id>/` so two
runs sharing a checkpoint directory never overwrite each other's files
— the actual on-disk path is always recorded in that run's
`checkpoint_saved` events (visible via `life analyze`). Without `--db`
there's no run id, so paths are used exactly as given.

```bash
life run experiments/configs/bff_dev.yaml --epochs 200
life run experiments/configs/bff_baseline.yaml --db runs/baseline.db \
    --checkpoint-dir runs/baseline_checkpoints --checkpoint-interval 500
life run experiments/configs/bff_dev.yaml --resume-from runs/baseline_checkpoints/run_1/epoch_0000000500 --epochs 500
```

## `life sweep`

```text
life sweep SWEEP_CONFIG.yaml --db PATH
```

Runs every point of a `bff_soup_sweep` config (see
[`configuration.md`](configuration.md#bff_soup_sweep-many-experiments-at-once)),
persisting each as its own run in `PATH`, tagged with a `sweep_point`
event recording exactly which parameter combination and seed produced
it. `--db` is required — a sweep's entire value is in comparing its
many runs afterward, so there's no reason to run one without persisting
it.

```bash
life sweep experiments/configs/bff_population_sweep.yaml --db runs/pop_sweep.db
```

## `life list-runs`

```text
life list-runs --db PATH [--experiment NAME]
```

Prints a table of every run in the database (id, experiment name, seed,
status, final epoch, start time), optionally filtered to one experiment
name. The starting point for "what's actually in this database" —
without it you'd need to open the file in a SQLite client or write a
throwaway script.

```bash
life list-runs --db runs/pop_sweep.db
life list-runs --db runs/pop_sweep.db --experiment population_size_sweep
```

## `life analyze`

```text
life analyze RUN_ID --db PATH
```

Prints one run's config metadata (experiment name, status, seed,
software version, final epoch), its most recent metrics snapshot (every
key `compute_metrics()` produces), and every recorded event —
including `checkpoint_saved` events, which is how you find a
checkpoint's actual on-disk path for `--resume-from` or `life inspect`.

```bash
life analyze 1 --db runs/baseline.db
```

## `life inspect`

```text
life inspect RUN_ID --db PATH --organism INDEX [--replication-score]
```

Loads a run's **latest saved checkpoint** and prints one organism's
full detail: organism id, generation, birth epoch, age, parent ids, and
genome (hex). `--organism` is a **population index** (0 to
`population_size - 1`, the slot in the array), matching the dashboard's
genome inspector — not the organism's globally-unique `organism_id`,
which can't be looked up directly since only the currently-alive
occupant of each slot is stored in a checkpoint.

Requires the run to have at least one saved checkpoint (`--db` alone,
with no `--save-checkpoint`/`--checkpoint-dir`, only persists metrics —
there's no population snapshot to inspect without one). `--replication-score`
additionally runs the on-demand replication-consistency check on that
one organism (see [`analysis_methods.md`](analysis_methods.md#replication-detection-analysisreplicationpy));
it's optional because it costs 65 BFF executions, not free.

```bash
life inspect 1 --db runs/baseline.db --organism 42
life inspect 1 --db runs/baseline.db --organism 42 --replication-score
```

## `life sweep-report`

```text
life sweep-report --db PATH --experiment NAME --group-by KEY [--genome-length N]
```

Groups a sweep's completed runs by one swept parameter (`--group-by`,
e.g. `population.size`) and reports, per group, how many runs' final
replication scan crossed the "candidate replicator" threshold out of
how many total runs in that group — `n_with_candidate_replicator /
n_runs`, never a bare probability without the sample size behind it.
Warns explicitly when the whole sweep has fewer than 10 total runs,
since that's too few to draw a conclusion from either way.

`--genome-length` normalizes replication scores (0..genome_length) into
a fraction against the classification threshold; it must be constant
across the sweep's runs for the report to mean anything — if a sweep
varies genome length itself, this report isn't the right tool (see
[`configuration.md`](configuration.md)).

```bash
life sweep-report --db runs/pop_sweep.db --experiment population_size_sweep \
    --group-by population.size --genome-length 64
```
