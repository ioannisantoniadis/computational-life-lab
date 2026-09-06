# Documentation index

The top-level [`README.md`](../README.md) covers installation and a
quickstart. Everything else lives here:

- [**`artificial_life_background.md`**](artificial_life_background.md)
  — what artificial life research is asking, the lineage of
  self-replicating/evolving computational systems this project sits in
  (von Neumann, Core War, Tierra, Avida), and how BFF/"Computational
  Life" and this platform's longer-term goals fit into that tradition.
- [**`bff_semantics.md`**](bff_semantics.md) — the exact BFF instruction
  set, byte encoding, and control-flow rules this project implements,
  derived from the primary reference implementation, with every place
  the project spec's own paraphrase needed correcting.
- [**`configuration.md`**](configuration.md) — full field-by-field
  reference for both YAML config kinds (`bff_soup`, `bff_soup_sweep`),
  their defaults, and the shipped example configs.
- [**`cli_reference.md`**](cli_reference.md) — every `life` subcommand,
  what it does, and worked examples.
- [**`dashboard_guide.md`**](dashboard_guide.md) — a walkthrough of every
  section of the Streamlit dashboard.
- [**`analysis_methods.md`**](analysis_methods.md) — how diversity,
  entropy, complexity proxies, replication detection, and lineage
  tracking actually work, and what each does and doesn't establish.
