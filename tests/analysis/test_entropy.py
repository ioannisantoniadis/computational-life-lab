import numpy as np
import pytest

from computational_life.analysis.entropy import (
    byte_entropy,
    instruction_entropy,
    shannon_entropy_genomes,
)
from computational_life.substrates.bff.instruction_set import parse


def test_shannon_entropy_zero_for_uniform_population():
    population = np.zeros((16, 8), dtype=np.uint8)
    assert shannon_entropy_genomes(population) == pytest.approx(0.0)


def test_shannon_entropy_genomes_maximal_for_equally_likely_distinct_genomes():
    # 4 equally frequent distinct genomes -> entropy = log2(4) = 2 bits.
    population = np.array(
        [[1, 1], [1, 1], [2, 2], [2, 2], [3, 3], [3, 3], [4, 4], [4, 4]],
        dtype=np.uint8,
    )
    assert shannon_entropy_genomes(population) == pytest.approx(2.0)


def test_byte_entropy_zero_when_all_bytes_identical():
    population = np.full((10, 16), 7, dtype=np.uint8)
    assert byte_entropy(population) == pytest.approx(0.0)


def test_byte_entropy_maximal_for_uniform_byte_distribution():
    # Every byte value 0..255 appears exactly once -> entropy = log2(256) = 8.
    population = np.arange(256, dtype=np.uint8).reshape(1, 256)
    assert byte_entropy(population) == pytest.approx(8.0)


def test_instruction_entropy_zero_when_single_instruction_repeated():
    population = np.tile(np.frombuffer(parse("+" * 16), dtype=np.uint8), (5, 1))
    assert instruction_entropy(population) == pytest.approx(0.0)


def test_instruction_entropy_positive_for_mixed_instructions():
    genome = parse("[]+-.,<>{}") + bytes(6)  # 10 distinct instructions + NOP padding
    population = np.tile(np.frombuffer(genome, dtype=np.uint8), (5, 1))
    assert instruction_entropy(population) > 0.0
