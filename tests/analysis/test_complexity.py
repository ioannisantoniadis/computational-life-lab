import numpy as np
import pytest

from computational_life.analysis.complexity import (
    compressed_bits_per_byte,
    structural_redundancy,
)


def test_uniform_population_compresses_to_near_zero_bits_per_byte():
    population = np.zeros((64, 64), dtype=np.uint8)
    assert compressed_bits_per_byte(population) < 0.5


def test_random_population_compresses_poorly():
    rng = np.random.default_rng(0)
    population = rng.integers(0, 256, size=(256, 64), dtype=np.uint8)
    bpb = compressed_bits_per_byte(population)
    assert 6.0 < bpb <= 8.5  # close to the 8-bit/byte incompressible ceiling


def test_repeated_genome_compresses_much_better_than_random():
    rng = np.random.default_rng(1)
    random_pop = rng.integers(0, 256, size=(512, 64), dtype=np.uint8)
    repeated_genome = rng.integers(0, 256, size=(1, 64), dtype=np.uint8)
    repeated_pop = np.tile(repeated_genome, (512, 1))
    assert compressed_bits_per_byte(repeated_pop) < compressed_bits_per_byte(random_pop)


def test_structural_redundancy_high_for_many_repeated_genomes():
    rng = np.random.default_rng(2)
    genome = rng.integers(0, 256, size=(1, 64), dtype=np.uint8)
    population = np.tile(genome, (256, 1))
    # Byte-value entropy is unaffected by repetition of the *same* pattern
    # (it only looks at value frequencies), but the compressor exploits the
    # repeated 64-byte block, so the gap should be large and positive.
    assert structural_redundancy(population) > 5.0


def test_structural_redundancy_near_zero_for_unstructured_random_population():
    rng = np.random.default_rng(3)
    population = rng.integers(0, 256, size=(256, 64), dtype=np.uint8)
    assert structural_redundancy(population) == pytest.approx(0.0, abs=1.0)


def test_empty_population_does_not_crash():
    population = np.zeros((0, 64), dtype=np.uint8)
    assert compressed_bits_per_byte(population) == 0.0
