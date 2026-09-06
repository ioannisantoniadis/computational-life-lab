# Artificial life: background and context

This project sits inside a specific research tradition. This document
sketches that tradition, situates BFF and the "Computational Life"
paper within it, and names the long-term research question the
platform is built to let someone eventually ask across substrates —
none of which is necessary to *run* the software (see the top-level
[`README.md`](../README.md) for that), but all of which is useful for
understanding *why* it's built the way it is.

## What "artificial life" is asking

Artificial life (often "ALife") studies life-like processes — self-
replication, evolution, adaptation, open-ended complexity growth — by
building and running minimal computational or physical systems that
exhibit them, rather than only observing biological organisms. The
recurring wager across the field: if a simple, fully-specified,
fully-observable system spontaneously produces something that looks
like replication or evolution, that tells you something general about
the *conditions* under which such processes can arise — not just about
carbon-based life's particular history.

This project's version of that wager, stated directly in the spec this
codebase implements: *"the simulator must not know what the
experimenter hopes to discover."* No fitness function, no explicit
selection, no hard-coded notion of "replicator" anywhere in the
mechanism (see [`../README.md`](../README.md#status) and spec section
3.1). Anything that looks like replication or evolution has to come
out of raw interaction dynamics, or it doesn't count.

## A lineage of self-replicating/evolving computational systems

### Von Neumann's universal constructor (1940s-1966)

John von Neumann asked, in the late 1940s, whether a machine could
build a copy of itself as a special case of being able to build
*anything* — a "universal constructor." He worked this out formally in
a cellular automaton with 29 possible states per cell, proving a
self-reproducing configuration was possible in principle. The work was
unfinished at his death in 1957 and was completed and published
posthumously by Arthur W. Burks as *Theory of Self-Reproducing
Automata* (1966). It wasn't actually run on a computer until Umberto
Pesavento's 1994 implementation — the proof long predated the
demonstration. This is the conceptual ancestor of every self-
replicating-program experiment since, including this one: it's the
first place "a program that constructs a copy of itself" was treated as
a rigorous, checkable claim rather than a metaphor.

### Core War (1984)

D. G. Jones and A. K. Dewdney's *Core War* (Redcode assembly programs
competing for control of a shared circular memory, popularized in
Dewdney's May 1984 *Scientific American* "Computer Recreations" column)
was a game, not a research platform, but it demonstrated something
that turned out to matter: self-replicating and self-modifying programs
sharing one address space produce complex, hard-to-predict competitive
dynamics essentially for free, just from the shared-memory,
mutual-interference structure. BFF's "two genomes concatenated into
one 128-byte tape, executed together" setup is a direct structural
descendant of this idea — interaction *is* physical adjacency in a
shared memory/tape, not a modeled "encounter."

### Tierra (Ray, 1991)

Thomas S. Ray's *Tierra* was the first system to combine self-
replicating machine-code creatures, mutation, and a shared, finite
resource (CPU time, allocated round-robin, with the oldest/buggiest
programs reaped first) into something that produced genuinely
Darwinian dynamics — parasites, hyper-parasites, and unplanned
ecological structure emerged from evolutionary pressure the
experimenter never specified. Tierra *does* have an implicit selection
pressure, though (faster/shorter replicators get more CPU time and
survive culling), which is exactly the ingredient the BFF/"Computational
Life" line of work set out to remove.

> Ray, T. S. (1991). *An Approach to the Synthesis of Life.* In
> Langton, C., Taylor, C., Farmer, J. D., & Rasmussen, S. (eds),
> *Artificial Life II*, Santa Fe Institute Studies in the Sciences of
> Complexity, vol. XI, pp. 371-408. Addison-Wesley.

### Avida (Ofria & Wilke, 2004)

*Avida* generalized Tierra's approach into an actively-maintained
research platform still used in evolutionary biology today: digital
organisms execute a simple instruction set, replicate, mutate, and
compete for CPU cycles on a spatial grid, with experimenters able to
reward specific computations (e.g. logic functions) to study how
complex traits evolve stepwise. Like Tierra, Avida's organisms compete
under an explicit resource-allocation scheme — a designed selection
pressure, even when no specific *task* is rewarded.

> Ofria, C., & Wilke, C. O. (2004). *Avida: A Software Platform for
> Research in Computational Evolutionary Biology.* Artificial Life,
> 10(2), 191-229.

### Computational Life / BFF (Agüera y Arcas et al., 2024)

The paper this project directly implements asks a sharper version of
the same question: can self-replication emerge with **no** designed
selection mechanism at all — no CPU-time allocation, no culling, no
task reward — just random pairing, self-modifying execution, and
replacement? BFF (an extension of Brainfuck where the two I/O
instructions become "copy between two tape heads" instead) is the
minimal substrate chosen to test this. When it works, the paper's
claim is stronger than Tierra's or Avida's: it isn't "evolution found a
better replicator under selection pressure I designed," it's
"replication itself spontaneously appeared with no selection pressure
provided at all."

> Agüera y Arcas, B., Alakuijala, J., Evans, J., Laurie, B., Mordvintsev,
> A., Niklasson, E., Randazzo, E., & Versari, L. (2024). *Computational
> Life: How Well-formed, Self-replicating Programs Emerge from Simple
> Interaction.* [arXiv:2406.19108](https://arxiv.org/abs/2406.19108).

See [`bff_semantics.md`](bff_semantics.md) for exactly how this
project's implementation was derived from that paper's own reference
code, byte for byte, and every place the project spec's paraphrase of
BFF's rules needed correcting against the primary source.

## Where this project sits, and where it's headed

Phases 1-4 (see the [README](../README.md#status)) implement the BFF
experiment itself, faithfully, plus the observability and
reproducibility machinery (dashboard, storage, checkpointing, sweeps)
needed to actually run it at scale and interrogate the results — all
built, per the project's own architectural principle, so that none of
it can leak back into the simulation as a hidden selection mechanism
(see [`analysis_methods.md`](analysis_methods.md) for how replication
detection stays purely observational).

Phase 5, deliberately not started yet, is where the project's longer
research question actually lives: BFF is one point in a much larger
space of possible substrates (SUBLEQ, Forth-like machines, register
machines, custom bytecodes — see the spec's section 32), and the field
this project is part of ultimately wants to know *which properties of a
substrate* make it fertile ground for spontaneous replication and
increasing complexity: instruction-set structure, self-reference,
locality/interaction topology, mutation rate, population size, or
something else. Answering that requires running the same experimental
protocol (population, pairing, execution, replacement, measurement)
across genuinely different substrates and comparing — which is exactly
why Phase 1-4's architecture keeps the substrate (`substrates/bff/`)
behind a boundary the rest of the system doesn't reach through.
