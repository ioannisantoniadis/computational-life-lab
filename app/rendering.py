"""Pure, UI-framework-independent helpers for rendering a population.

Kept separate from computational_life.core/substrates on purpose: this is
presentation logic (how to lay organisms out on a grid, which cluster id
to color them by), not simulation mechanism or scientific analysis. It
must never feed back into the simulator (spec section 3.2).
"""

from __future__ import annotations

import math

import numpy as np

from computational_life.substrates.bff.instruction_set import OP_TO_BYTE, Op, decode

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


def population_to_cluster_grid(population: np.ndarray) -> tuple[np.ndarray, int]:
    """Assign each displayed organism a genome-identity cluster id and lay
    it out on a near-square grid.

    Identical genomes get identical cluster ids (so identical-genome
    clusters are visually apparent as same-colored regions); the mapping
    from id to genome is arbitrary (lexicographic order of unique genomes)
    and carries no scientific meaning on its own. Padding cells (when
    rows * cols > len(population)) are filled with -1.

    Returns (grid, num_unique_genomes).
    """
    if population.ndim != 2:
        raise ValueError("population must be a 2D (n_organisms, genome_length) array")
    n = population.shape[0]
    _, inverse = np.unique(population, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    num_unique = int(inverse.max()) + 1 if n else 0

    rows, cols = grid_shape(n)
    grid = np.full(rows * cols, -1, dtype=np.int64)
    grid[:n] = inverse
    return grid.reshape(rows, cols), num_unique


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
