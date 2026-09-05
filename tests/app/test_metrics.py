from metrics import compute_metrics_record

from computational_life.substrates.bff.universe import BffSoupConfig, BffSoupUniverse


def test_compute_metrics_record_has_expected_keys_and_bounds():
    universe = BffSoupUniverse(BffSoupConfig(population_size=32, genome_length=16, seed=1))
    record = compute_metrics_record(universe)

    assert record["epoch"] == 0
    assert 1 <= record["unique_genomes"] <= 32
    assert 0 < record["dominant_genome_frequency"] <= 1.0
    assert 0.0 <= record["simpson_diversity"] <= 1.0
    assert record["genome_entropy_bits"] >= 0.0
    assert 0.0 <= record["byte_entropy_bits"] <= 8.0
    assert record["instruction_entropy_bits"] >= 0.0
    assert 0.0 <= record["compressed_bits_per_byte"] <= 8.5


def test_compute_metrics_record_tracks_epoch_progress():
    universe = BffSoupUniverse(BffSoupConfig(population_size=32, genome_length=16, seed=1))
    universe.step_epoch()
    universe.step_epoch()
    record = compute_metrics_record(universe)
    assert record["epoch"] == 2
