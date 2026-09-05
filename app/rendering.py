"""Pure, UI-framework-independent helpers for rendering a population.

Kept separate from computational_life.core/substrates on purpose: this is
presentation logic (how to lay organisms out on a grid, which cluster id
to color them by), not simulation mechanism or scientific analysis. It
must never feed back into the simulator (spec section 3.2).
"""

from __future__ import annotations

import math

import numpy as np

DEFAULT_MAX_DISPLAYED_ORGANISMS = 10_000


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
