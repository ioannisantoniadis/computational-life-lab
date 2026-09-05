import numpy as np
import pytest

from computational_life.substrates.bff.interpreter import BffInterpreter
from computational_life.substrates.bff.universe import BffSoupConfig, BffSoupUniverse


def small_config(**overrides) -> BffSoupConfig:
    params = dict(population_size=16, genome_length=8, max_steps=200, seed=42)
    params.update(overrides)
    return BffSoupConfig(**params)


def test_population_initialized_with_expected_shape_and_dtype():
    universe = BffSoupUniverse(small_config())
    assert universe.population.shape == (16, 8)
    assert universe.population.dtype == np.uint8
    assert universe.epoch == 0
    assert list(universe.organism_id) == list(range(16))
    assert (universe.generation == 0).all()
    assert (universe.parent_ids == -1).all()


def test_odd_population_size_rejected():
    with pytest.raises(ValueError):
        BffSoupConfig(population_size=15, genome_length=8)


def test_invalid_mutation_rate_rejected():
    with pytest.raises(ValueError):
        BffSoupConfig(population_size=4, genome_length=8, mutation_rate=1.5)


def test_same_seed_is_fully_deterministic():
    config = small_config()
    u1 = BffSoupUniverse(config)
    u2 = BffSoupUniverse(config)
    for _ in range(10):
        u1.step_epoch()
        u2.step_epoch()
    assert np.array_equal(u1.population, u2.population)
    assert np.array_equal(u1.organism_id, u2.organism_id)
    assert np.array_equal(u1.generation, u2.generation)
    assert np.array_equal(u1.parent_ids, u2.parent_ids)


def test_different_seed_diverges():
    u1 = BffSoupUniverse(small_config(seed=1))
    u2 = BffSoupUniverse(small_config(seed=2))
    assert not np.array_equal(u1.population, u2.population)


def test_every_organism_gets_a_new_id_each_epoch():
    # Every slot participates in exactly one pairing per epoch (a full
    # perfect matching), so every slot's organism_id changes every epoch.
    universe = BffSoupUniverse(small_config())
    ids_before = universe.organism_id.copy()
    universe.step_epoch()
    assert not np.any(universe.organism_id == ids_before)
    assert len(set(universe.organism_id.tolist())) == len(universe.organism_id)


def test_parent_ids_reference_the_correct_pre_epoch_organisms():
    universe = BffSoupUniverse(small_config(population_size=4, genome_length=8))
    ids_before = universe.organism_id.copy()
    universe.step_epoch()
    for slot in range(4):
        p0, p1 = universe.parent_ids[slot]
        assert p0 in ids_before and p1 in ids_before
        assert {p0, p1} <= set(ids_before.tolist())


def test_generation_increases_monotonically():
    universe = BffSoupUniverse(small_config())
    for _ in range(5):
        universe.step_epoch()
        assert (universe.generation >= 1).all()
    assert universe.generation.max() <= 5


def test_summary_reports_sane_population_statistics():
    universe = BffSoupUniverse(small_config())
    summary = universe.summary()
    assert summary["population_size"] == 16
    assert 1 <= summary["unique_genomes"] <= 16
    assert 0 < summary["dominant_genome_frequency"] <= 1.0
    universe.step_epoch()
    assert universe.summary()["epoch"] == 1


def test_mutation_disabled_by_default():
    config = small_config()
    assert config.mutation_enabled is False


def test_mutation_enabled_changes_trajectory_relative_to_disabled():
    base_kwargs = dict(population_size=64, genome_length=16, max_steps=200, seed=7)
    no_mutation = BffSoupUniverse(BffSoupConfig(**base_kwargs, mutation_enabled=False))
    with_mutation = BffSoupUniverse(
        BffSoupConfig(**base_kwargs, mutation_enabled=True, mutation_rate=0.1)
    )
    for _ in range(5):
        no_mutation.step_epoch()
        with_mutation.step_epoch()
    assert not np.array_equal(no_mutation.population, with_mutation.population)


def test_universe_epoch_matches_manual_scalar_execution():
    # End-to-end regression: for a population of exactly one pair, the
    # universe's vectorized epoch must reproduce hand-driven scalar
    # execution of the same concatenated tape.
    config = BffSoupConfig(population_size=2, genome_length=8, max_steps=100, seed=99)
    universe = BffSoupUniverse(config)
    genome0 = bytes(universe.population[0])
    genome1 = bytes(universe.population[1])

    universe.step_epoch()

    # Figure out which slot ended up "left" vs "right" by reconstructing the
    # pairing RNG independently. The "pairing" substream is independent of
    # "init"/"mutation" (see RngStreams), so this reproduces the exact same
    # permutation the universe itself drew, without needing to replay init.
    from computational_life.core.rng import RngStreams

    rng = RngStreams(config.seed)
    permutation = rng.stream("pairing").permutation(2)
    left, right = permutation[0], permutation[1]
    genomes = [genome0, genome1]
    combined = genomes[left] + genomes[right]

    scalar = BffInterpreter(bytearray(combined), head_init=config.head_init)
    scalar.run(max_steps=config.max_steps)

    expected_left = scalar.tape[:8]
    expected_right = scalar.tape[8:]
    assert bytes(universe.population[left]) == bytes(expected_left)
    assert bytes(universe.population[right]) == bytes(expected_right)
