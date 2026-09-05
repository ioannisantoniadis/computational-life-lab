import numpy as np
import pytest

from computational_life.analysis.diversity import (
    dominant_genome_frequency,
    genome_frequency_counts,
    simpson_diversity_index,
    unique_genome_count,
)


def test_all_identical_genomes_has_no_diversity():
    population = np.zeros((10, 8), dtype=np.uint8)
    assert unique_genome_count(population) == 1
    assert dominant_genome_frequency(population) == 1.0
    assert simpson_diversity_index(population) == pytest.approx(0.0)


def test_all_distinct_genomes_maximizes_dominant_frequency_inverse():
    population = np.arange(10 * 8, dtype=np.uint8).reshape(10, 8)
    assert unique_genome_count(population) == 10
    assert dominant_genome_frequency(population) == pytest.approx(0.1)
    # Simpson's index for 10 equally-frequent categories: 1 - 10*(0.1^2) = 0.9
    assert simpson_diversity_index(population) == pytest.approx(0.9)


def test_partial_duplication():
    population = np.array(
        [[1, 1], [1, 1], [1, 1], [2, 2]],
        dtype=np.uint8,
    )
    assert unique_genome_count(population) == 2
    assert dominant_genome_frequency(population) == pytest.approx(0.75)
    counts = sorted(genome_frequency_counts(population).tolist())
    assert counts == [1, 3]


def test_rejects_non_2d_input():
    with pytest.raises(ValueError):
        genome_frequency_counts(np.zeros(10, dtype=np.uint8))
