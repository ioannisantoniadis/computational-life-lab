import numpy as np
import pytest

from rendering import grid_shape, population_to_cluster_grid, select_display_sample


@pytest.mark.parametrize("n", [1, 2, 4, 5, 16, 100, 131072])
def test_grid_shape_covers_population_and_is_near_square(n):
    rows, cols = grid_shape(n)
    assert rows * cols >= n
    assert rows >= 1 and cols >= 1
    # Not wildly non-square (rows is the floor of sqrt(n) by construction).
    assert rows <= math_isqrt(n) + 1


def math_isqrt(n):
    import math

    return math.isqrt(n)


def test_grid_shape_rejects_non_positive():
    with pytest.raises(ValueError):
        grid_shape(0)


def test_select_display_sample_returns_everything_when_small():
    indices = select_display_sample(500, max_displayed=10_000)
    assert list(indices) == list(range(500))


def test_select_display_sample_subsamples_when_large():
    indices = select_display_sample(50_000, max_displayed=1_000, seed=1)
    assert len(indices) == 1_000
    assert len(set(indices.tolist())) == 1_000
    assert indices.min() >= 0 and indices.max() < 50_000


def test_select_display_sample_is_deterministic():
    a = select_display_sample(50_000, max_displayed=1_000, seed=1)
    b = select_display_sample(50_000, max_displayed=1_000, seed=1)
    assert np.array_equal(a, b)


def test_cluster_grid_assigns_identical_ids_to_identical_genomes():
    population = np.array(
        [
            [1, 2, 3],
            [1, 2, 3],
            [4, 5, 6],
            [7, 8, 9],
        ],
        dtype=np.uint8,
    )
    grid, num_unique = population_to_cluster_grid(population)
    assert num_unique == 3
    flat = grid.flatten()
    valid = flat[flat >= 0]
    assert len(valid) == 4
    # The two identical genomes (indices 0 and 1) must share a cluster id.
    assert flat[0] == flat[1]
    assert flat[2] != flat[0]
    assert flat[3] != flat[0]
    assert flat[3] != flat[2]


def test_cluster_grid_shape_matches_grid_shape_and_pads_with_negative_one():
    population = np.zeros((5, 4), dtype=np.uint8)
    grid, _ = population_to_cluster_grid(population)
    rows, cols = grid_shape(5)
    assert grid.shape == (rows, cols)
    assert (grid.flatten()[5:] == -1).all()


def test_cluster_grid_rejects_non_2d_input():
    with pytest.raises(ValueError):
        population_to_cluster_grid(np.zeros(10, dtype=np.uint8))
