from pathlib import Path

import numpy as np

from computational_life import __version__
from computational_life.storage.checkpoints import (
    checkpoint_file_path,
    checkpoint_metadata,
    load_checkpoint,
    save_checkpoint,
)
from computational_life.substrates.bff.universe import BffSoupConfig, BffSoupUniverse


def test_checkpoint_file_path_appends_npz_when_missing():
    assert checkpoint_file_path("foo") == Path("foo.npz")
    assert checkpoint_file_path("dir/foo") == Path("dir/foo.npz")


def test_checkpoint_file_path_does_not_double_append():
    assert checkpoint_file_path("foo.npz") == Path("foo.npz")


def test_checkpoint_file_path_preserves_other_extensions():
    assert checkpoint_file_path("foo.dat") == Path("foo.dat.npz")


def make_universe(**overrides) -> BffSoupUniverse:
    params = dict(population_size=16, genome_length=8, max_steps=200, seed=42)
    params.update(overrides)
    return BffSoupUniverse(BffSoupConfig(**params))


def assert_universes_equal(a: BffSoupUniverse, b: BffSoupUniverse) -> None:
    assert a.config == b.config
    assert a.epoch == b.epoch
    assert a._next_organism_id == b._next_organism_id
    assert np.array_equal(a.population, b.population)
    assert np.array_equal(a.organism_id, b.organism_id)
    assert np.array_equal(a.generation, b.generation)
    assert np.array_equal(a.birth_epoch, b.birth_epoch)
    assert np.array_equal(a.parent_ids, b.parent_ids)


def test_round_trip_preserves_full_state(tmp_path):
    universe = make_universe()
    for _ in range(5):
        universe.step_epoch()

    path = tmp_path / "checkpoint"
    save_checkpoint(universe, path)
    restored = load_checkpoint(path)

    assert_universes_equal(universe, restored)


def test_checkpoint_saved_without_npz_extension_is_still_loadable(tmp_path):
    universe = make_universe()
    path = tmp_path / "no_extension"
    save_checkpoint(universe, path)
    assert (tmp_path / "no_extension.npz").exists()
    restored = load_checkpoint(path)  # same bare path, no .npz suffix
    assert_universes_equal(universe, restored)


def test_resuming_from_checkpoint_matches_uninterrupted_run(tmp_path):
    config = BffSoupConfig(population_size=32, genome_length=16, max_steps=300, seed=7)

    uninterrupted = BffSoupUniverse(config)
    for _ in range(10):
        uninterrupted.step_epoch()

    checkpointed = BffSoupUniverse(config)
    for _ in range(4):
        checkpointed.step_epoch()
    path = tmp_path / "mid_run"
    save_checkpoint(checkpointed, path)

    resumed = load_checkpoint(path)
    for _ in range(6):  # 4 + 6 == 10, matching the uninterrupted run
        resumed.step_epoch()

    assert_universes_equal(uninterrupted, resumed)


def test_checkpoint_metadata_reads_without_full_population(tmp_path):
    universe = make_universe()
    universe.step_epoch()
    universe.step_epoch()
    path = tmp_path / "meta_check"
    save_checkpoint(universe, path)

    metadata = checkpoint_metadata(path)
    assert metadata["epoch"] == 2
    assert metadata["software_version"] == __version__
    assert metadata["config"]["seed"] == 42
    assert metadata["next_organism_id"] == universe._next_organism_id
    assert "rng_state" in metadata


def test_rng_streams_continue_identically_after_restore(tmp_path):
    # Beyond matching state after resuming, the *ongoing* random draws
    # from a restored universe must match what an uninterrupted universe
    # would draw next -- not just that some prior state was copied.
    config = BffSoupConfig(population_size=16, genome_length=8, max_steps=200, seed=3)
    uninterrupted = BffSoupUniverse(config)
    uninterrupted.step_epoch()

    checkpointed = BffSoupUniverse(config)
    checkpointed.step_epoch()
    path = tmp_path / "rng_check"
    save_checkpoint(checkpointed, path)
    resumed = load_checkpoint(path)

    next_permutation_expected = uninterrupted.rng.stream("pairing").permutation(16)
    next_permutation_actual = resumed.rng.stream("pairing").permutation(16)
    assert np.array_equal(next_permutation_expected, next_permutation_actual)
