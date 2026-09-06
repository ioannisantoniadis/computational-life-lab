# Analysis methods

Everything in `src/computational_life/analysis/` is purely
observational: it reads a population snapshot (or a run's recorded
history) and reports a number or classification. Nothing here is
imported by `substrates/` or fed back into simulation dynamics (spec
section 3.2) — the simulator genuinely does not know any of this
exists. This document explains what each measurement actually computes,
why it's defined that way, and what it doesn't establish, in more depth
than the in-code docstrings.

## Diversity (`analysis/diversity.py`)

**Unique genome count** and **dominant genome frequency** are exactly
what they say: `len(set(genomes))`, and `max(count) / population_size`.

**Simpson's diversity index**: `1 - sum(p_i^2)` over the genome
frequency distribution, where `p_i` is genome `i`'s share of the
population. 0 means the whole population shares one genome; it
approaches 1 as genomes spread evenly across many distinct values.
"Diversity index" isn't one universally agreed-upon formula, so the
project picked this one (a standard ecological diversity measure) and
documents it explicitly rather than leaving "diversity" ambiguous.

## Entropy (`analysis/entropy.py`)

Three genuinely different quantities, all Shannon entropy in bits
(`-sum(p_i * log2(p_i))`) of three different frequency distributions —
kept as three separate numbers because they answer different questions
and are easy to conflate under the single word "entropy":

- **Genome-level**: entropy of the distribution over *distinct 64-byte
  genomes*. Answers "how spread out is the population across
  genotypes?" — closely related to Simpson's index above, but on a
  logarithmic rather than quadratic scale.
- **Byte-level**: entropy of the raw *byte values* (0-255) across every
  position of every genome in the population, ignoring genome
  boundaries entirely. This mirrors the reference `cubff`
  implementation's own `h0` metric. Maxes out at 8.0 bits (a perfectly
  uniform byte-value distribution); a healthy random population starts
  near that ceiling.
- **Instruction-level**: entropy of the *decoded* BFF operation at every
  byte position (the ten instructions, the NULL sentinel, and every
  other byte pooled into one "NOP" category — twelve categories total,
  max `log2(12) ≈ 3.58` bits). Since only 11 of 256 byte values decode
  to something other than NOP (see
  [`bff_semantics.md`](bff_semantics.md#2-byte-encoding-is-literal-ascii-plus-one-reserved-sentinel)),
  a random population's instruction entropy is naturally low (most mass
  sits in the NOP category) — a low number here is expected baseline
  behavior, not evidence of anything.

## Complexity proxies (`analysis/complexity.py`)

Per the spec: "do not label any one proxy 'the complexity of the
organism' — call them explicitly complexity proxies." Both measures
here are adapted directly from the reference `cubff` implementation's
own instrumentation (which computes a Brotli-compressed population size
every reporting interval); this project uses Python's standard-library
`zlib` instead of Brotli to avoid a new dependency — the qualitative
interpretation is the same, the absolute numbers aren't comparable
between the two compressors.

**Compressed bits per byte**: `zlib`-compress the entire population as
one blob, report `compressed_size * 8 / original_size`. A mostly-random
population compresses poorly (near 8 bits/byte, the incompressible
ceiling); a population containing many repeated genomes or repeated
substrings (e.g. from copying) compresses much better. This looks at
the population as a whole, not any single organism.

**Structural redundancy**: `byte_entropy - compressed_bits_per_byte`.
Byte-frequency entropy alone only sees *which byte values* are common,
not repeated *patterns* — the same 64-byte genome appearing many times
looks no different to it than the same bytes shuffled randomly, since
value frequencies are identical either way. A real compressor exploits
repeated patterns that entropy can't see, so a large positive gap
between the two numbers suggests structure beyond a flat byte-value
distribution — worth a closer look, not proof of anything. It can be
slightly negative for small populations, where compression format
overhead outweighs any real redundancy.

## Replication detection (`analysis/replication.py`)

The centerpiece, and the one method faithfully adapted rather than
invented: `replication_scores()` is derived directly from the
reference `cubff` implementation's own `CheckSelfRep` — the actual
method used to produce the "Computational Life" paper's own reported
statistics (e.g. "self-replicators emerged in ~40% of runs"), not a
cheaper stand-in for it.

**The method**, for one candidate 64-byte genome:

1. Run 13 independent trials. Each trial pairs the candidate with a
   *fresh random* 64-byte "noise" genome and executes BFF for
   `max_steps`.
2. Repeat 4 more times per trial: take the resulting right half, pair
   it with the *same* noise genome again, and execute again. (5 chained
   generations total per trial, each against the same noise partner.)
3. After all 13 trials, for each of the 128 final byte positions, check
   whether *some* trial's value at that position recurs in at least 4
   of the 13 trials — and, for left-half positions specifically, also
   matches the original candidate. Positions satisfying this are
   "robust": they come out the same regardless of which random partner
   the candidate was paired against.
4. The score is `min(robust positions in the left half, robust
   positions in the right half)` — an integer from 0 to 64 (or whatever
   the genome length is).

**Why this is the right kind of test**: a genuine, partner-independent
self-copier should produce output that doesn't depend on what it's
paired with. A genome that "replicates" only against one specific lucky
partner isn't really self-replicating — it's this partner-independence
under repeated random pairing that the test actually checks, not
literal byte-for-byte copying (the right half is never required to
equal the original candidate, only to be *consistent* across
independent trials).

**What it doesn't establish**: this is a heuristic consistent with the
reference implementation's own methodology, not a formal proof of
self-replication. `classify()` turns a raw score into a label
(`"high-fidelity replicator candidate"`, `"candidate replicator"`, `"no
replication signal"`) via configurable thresholds (default: ≥90% and
≥50% of genome length respectively) — these are explicitly analytical
labels applied after the fact, never intrinsic simulator properties
(spec section 13).

**Cost**: 13 × 5 = 65 BFF executions per candidate, which is why it's
never run automatically on the whole population — only on demand (one
genome, via the dashboard's genome inspector or `life inspect
--replication-score`) or as a single end-of-run scan over a sample
(sweeps, or the dashboard's "Scan for candidate replicators").
`replication_scores()` is vectorized across candidates using the same
`BatchBffInterpreter` the main epoch loop uses, so scanning e.g. 200
candidates costs roughly the same wall time as one candidate, not 200x.

## Lineage tracking (`analysis/lineage.py`)

`BffSoupUniverse` only ever holds the *current* generation's immediate
parent ids — every population slot gets a fresh organism every epoch
(spec section 9), so reconstructing ancestry across many epochs
requires an explicit, opt-in `LineageRecorder` that snapshots the
universe after each epoch it's called on.

**This is a DAG, not a tree.** Every organism has *two* parents, so two
independent lineages can merge back into one a few generations later.
There is deliberately no "root ancestor per organism" concept anywhere
in this module — for most organisms more than a couple of generations
in, no single well-defined founder exists, since its two parent chains
may trace back to different original seeds. `lineage_graph()` (in
`app/rendering.py`) reflects this honestly: it lays out whichever
ancestors and descendants were actually recorded, by generation, rather
than inventing a single-founder coloring scheme.

**Memory cost is `O(population_size × epochs recorded)`** — one entry
per organism ever created, which is `population_size` new organisms
*every single epoch*. This is stated explicitly, not hidden, so lineage
tracking is opt-in (the dashboard's "Track lineage" toggle, or manually
constructing a `LineageRecorder` in code) and should only be enabled for
runs where following ancestry is actually worth the memory it costs.
