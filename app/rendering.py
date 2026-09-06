"""Pure, UI-framework-independent helpers for rendering a population.

Kept separate from computational_life.core/substrates on purpose: this is
presentation logic (how to lay organisms out on a grid, which cluster id
to color them by), not simulation mechanism or scientific analysis. It
must never feed back into the simulator (spec section 3.2).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from computational_life.substrates.bff.instruction_set import OP_TO_BYTE, Op, decode

if TYPE_CHECKING:
    from computational_life.analysis.lineage import LineageRecorder

DEFAULT_MAX_DISPLAYED_ORGANISMS = 10_000

# One display character per instruction Op, derived from the canonical
# byte encoding rather than duplicated by hand.
_OP_SYMBOL = {op: chr(byte) for op, byte in OP_TO_BYTE.items() if op != Op.NULL}


def grid_shape(n: int) -> tuple[int, int]:
    """A near-square (rows, cols) grid with rows * cols >= n."""
    if n <= 0:
        raise ValueError("n must be positive")
    rows = int(math.floor(math.sqrt(n)))
    rows = max(rows, 1)
    cols = math.ceil(n / rows)
    return rows, cols


def select_display_sample(
    population_size: int, *, max_displayed: int = DEFAULT_MAX_DISPLAYED_ORGANISMS, seed: int = 0
) -> np.ndarray:
    """Indices of organisms to display.

    Returns every index if the population fits within ``max_displayed``,
    otherwise a fixed-seed random subsample -- so large populations are
    visualized cheaply rather than rendering every organism as a heavyweight
    UI element (spec section 16), while staying deterministic across reruns
    of the same population size.
    """
    if population_size <= max_displayed:
        return np.arange(population_size)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(population_size, size=max_displayed, replace=False))


def population_to_highlight_grid(
    population: np.ndarray, *, max_highlighted: int = 12
) -> tuple[np.ndarray, list[dict]]:
    """Lay organisms out on a near-square grid, color-coded by whether
    their genome is *repeated*, not by raw genome identity.

    With 256**genome_length possible 64-byte genomes, an exact duplicate
    arising by chance alone is astronomically unlikely -- so in a
    healthy, diverse population, giving every unique genome its own
    color (as an earlier version of this grid did) makes nearly every
    cell a different, essentially arbitrary color: high-frequency visual
    noise with no information content, since almost nothing actually
    repeats. Any genome that *does* repeat, on the other hand, is
    already a meaningful signal on its own. This highlights up to
    ``max_highlighted`` of the most frequent repeated genomes and
    renders every unique (unrepeated) genome the same neutral value, so
    a real cluster is visible against a quiet background instead of
    blending into rainbow static.

    Grid values: -1 = padding (when rows * cols > len(population)),
    0 = a unique genome, 1..K = rank of a highlighted repeated genome
    (1 = most frequent), K+1 = a repeated genome that didn't make the
    top-K cut (still worth distinguishing from a true unique/singleton).

    Returns (grid, legend); legend is a list of {"rank", "count",
    "frequency"} dicts for the highlighted genomes, most frequent first.
    """
    if population.ndim != 2:
        raise ValueError("population must be a 2D (n_organisms, genome_length) array")
    n = population.shape[0]
    _, inverse, counts = np.unique(population, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)

    repeated = np.where(counts > 1)[0]
    order = repeated[np.argsort(-counts[repeated])]
    highlighted = order[:max_highlighted]
    overflow = order[max_highlighted:]

    rank_lookup = np.zeros(len(counts), dtype=np.int64)
    rank_lookup[highlighted] = np.arange(1, len(highlighted) + 1)
    rank_lookup[overflow] = max_highlighted + 1
    values = rank_lookup[inverse]

    legend = [
        {"rank": rank, "count": int(counts[cid]), "frequency": float(counts[cid]) / n}
        for rank, cid in enumerate(highlighted, start=1)
    ]

    rows, cols = grid_shape(n)
    grid = np.full(rows * cols, -1, dtype=np.int64)
    grid[:n] = values
    return grid.reshape(rows, cols), legend


def genome_symbols(genome: bytes) -> list[tuple[str, str]]:
    """Per-byte (symbol, category) pairs for rendering a genome.

    category is one of "instruction", "null", or "nop" -- spec section 18
    asks that active instructions be visually distinguished from NOP bytes.
    """
    symbols = []
    for byte in genome:
        op = decode(byte)
        if op is Op.NULL:
            symbols.append(("0", "null"))
        elif op is Op.NOP:
            symbols.append((f"{byte:02x}", "nop"))
        else:
            symbols.append((_OP_SYMBOL[op], "instruction"))
    return symbols


_CATEGORY_STYLE = {
    "instruction": "color:#111827; font-weight:700;",
    "null": "color:#9ca3af;",
    "nop": "color:#d1d5db; font-size:0.8em;",
}

# Matches the head0/head1/pc debug colors used by the reference cubff
# implementation's own PrintProgramInternal (blue/red/green respectively).
_HEAD0_BG = "#bfdbfe"
_HEAD1_BG = "#fecaca"
_PC_BG = "#bbf7d0"


def render_tape_html(
    tape: bytes, *, head0: int | None = None, head1: int | None = None, pc: int | None = None
) -> str:
    """Render a tape as monospace HTML spans, one per byte.

    Instruction bytes are bold, the NULL sentinel is muted, and NOP bytes
    are shown as small hex codes (spec section 18's "distinguish active
    instructions from NOP bytes"). When given, head0/head1/pc positions
    are highlighted with a background color, matching the color scheme
    the reference BFF implementation itself uses for its own debug output.
    """
    spans = []
    for i, (symbol, category) in enumerate(genome_symbols(tape)):
        style = _CATEGORY_STYLE[category]
        bg = None
        if pc is not None and i == pc:
            bg = _PC_BG
        elif head0 is not None and i == head0:
            bg = _HEAD0_BG
        elif head1 is not None and i == head1:
            bg = _HEAD1_BG
        if bg:
            style += f" background-color:{bg}; border-radius:3px;"
        spans.append(f'<span style="{style} padding:1px 2px;">{symbol}</span>')
    return (
        '<div style="font-family:monospace; font-size:1.1em; line-height:1.8; '
        'word-break:break-all;">' + "".join(spans) + "</div>"
    )


def instruction_distribution(genome: bytes) -> dict[str, int]:
    """Count of each decoded Op across a genome, keyed by Op name."""
    counts: dict[str, int] = {}
    for byte in genome:
        name = decode(byte).name
        counts[name] = counts.get(name, 0) + 1
    return counts


def lineage_graph(
    recorder: LineageRecorder,
    organism_id: int,
    *,
    max_ancestors: int = 40,
    max_descendants: int = 40,
) -> tuple[dict[int, tuple[float, float]], list[tuple[int, int]]]:
    """Node positions and parent->child edges for a lineage graph centered
    on one organism (spec section 15's "select organism -> show ancestors
    -> show descendants -> show lineage tree").

    Ancestry here is a DAG, not a tree: every organism has *two* parents,
    so two lineages can merge back into one. This deliberately does not
    invent a single "root ancestor" per organism (usually none exists
    once lineages have merged) -- it just lays out whichever ancestors
    and descendants were recorded, positioned by generation (x-axis) with
    an arbitrary vertical spread within each generation to avoid overlap.

    Truncates to the nearest ``max_ancestors``/``max_descendants`` (by
    the recorder's breadth-first order, i.e. closest relatives first) so
    the diagram stays legible for a long, heavily-recorded run. Returns
    (positions, edges); positions maps organism_id -> (x, y).
    """
    ancestors = recorder.ancestors(organism_id)[:max_ancestors]
    descendants = recorder.descendants(organism_id)[:max_descendants]
    node_ids = {organism_id, *ancestors, *descendants}

    by_generation: dict[int, list[int]] = {}
    for oid in node_ids:
        by_generation.setdefault(recorder.generation(oid), []).append(oid)

    positions: dict[int, tuple[float, float]] = {}
    for gen, ids in by_generation.items():
        ids = sorted(ids)
        offset = (len(ids) - 1) / 2
        for i, oid in enumerate(ids):
            positions[oid] = (float(gen), i - offset)

    edges: list[tuple[int, int]] = []
    for oid in node_ids:
        parents = recorder.parents(oid)
        if not parents:
            continue
        for parent_id in parents:
            if parent_id in node_ids:
                edges.append((parent_id, oid))

    return positions, edges
