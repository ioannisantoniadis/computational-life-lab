# BFF semantics: source and resolved decisions

This document records the primary sources consulted for BFF's exact
computational semantics, the specific ambiguities/omissions found in
`computational-life-lab-spec.md`, and how each was resolved. Per the
spec's own instruction (section 38): "do not assume that all terminology
or semantics from secondary implementations are correct... derive the
baseline implementation from the primary/reference description and
document deviations."

## Sources

1. Agüera y Arcas, Alakuijala, Evans, Laurie, Mordvintsev, Niklasson,
   Randazzo, Versari. *Computational Life: How Well-formed,
   Self-replicating Programs Emerge from Simple Interaction*.
   [arXiv:2406.19108](https://arxiv.org/abs/2406.19108).
2. [`paradigms-of-intelligence/cubff`](https://github.com/paradigms-of-intelligence/cubff) —
   the paper authors' own reference implementation (Apache-2.0, Google
   LLC). Most experiments in the paper were run with this code. The exact
   ISA and execution semantics below are read directly from `bff.inc.h`
   and `common_language.h` in that repository (accessed 2026-09).

Only the *semantics* (instruction meanings, byte encoding, control flow,
default parameters) are derived from cubff; no code from that repository
is copied into this project.

## Resolved decisions

### 1. The instruction set has 10 operations, not 8

`computational-life-lab-spec.md` section 8 lists only 8 characters
(`< > + - , . [ ]`), omitting `{` and `}` (move head1 left/right). Without
them, head1 never moves from its initial position, which breaks the
copy mechanism (`.`/`,`) the paper's self-replicators rely on.

**Decision:** implement the full 10-instruction set from `bff.inc.h`:
`< > + - . , [ ] { }`, with `< >` moving head0 and `{ }` moving head1.
This is treated as a correction of an incomplete paraphrase in the spec,
per section 38's instruction to derive semantics from the primary source.

### 2. Byte encoding is literal ASCII, plus one reserved sentinel

The reference implementation switches on the raw byte value using its
ASCII code: `[`=0x5B `]`=0x5D `+`=0x2B `-`=0x2D `.`=0x2E `,`=0x2C `<`=0x3C
`>`=0x3E `{`=0x7B `}`=0x7D. Byte value `0x00` is a distinct **NULL**
sentinel — the value tested by `[`/`]` for loop control. Every other byte
value (about 245 of the 256 possible) is a plain NOP when executed as an
instruction.

**Decision:** use the literal ASCII codes for the 10 instructions and
reserve byte 0 as NULL, exactly as in the reference. This makes genomes
and execution traces directly comparable to any BFF material published
elsewhere. See `substrates/bff/instruction_set.py`.

Importantly, `[`/`]` test whether the byte at head0 is *exactly* 0
(NULL) — not whether it "looks like a no-op." A NOP byte with value, say,
200, is truthy for loop-condition purposes.

### 3. Loop semantics and unmatched-bracket behavior

- `[`: if `tape[head0] == NULL`, skip forward to the instruction
  immediately after the matching `]` (loop body not entered). Otherwise
  fall through into the loop body.
- `]`: if `tape[head0] != NULL`, jump back to the instruction immediately
  after the matching `[` (the `[` itself is not re-executed). Otherwise
  fall through past the loop.
- Bracket matching never wraps around the tape. If the forward or
  backward scan reaches the end of the tape without finding a match,
  **execution halts immediately** — this is not a NOP and not a wrapped
  search.

This is confirmed byte-for-byte against `EvaluateOne` in `bff.inc.h`.

### 4. Head initialization: "noheads" is the Phase 1 default

Two variants exist in the reference:

- `bff.cu` (`BFF_HEADS` defined): head0/head1 are read from the tape's
  own first two bytes (`tape[0]`, `tape[1]`, each wrapped into range);
  execution starts at `pc = 2`.
- `bff_noheads.cu`: head0 = head1 = 0; execution starts at `pc = 0`.

The `cubff` README's own quick-start command (`bin/main --lang
bff_noheads`) and its example Python script both use the "noheads"
variant.

**Decision:** implement `head_init="zero"` (the noheads variant) as the
Phase 1 default, matching the paper's own quick-start baseline. The
`head_init="from_tape"` variant is also implemented (both interpreters
accept a `head_init` parameter) so the "heads" variant can be selected
later without changing the interpreter core.

### 5. "Random pairing... repeat" means one epoch = one full random perfect matching

The spec's flowchart (sections 2 and 9) does not specify whether
"repeat" means repeating single random pairings one at a time, or
re-pairing the whole population at once. The reference implementation's
main loop (`RunSimulation` in `common_language.h`) does the latter: each
epoch, it Fisher–Yates shuffles the full index array and pairs up
consecutive slots, so every organism interacts with exactly one partner
per epoch, and all pairs execute simultaneously (in the CUDA/SIMT sense).

**Decision:** adopt "epoch" (matching the reference's own `state.epoch`)
as the unit of simulated time: one epoch = shuffle the whole population,
pair up consecutive indices, execute all pairs, replace all slots. This
is both more faithful to the primary source and what makes the whole
population vectorizable (see `substrates/bff/vectorized.py`).

### 6. Mutation, when enabled, replaces whole bytes

The reference applies mutation to every byte of the combined 128-byte
tape independently, before execution: with probability `mutation_prob`
(default 2⁻¹² in cubff), a byte is replaced by a uniformly random byte
value (not incremented, not bit-flipped).

**Decision:** implement the same full-byte-replacement mutation model,
as a configurable per-byte probability. The Phase 1 default stays
`mutation.enabled: false`, matching `computational-life-lab-spec.md`
sections 9/10/20 exactly — the baseline experiment's entire point is to
show emergence *without* mutation.

### 7. Default execution budget: 8192 steps per pairing

Matches the spec's own example config and the reference's literal
`Evaluate(tape, 8 * 1024, ...)` call.

### 8. Random number generation is *not* bit-matched to the reference

cubff derives all randomness from `SplitMix64`, a technique suited to
lock-free parallel (CUDA) determinism. This project uses NumPy's
`Generator(PCG64)`, seeded via `SeedSequence.spawn()` into independent
substreams for population init / pairing / mutation (see
`core/rng.py`). Runs are fully reproducible from (config, seed) under
this project's own RNG, but will **not** produce byte-identical
trajectories to cubff given "the same" seed — the two implementations
draw from different, independent random streams by construction. This is
expected and does not affect scientific validity: reproducibility is
about a run being self-consistent under its own documented RNG scheme,
not about cross-implementation bit-matching.

## Not yet resolved / out of Phase 1 scope

- The reference's built-in replicator heuristic (`CheckSelfRep`: run a
  candidate genome against several independent noise partners across a
  few generations and check for consistency) was deliberately **not**
  implemented in Phase 1 — Phase 1 must not embed any replication
  classification into the simulator itself (spec section 3.1/13). It is
  now implemented, faithfully adapted from the same reference algorithm,
  as an analysis-layer module: `analysis/replication.py`. It is never
  called from `substrates/bff/universe.py` — only from the analysis layer
  and the UI, on demand.
