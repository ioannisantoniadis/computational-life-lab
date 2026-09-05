from computational_life.experiments.base import BffSoupExperimentConfig
from computational_life.experiments.bff_soup import compute_metrics, run_bff_soup
from computational_life.substrates.bff.universe import BffSoupConfig, BffSoupUniverse


def make_config(**overrides) -> BffSoupExperimentConfig:
    universe = BffSoupConfig(population_size=32, genome_length=16, max_steps=200, seed=3)
    params = dict(name="test", seed=3, universe=universe, epochs=10, report_interval=5)
    params.update(overrides)
    return BffSoupExperimentConfig(**params)


def test_run_bff_soup_advances_epochs():
    config = make_config()
    universe = run_bff_soup(config)
    assert universe.epoch == 10


def test_run_bff_soup_reports_at_configured_intervals():
    config = make_config(epochs=10, report_interval=5)
    reports = []
    run_bff_soup(config, on_report=reports.append)
    # Initial report (epoch 0) + epoch 5 + epoch 10.
    assert [r["epoch"] for r in reports] == [0, 5, 10]


def test_run_bff_soup_is_deterministic():
    config = make_config()
    u1 = run_bff_soup(config)
    u2 = run_bff_soup(config)
    assert (u1.population == u2.population).all()


def test_run_bff_soup_diverges_across_seeds():
    universe_a = BffSoupConfig(population_size=32, genome_length=16, max_steps=200, seed=1)
    universe_b = BffSoupConfig(population_size=32, genome_length=16, max_steps=200, seed=2)
    u1 = run_bff_soup(make_config(seed=1, universe=universe_a))
    u2 = run_bff_soup(make_config(seed=2, universe=universe_b))
    assert not (u1.population == u2.population).all()


def test_compute_metrics_has_expected_keys_and_bounds():
    universe = BffSoupUniverse(BffSoupConfig(population_size=32, genome_length=16, seed=1))
    record = compute_metrics(universe)

    assert record["epoch"] == 0
    assert 1 <= record["unique_genomes"] <= 32
    assert 0 < record["dominant_genome_frequency"] <= 1.0
    assert 0.0 <= record["simpson_diversity"] <= 1.0
    assert record["genome_entropy_bits"] >= 0.0
    assert 0.0 <= record["byte_entropy_bits"] <= 8.0
    assert record["instruction_entropy_bits"] >= 0.0
    assert 0.0 <= record["compressed_bits_per_byte"] <= 8.5


def test_compute_metrics_tracks_epoch_progress():
    universe = BffSoupUniverse(BffSoupConfig(population_size=32, genome_length=16, seed=1))
    universe.step_epoch()
    universe.step_epoch()
    assert compute_metrics(universe)["epoch"] == 2
