import pytest

from computational_life.analysis.lineage import LineageRecorder
from computational_life.substrates.bff.universe import BffSoupConfig, BffSoupUniverse


def make_universe(**overrides) -> BffSoupUniverse:
    params = dict(population_size=8, genome_length=8, max_steps=100, seed=1)
    params.update(overrides)
    return BffSoupUniverse(BffSoupConfig(**params))


def test_initial_population_has_no_parents():
    universe = make_universe()
    recorder = LineageRecorder()
    recorder.record(universe)

    for oid in universe.organism_id.tolist():
        assert recorder.parents(oid) is None
        assert recorder.generation(oid) == 0
        assert recorder.ancestors(oid) == []


def test_recording_across_epochs_tracks_parentage():
    universe = make_universe()
    recorder = LineageRecorder()
    recorder.record(universe)

    universe.step_epoch()
    recorder.record(universe)

    for oid in universe.organism_id.tolist():
        parents = recorder.parents(oid)
        assert parents is not None
        p0, p1 = parents
        assert p0 in recorder
        assert p1 in recorder
        assert recorder.generation(oid) == 1
        assert set(recorder.ancestors(oid)) == {p0, p1}


def test_descendants_are_the_inverse_of_ancestors():
    universe = make_universe()
    recorder = LineageRecorder()
    recorder.record(universe)
    initial_ids = universe.organism_id.tolist()

    universe.step_epoch()
    recorder.record(universe)

    for seed_id in initial_ids:
        for descendant_id in recorder.descendants(seed_id):
            assert seed_id in recorder.ancestors(descendant_id)


def test_multi_epoch_ancestor_chain_reaches_back_to_seed_generation():
    universe = make_universe(population_size=4, genome_length=8)
    recorder = LineageRecorder()
    recorder.record(universe)

    for _ in range(5):
        universe.step_epoch()
        recorder.record(universe)

    for oid in universe.organism_id.tolist():
        ancestors = recorder.ancestors(oid)
        assert recorder.lineage_depth(oid) == 5
        # Every recorded ancestor chain must bottom out at a generation-0 seed.
        oldest_generations = [recorder.generation(a) for a in ancestors]
        assert 0 in oldest_generations


def test_len_and_contains():
    universe = make_universe()
    recorder = LineageRecorder()
    assert len(recorder) == 0
    recorder.record(universe)
    assert len(recorder) == universe.config.population_size
    assert int(universe.organism_id[0]) in recorder
    assert -1 not in recorder


def test_recording_the_same_state_twice_is_idempotent():
    universe = make_universe()
    recorder = LineageRecorder()
    recorder.record(universe)
    recorder.record(universe)
    assert len(recorder) == universe.config.population_size


def test_unrecorded_organism_raises_key_error():
    recorder = LineageRecorder()
    with pytest.raises(KeyError):
        recorder.generation(999)
