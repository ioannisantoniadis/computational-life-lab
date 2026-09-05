import numpy as np
import pytest

from rendering import (
    genome_symbols,
    grid_shape,
    instruction_distribution,
    population_to_cluster_grid,
    render_tape_html,
    select_display_sample,
)


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


def test_genome_symbols_categorizes_instructions_null_and_nop():
    genome = bytes([ord("+"), 0, 1])  # instruction, NULL sentinel, unassigned NOP
    symbols = genome_symbols(genome)
    assert symbols[0] == ("+", "instruction")
    assert symbols[1] == ("0", "null")
    assert symbols[2][1] == "nop"


def test_genome_symbols_covers_every_instruction_character():
    from computational_life.substrates.bff.instruction_set import parse

    genome = parse("[]+-.,<>{}")
    symbols = genome_symbols(genome)
    assert [s for s, _ in symbols] == list("[]+-.,<>{}")
    assert all(category == "instruction" for _, category in symbols)


def test_instruction_distribution_counts_by_op_name():
    genome = bytes([ord("+"), ord("+"), ord("-"), 0, 1, 2])
    counts = instruction_distribution(genome)
    assert counts["INC_CELL"] == 2
    assert counts["DEC_CELL"] == 1
    assert counts["NULL"] == 1
    assert counts["NOP"] == 2


def test_instruction_distribution_sums_to_genome_length():
    genome = bytes(range(256)) * 2  # every possible byte value, twice
    counts = instruction_distribution(genome)
    assert sum(counts.values()) == len(genome)


def test_render_tape_html_contains_one_span_per_byte():
    genome = bytes([ord("+"), ord("-"), 0])
    html = render_tape_html(genome)
    assert html.count("<span") == 3
    assert ">+<" in html
    assert ">-<" in html
    assert ">0<" in html


def test_render_tape_html_highlights_head_and_pc_positions():
    genome = bytes([ord(">"), ord("<"), ord("+")])
    html = render_tape_html(genome, head0=0, head1=1, pc=2)
    # Order of spans matches tape order; check each carries its own color.
    spans = html.split("<span")[1:]
    assert "#bfdbfe" in spans[0]  # head0
    assert "#fecaca" in spans[1]  # head1
    assert "#bbf7d0" in spans[2]  # pc


def test_render_tape_html_pc_takes_precedence_when_positions_coincide():
    genome = bytes([ord("+")])
    html = render_tape_html(genome, head0=0, head1=0, pc=0)
    assert "#bbf7d0" in html
    assert "#bfdbfe" not in html
    assert "#fecaca" not in html
