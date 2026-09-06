# Configuration reference

Full field-by-field reference for both YAML config kinds this project
reads. For a quick example of each, see the [README quickstart](../README.md#quickstart);
for *why* particular defaults were chosen (e.g. `head_init: zero`,
`max_steps: 8192`), see [`bff_semantics.md`](bff_semantics.md).

## `bff_soup`: a single experiment

Parsed by `experiments.base.parse_bff_soup_config` /
`load_bff_soup_config`. `seed` is the only field with no default —
every experiment must be reproducible from (config, seed), so there is
deliberately no implicit seed.

```yaml
experiment: bff_soup      # required, must be exactly this string
name: my_experiment       # default: "bff_soup"
seed: 12345                # required -- no default

population:
  size: 131072              # default: 131072
  genome_length: 64          # default: 64

execution:
  max_steps: 8192            # default: 8192
  head_init: zero             # default: "zero"

mutation:
  enabled: false               # default: false
  rate: 0.0                     # default: 0.0

run:
  epochs: 1000                   # default: 1000
  report_interval: 100            # default: 100

interaction:
  strategy: random_pairing         # accepted, not currently read (see below)
```

| Field | Default | Meaning |
|---|---|---|
| `experiment` | — (required) | Must be the literal string `bff_soup`. Distinguishes this config kind from a `bff_soup_sweep`. |
| `name` | `"bff_soup"` | Becomes the `experiment_name` column when the run is persisted with `--db`; purely a label. |
| `seed` | — (required) | The single integer that, together with the rest of this file, fully determines the run's trajectory (`core.rng.RngStreams`; see [`bff_semantics.md`](bff_semantics.md#8-random-number-generation-is-not-bit-matched-to-the-reference)). |
| `population.size` | `131072` | Number of organisms. Must be even (they interact in pairs). The spec's canonical/paper-matching value. |
| `population.genome_length` | `64` | Bytes per genome. The combined tape two organisms are executed on is `2 * genome_length`. |
| `execution.max_steps` | `8192` | BFF instructions executed per pairing, per epoch, before forcibly stopping a non-halting program. Matches the reference implementation's own budget (`8 * 1024`). |
| `execution.head_init` | `"zero"` | `"zero"`: head0 = head1 = 0 at the start of every pairing (the paper's own "bff_noheads" quick-start variant). `"from_tape"`: heads are read from the tape's own first two bytes instead (the "bff" / `BFF_HEADS` variant). See [`bff_semantics.md`](bff_semantics.md#4-head-initialization-noheads-is-the-phase-1-default) for why `"zero"` is the default. |
| `mutation.enabled` | `false` | Whether any mutation is applied. The baseline experiment's entire point is to show emergence *without* this. |
| `mutation.rate` | `0.0` | Per-byte probability of the byte being replaced by a uniformly random value, applied to the whole 128-byte combined tape *before* execution, only when `enabled: true`. Not an increment or bit-flip — full replacement (see [`bff_semantics.md`](bff_semantics.md#6-mutation-when-enabled-replaces-whole-bytes)). |
| `run.epochs` | `1000` | Number of epochs `life run` executes. One epoch = one full random perfect matching of the population, all pairs executed (see [`bff_semantics.md`](bff_semantics.md#5-random-pairing-repeat-means-one-epoch--one-full-random-perfect-matching)) — not one single pairing. |
| `run.report_interval` | `100` | Epochs between `compute_metrics()` snapshots — both the CLI's progress lines and, when `--db` is set, the rows written to the `metrics` table. Smaller values give finer-grained history at the cost of more (cheap) computation per run. |
| `interaction.strategy` | `random_pairing` | Accepted for shape-compatibility with the project spec's own config example, but **not read anywhere in the parser**. Random pairing is the only interaction strategy this engine implements; this field is a placeholder for when Phase 5 adds others. |

## `bff_soup_sweep`: many experiments at once

Parsed by `experiments.sweep.load_sweep_config`. Cross-products every
list under `sweep:` with the seed list, producing one full `bff_soup`
config per combination, each run exactly like a normal experiment via
`experiments.sweep.run_sweep`.

```yaml
experiment: bff_soup_sweep
name: population_size_sweep

base:                        # same shape as a bff_soup config, minus `seed`
  population:
    genome_length: 64
  execution:
    max_steps: 4096
  run:
    epochs: 500
    report_interval: 100

sweep:
  population.size: [256, 1024, 4096]
  # mutation.rate: [0, 0.001]        # multiple swept keys cross-product together

seeds:
  count: 5      # seeds 0..4
  start: 0      # (default 0; only meaningful with `count`)
  # list: [10, 20, 30]   # alternative to count/start: an explicit seed list
```

| Field | Default | Meaning |
|---|---|---|
| `experiment` | — (required) | Must be the literal string `bff_soup_sweep`. |
| `name` | `"sweep"` | Becomes every point's `experiment_name` when persisted — this is what `life sweep-report --experiment NAME` and `life list-runs --experiment NAME` filter on. |
| `base` | `{}` | A dict shaped exactly like a `bff_soup` config (minus `seed`, which the sweep injects per point). `experiment: bff_soup` is filled in automatically if omitted. |
| `sweep` | `{}` | Maps dotted keys (e.g. `population.size`, `mutation.rate` — addressing the same nested shape `base` uses) to a list of values. Every combination across all swept keys is cross-produced (so two swept keys with 3 values each produce 9 combinations, times however many seeds). |
| `seeds.count` / `seeds.start` | `count: 1`, `start: 0` | Generates `range(start, start + count)`. Used when `seeds.list` is absent. |
| `seeds.list` | — | An explicit list of seeds, used instead of `count`/`start` when present. |

Each sweep point, after its `run.epochs` complete, is additionally
scanned for candidate replicators
(`analysis.replication.replication_scores`) over a sample of its final
population — this is what `life sweep-report` aggregates into
`P(candidate replicator | swept parameter)`. See
[`analysis_methods.md`](analysis_methods.md#replication-detection-analysisreplicationpy) for
exactly what that scan does and doesn't establish.

## Shipped configs

All under `experiments/configs/`:

| File | Kind | Purpose |
|---|---|---|
| `bff_dev.yaml` | `bff_soup` | Small (population 512), fast — local smoke-testing the CLI or dashboard. Not scientifically meaningful on its own. |
| `bff_baseline.yaml` | `bff_soup` | The canonical experiment: population 131,072, 20,000 epochs, no mutation. See [Performance](../README.md#performance) for how long this actually takes. |
| `bff_population_sweep.yaml` | `bff_soup_sweep` | Spec experiment 004 (population-size sweep), kept small/fast to run as shipped — bump population sizes, epochs, and seed count for a statistically meaningful result. |
