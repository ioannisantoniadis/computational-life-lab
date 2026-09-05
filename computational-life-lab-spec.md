# Computational Life Lab — Agent Implementation Specification

## 1. Project vision

Build an open-source experimental platform for studying **emergence, evolution, self-replication, complexity, and intelligence-like behavior in minimal computational universes**.

The central philosophy is:

> Start with extremely simple computational rules and no explicitly designed intelligence, then observe what structures and capabilities emerge.

The first and most important experiment is a polished implementation of the BFF computational-life primordial soup. The architecture should then make it possible to build other computational substrates and experiments without rewriting the simulator.

This is a **research/experimental laboratory**, not merely a game or a Brainfuck interpreter.

---

## 2. Initial scope

Do NOT attempt to implement the entire long-term vision immediately.

The first milestone should be a complete, scientifically useful BFF experiment:

```text
random 64-byte programs
        ↓
random interactions
        ↓
BFF execution / self-modification
        ↓
replacement / inheritance
        ↓
emergent structure
        ↓
replicators, if they arise
        ↓
visualization + quantitative analysis
```

The initial implementation should answer:

- Can self-replicators emerge?
- When do they emerge?
- How often do they emerge across random seeds?
- What do their genomes look like?
- How do they spread?
- What happens to population diversity?
- What lineages lead to successful replicators?

Do not hard-code any of these outcomes.

---

# 3. Design principles

### 3.1 Emergence must be genuine

Do NOT implement:

```python
if looks_like_replicator(organism):
    reproduce()
```

or equivalent hidden mechanisms.

Reproduction, competition, persistence, etc. should arise from the computational rules.

### 3.2 Separate mechanism from observation

The simulator defines:

- state
- computation
- interaction
- mutation
- replacement

The analysis layer observes:

- replication
- diversity
- entropy
- species-like clusters
- parasites
- complexity

Do not make observational classifications part of the simulation dynamics unless explicitly configured as an experimental mechanism.

### 3.3 Reproducibility

Every run must be reproducible from:

- experiment configuration
- random seed
- software version
- initial state, when applicable

### 3.4 UI-independent core

The simulation engine must have no dependency on Streamlit or UI code.

The same experiment must be runnable from Python/CLI and from the UI.

### 3.5 Research-grade observability

The system should make it easy to inspect exactly why an observed behavior occurred.

---

# 4. Technology

Initial stack:

- Python 3.12+
- NumPy where useful
- Streamlit for UI
- pandas for analysis
- Plotly or native Streamlit-compatible plotting for interactive charts
- SQLite for experiment metadata/results
- pytest for tests
- YAML for experiment configuration

Use a `pyproject.toml`-based package.

Keep dependencies minimal.

Do not prematurely introduce C++, Rust, distributed systems, or complex infrastructure.

Design the interpreter boundary so a future optimized backend (Numba/Rust/etc.) can be added without changing the experiment/UI APIs.

---

# 5. Repository structure

Use approximately:

```text
computational-life/
│
├── src/
│   └── computational_life/
│       ├── core/
│       │   ├── universe.py
│       │   ├── organism.py
│       │   ├── interpreter.py
│       │   ├── instruction_set.py
│       │   ├── interaction.py
│       │   ├── mutation.py
│       │   ├── reproduction.py
│       │   ├── scheduler.py
│       │   └── rng.py
│       │
│       ├── substrates/
│       │   └── bff/
│       │       ├── interpreter.py
│       │       ├── instruction_set.py
│       │       └── universe.py
│       │
│       ├── experiments/
│       │   ├── base.py
│       │   └── bff_soup.py
│       │
│       ├── analysis/
│       │   ├── replication.py
│       │   ├── entropy.py
│       │   ├── diversity.py
│       │   ├── complexity.py
│       │   ├── lineage.py
│       │   └── statistics.py
│       │
│       ├── storage/
│       │   ├── database.py
│       │   └── checkpoints.py
│       │
│       └── cli.py
│
├── app/
│   └── streamlit_app.py
│
├── experiments/
│   └── configs/
│       └── bff_baseline.yaml
│
├── tests/
│
├── docs/
│
├── README.md
├── pyproject.toml
└── LICENSE
```

Exact structure can vary if the agent has a better reason, but maintain the architectural separation.

---

# 6. Generic computational universe

Create a generic abstraction roughly equivalent to:

```python
Universe
    state
    population
    rules
    interpreter
    scheduler
    mutation_model
    metrics
```

A universe should define:

### State

Persistent computational state.

### Rules

What happens when entities interact.

### Interpreter

How an organism/program executes.

### Scheduler

Which organisms interact and in what order.

### Mutation model

How variation enters the system.

### Measurements

What quantities are recorded.

The BFF implementation should specialize this abstraction rather than define the entire simulator around BFF-specific assumptions.

---

# 7. Organism model

An organism should contain at least:

```text
organism_id
genome
birth_time
parent_id
generation
```

Prefer immutable genome representations where practical.

Track ancestry through a lineage graph.

Example:

```text
ancestor
   │
   ├── A
   │   ├── A1
   │   └── A2
   │
   └── B
       ├── B1
       └── B2
```

Do not store unnecessary per-step organism history in memory. Use event recording/checkpointing selectively so large populations remain feasible.

---

# 8. BFF substrate

Implement the BFF computational substrate used in the computational-life experiments.

Default parameters:

```yaml
population_size: 131072
genome_length: 64
combined_length: 128
```

Each organism initially consists of a random 64-byte tape.

The tape is both program and data.

Use byte values `0..255`.

Only the defined instruction bytes have semantics; other byte values are NOPs.

The active instruction set is:

```text
<  move head 0 left
>  move head 0 right
+  increment byte at head 0
-  decrement byte at head 0
,  copy head 1 -> head 0
.  copy head 0 -> head 1
[  conditional loop
]  conditional loop
```

Use the exact BFF semantics established by the reference experiment/paper/book being implemented. Document any interpretation decisions explicitly.

Pointers should wrap around the tape.

Byte arithmetic should wrap around `0..255`.

Execution must have a configurable maximum number of instructions to prevent nontermination.

Unknown byte values are NOPs.

---

# 9. BFF interaction

Baseline experiment:

```text
1. Start with N random 64-byte genomes.
2. Randomly pair organisms.
3. Concatenate the two 64-byte genomes into a 128-byte tape.
4. Execute the combined tape according to BFF semantics.
5. Split the resulting tape into two 64-byte genomes.
6. Replace the original pair with the resulting pair.
7. Repeat.
```

The baseline should have:

```text
explicit_fitness: false
mutation: configurable, default false
interaction: random pairing
```

The absence of an explicit fitness function is essential.

The simulator should not preferentially preserve organisms because they are "good".

---

# 10. Deterministic random number generation

Use an explicit RNG object throughout the simulation.

Every experiment must accept a seed.

Example:

```yaml
experiment: bff_soup
seed: 12345

population:
  size: 131072
  genome_length: 64

execution:
  max_steps: 8192

interaction:
  strategy: random_pairing

mutation:
  enabled: false
```

Running the same configuration and seed should produce the same result, subject to documented numerical/backend guarantees.

Do not use uncontrolled calls to the global Python random generator.

---

# 11. Execution model

The interpreter must expose a debuggable execution state.

At minimum:

```text
tape
instruction_pointer
head0
head1
step_count
halted
```

Provide:

```python
step()
run(max_steps)
reset()
```

`step()` should execute exactly one instruction and make the resulting state inspectable.

The execution engine must be testable independently from the universe.

---

# 12. Execution debugger

Build a debugger capable of showing:

```text
instruction pointer
head0
head1
current instruction
tape contents
modified cells
step count
```

Support:

```text
Run
Pause
Step
Reset
```

The UI should make it possible to inspect a specific organism/program and understand its execution.

This is not optional polish; it is part of the project's scientific/educational value.

---

# 13. Replication detection

Implement replication detection as an **analysis module**, not as a simulation mechanism.

A candidate replicator should be identified based on observed computational outcomes.

Possible measurements:

```text
genome similarity
copy fidelity
offspring production
replication frequency
generation time
descendant abundance
```

Support configurable similarity thresholds.

Classifications may include:

```text
candidate replicator
high-fidelity replicator
partial replicator
candidate parasite
candidate hyperparasite
```

These are analytical classifications, not intrinsic simulator properties.

Document every classification rule.

Avoid claiming "this is a parasite" unless the implemented detector actually supports that conclusion.

---

# 14. Metrics

Record metrics over time.

## Population

```text
population size
number of unique genomes
dominant genome frequency
genome-frequency distribution
```

## Diversity

```text
Shannon entropy
genotype diversity
instruction distribution
```

## Evolution

```text
mutation rate
lineage depth
generation count
genome persistence
replication frequency
```

## Emergence

```text
first candidate replicator
time to first replicator
replicator probability across seeds
replicator takeover time
number of independent origins
```

## Complexity

Start with practical proxies:

```text
genome compressibility
instruction entropy
unique sequence counts
behavioral diversity where measurable
```

Do not label any one proxy "the complexity of the organism". Call them explicitly "complexity proxies".

---

# 15. Lineage tracking

Maintain parent-child relationships.

The UI should support:

```text
select organism
→ show ancestors
→ show descendants
→ show lineage tree
```

Allow coloring the population by lineage.

A user should be able to identify where a successful replicator originated and watch its lineage spread.

---

# 16. Visualization

The Streamlit UI should have a main experiment dashboard.

## Universe view

Display the population as a grid.

Each cell represents an organism.

Allow coloring by:

```text
genome identity
lineage
generation
age
instruction composition
replication status
```

For large populations, aggregate/visualize efficiently rather than attempting to render every organism as a heavyweight UI element.

The user should be able to watch population structure evolve.

---

# 17. Time controls

Provide:

```text
Play
Pause
Step
Fast-forward
Speed control
Jump to event
```

Example event:

```text
First candidate replicator detected at epoch 18,392
```

Clicking the event should load the nearest checkpoint and navigate the visualization to that region/time where possible.

---

# 18. Genome inspector

Clicking an organism should display:

```text
organism ID
genome
parent ID
generation
age
lineage
replication statistics
genome length
instruction distribution
```

Render the genome as a byte/instruction sequence and distinguish active instructions from NOP bytes.

---

# 19. Metrics dashboard

Provide live charts for:

```text
genome diversity
entropy
dominant genome frequency
instruction frequencies
candidate replicator count/frequency
lineage depth
complexity proxies
```

Allow zooming and inspecting historical values.

Do not make charts visually misleading: label all axes and units and clearly distinguish raw metrics from derived metrics.

---

# 20. Experiment configuration

Experiments should be defined by YAML or equivalent structured configuration.

Example:

```yaml
experiment: bff_soup

seed: 12345

population:
  size: 131072
  genome_length: 64

execution:
  max_steps: 8192

interaction:
  strategy: random_pairing

mutation:
  enabled: false
  rate: 0.0

analysis:
  replication_detection: true
  lineage_tracking: true

checkpointing:
  interval: 1000
```

The UI should expose the important parameters as controls.

---

# 21. First experiment presets

Implement these sequentially.

## 001 — Dead Soup

A null/baseline computational system with dynamics designed to make clear what happens without the relevant self-modification/reproduction mechanism.

Purpose:

Establish a baseline and validate that analysis tools do not manufacture apparent emergence.

## 002 — BFF Emergence

Canonical BFF primordial soup.

Question:

> Do self-replicators spontaneously emerge?

## 003 — Mutation sweep

Vary mutation rate.

Question:

> How does mutation affect emergence and persistence?

## 004 — Population-size sweep

Run multiple population sizes.

Example:

```text
256
1024
4096
16384
65536
131072
```

Question:

> How does system size affect emergence probability?

## 005 — Genome-length sweep

Example:

```text
16
32
64
128
256
```

Question:

> How does genome length affect emergence?

## 006 — Instruction ablation

Remove one instruction at a time.

Question:

> Which primitive operations appear necessary for spontaneous replication?

Only introduce this once the baseline interpreter is verified.

---

# 22. Batch experiments

Support parameter sweeps.

Example:

```yaml
sweep:
  population_size:
    - 256
    - 1024
    - 4096

  mutation_rate:
    - 0
    - 0.0001
    - 0.001

  seeds:
    count: 100
```

The system should execute independent runs and store results.

The output should support questions such as:

```text
P(replicator | population size)
P(replicator | mutation rate)
median emergence time
distribution of emergence times
```

Do not report statistically meaningful conclusions from a tiny number of runs; display sample sizes.

---

# 23. Storage

Use SQLite initially.

Store enough metadata to reproduce and analyze experiments:

```text
experiment
run
configuration
seed
software version
metrics
events
lineage metadata
checkpoints
```

Avoid writing every interpreter instruction to SQLite. High-frequency execution traces should only be recorded for explicit debugging/inspection runs.

---

# 24. Checkpointing

Support:

```text
save checkpoint
load checkpoint
automatic checkpoints
```

A checkpoint should include:

```text
universe state
RNG state
configuration
simulation time
metrics state
lineage state
software/version metadata
```

Checkpoint restoration should produce the same subsequent trajectory as uninterrupted execution for the same backend.

---

# 25. CLI

Provide a simple CLI.

Examples:

```bash
life run experiments/configs/bff_baseline.yaml
```

```bash
life sweep experiments/configs/bff_sweep.yaml
```

```bash
life analyze RUN_ID
```

```bash
life inspect RUN_ID --organism ORGANISM_ID
```

The CLI should not depend on Streamlit.

---

# 26. UI pages

Start with:

### Home

Explain the project and show recent experiments.

### Experiment

Configure and run an experiment.

### Live simulation

Watch the universe evolve.

### Organism

Inspect an individual genome/execution.

### Lineage

Explore ancestry.

### Analysis

Explore metrics and derived observations.

### Runs

Compare historical runs.

Keep the UI simple and scientific rather than game-like.

---

# 27. Scientific terminology

Be careful with anthropomorphic language.

Prefer:

```text
candidate replicator
selection-like dynamics
species-like cluster
complexity proxy
information-processing behavior
```

rather than asserting biological equivalence.

The goal is to study analogues of biological phenomena in computational systems.

---

# 28. Testing

Write tests before optimizing.

## Interpreter tests

- pointer wrapping
- byte wrapping
- increment/decrement
- copy operations
- loop behavior
- NOP behavior
- self-modification
- execution limit

## Universe tests

- deterministic seeds
- population initialization
- random pairing
- concatenation
- execution
- splitting
- replacement
- checkpoint restoration

## Analysis tests

- entropy
- diversity
- genome similarity
- replication detection
- lineage construction

## Regression tests

Include known small programs/genomes with expected execution traces.

---

# 29. Performance targets

Initial goal:

- Correct Python implementation first.
- Efficient NumPy/data-oriented structures where beneficial.
- Avoid Python object-per-byte designs for large populations.
- Avoid unnecessary copies of 128-byte tapes.
- Profile before optimizing.

The first implementation should be capable of experimenting with populations in the thousands comfortably.

Then optimize toward the canonical large population.

Do not sacrifice correctness for performance.

---

# 30. Documentation

README should immediately communicate:

```text
random computation
        ↓
interaction
        ↓
self-modification
        ↓
structured computation
        ↓
self-replication
        ↓
evolutionary dynamics
        ↓
?
```

Include:

- project motivation
- architecture
- how to run the first experiment
- explanation of BFF
- reproducibility instructions
- screenshots/GIFs once available
- scientific references
- limitations
- future experiments

Document the exact computational semantics used.

---

# 31. Development process for the coding agent

Do NOT implement all phases in one giant change.

Work incrementally:

## Phase 1 — Core + BFF

Implement:

- project structure
- BFF instruction set
- interpreter
- tests
- random population
- interaction loop
- deterministic RNG
- CLI

Deliverable:

A correct headless BFF primordial soup.

## Phase 2 — Visualization

Implement:

- Streamlit app
- population grid
- controls
- metrics
- genome inspector
- execution debugger

Deliverable:

A polished interactive experiment.

## Phase 3 — Analysis

Implement:

- replication detection
- lineage tracking
- diversity
- entropy
- complexity proxies
- event detection

Deliverable:

A scientifically useful analysis environment.

## Phase 4 — Reproducibility

Implement:

- SQLite
- run metadata
- checkpoints
- parameter sweeps
- run comparison

Deliverable:

Repeatable experiments across many seeds.

## Phase 5 — Generalization

Only after the BFF system is solid:

- generic substrates
- generic instruction sets
- generic interaction models
- alternative interpreters

Deliverable:

A framework for computational-life experiments beyond BFF.

---

# 32. Future research directions

Do not implement these initially, but design the architecture so they are possible.

### Spatial universes

Compare:

```text
global random interactions
1D locality
2D locality
nearest-neighbor
small-world
```

### Resources and explicit selection

Introduce:

```text
energy
resources
limited computation
environmental constraints
```

Then compare spontaneous dynamics with explicit selection.

### Parasites

Investigate whether genomes that exploit other replicators emerge.

### Cooperation

Investigate whether mutually beneficial interactions emerge.

### Communication

Give organisms mechanisms through which one organism can influence another.

### Alternative substrates

Implement:

```text
Brainfuck variants
SUBLEQ
Forth-like machines
register machines
cellular automata
custom bytecode
```

### Intelligence experiments

Eventually introduce environments where organisms must process information to gain resources or reproduce.

Potential capabilities to measure:

```text
memory
prediction
communication
planning
environmental modeling
problem solving
```

These should emerge from the substrate rather than being hard-coded as "intelligence".

---

# 33. Long-term scientific goal

The eventual research question is:

> **What properties of a computational substrate make it fertile for the emergence of life-like and intelligence-like behavior?**

This motivates systematic comparisons between substrates, interaction topologies, mutation models, population sizes, and environmental constraints.

The project should eventually make experiments like this easy:

```text
              COMPUTATIONAL SUBSTRATE
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
        BFF          SUBLEQ       Custom VM
          │            │            │
          └────────────┼────────────┘
                       ↓
              Same experimental protocol
                       ↓
             emergence statistics
                       ↓
              comparative analysis
```

The platform should make it possible to ask whether emergence depends on:

- computational universality
- self-reference
- instruction-set structure
- locality
- interaction
- mutation
- selection
- population size
- geometry of program space
- existence of short replicators

---

# 34. Important implementation constraint

The project must remain honest about what is actually being demonstrated.

For every experiment, clearly separate:

### Mechanism

What the simulator explicitly implements.

### Observation

What happened during the run.

### Interpretation

What the observation might mean.

For example:

```text
Mechanism:
random pairing + BFF execution + replacement

Observation:
a genome increased from 1 individual to 43,000 individuals

Interpretation:
candidate self-replication and selection-like dynamics
```

Never silently turn interpretation into simulation rules.

---

# 35. Definition of done for the first milestone

The first milestone is complete when:

1. A random BFF population can be initialized.
2. The BFF interpreter passes comprehensive semantic tests.
3. Random pairing and execution work deterministically from a seed.
4. The full experiment can run without the UI.
5. The Streamlit UI can launch and visualize a run.
6. The population can be watched evolving over time.
7. Individual genomes can be inspected.
8. Individual execution can be stepped through.
9. Lineages can be inspected.
10. Basic diversity/entropy metrics are displayed.
11. Candidate replicators can be detected from observations.
12. Runs can be saved and reproduced.
13. Multiple seeds can be compared.
14. The README explains how to reproduce the baseline experiment.
15. No mechanism explicitly rewards or preserves replicators.

---

# 36. Agent behavior

Act as a careful research software engineer.

Before implementing each phase:

1. Understand the existing architecture.
2. Identify assumptions.
3. Implement the smallest coherent increment.
4. Write/update tests.
5. Run tests.
6. Run a small experimental sanity check.
7. Document the result.

Do not continuously refactor working code without a concrete reason.

Do not add dependencies without justification.

Do not optimize before profiling.

Do not hide scientific assumptions inside utility functions.

When a scientific definition is ambiguous, make it configurable and document the choice.

The most important properties are:

**correctness → reproducibility → observability → extensibility → performance**

in that order.

---

# 37. Suggested first commit sequence

```text
1. Initialize package + CI + pytest
2. Implement BFF instruction semantics
3. Add interpreter tests
4. Implement organisms/population
5. Implement random pairing + universe loop
6. Add deterministic seeds
7. Add CLI
8. Add baseline BFF experiment
9. Add metrics
10. Add Streamlit visualization
11. Add genome debugger
12. Add lineage tracking
13. Add replication analysis
14. Add persistence/checkpoints
15. Add parameter sweeps
```

At every step, keep the project runnable.

---

# 38. References

The implementation should consult and cite the original/reference work describing computational life and BFF semantics.

Primary references include:

- *What is Intelligence?* — Blaise Agüera y Arcas
- The Computational Life project/material accompanying the book
- *Computational Life: How to Create Intelligence from Simple Programs* and associated papers/preprints
- Avida and Tierra as historical artificial-life context
- Relevant subsequent work investigating alternative routes to discovering computational replicators

Do not assume that all terminology or semantics from secondary implementations are correct. Where possible, derive the baseline implementation from the primary/reference description and document deviations.

---

# Final instruction

Build **the smallest serious computational-life laboratory**, not the largest feature set.

The first success criterion is not "many features."

It is:

> **I can press Run, start from computational noise, watch the universe evolve, notice something strange happening, click on it, inspect its genome, step through its computation, follow its lineage, and quantitatively determine what actually happened.**

Everything else should grow from that.
