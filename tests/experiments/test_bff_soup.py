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


def test_run_bff_soup_accepts_a_pre_built_universe_and_continues_it():
    starting_universe = BffSoupUniverse(
        BffSoupConfig(population_size=32, genome_length=16, max_steps=200, seed=3)
    )
    starting_universe.step_epoch()
    starting_universe.step_epoch()

    config = make_config(epochs=3)
    result = run_bff_soup(config, universe=starting_universe)

    assert result is starting_universe
    assert result.epoch == 5  # 2 already done + 3 more


def test_run_bff_soup_invokes_on_checkpoint_at_configured_interval():
    # The callback receives the live universe (not a copy), so record the
    # epoch *at call time* -- capturing the object for later inspection
    # would just see its final epoch for every entry.
    config = make_config(epochs=10, report_interval=100)
    checkpoint_epochs = []
    run_bff_soup(
        config,
        on_checkpoint=lambda u: checkpoint_epochs.append(u.epoch),
        checkpoint_interval=4,
    )
    assert checkpoint_epochs == [4, 8]


def test_run_bff_soup_does_not_checkpoint_without_an_interval():
    config = make_config(epochs=10)
    checkpoints = []
    run_bff_soup(config, on_checkpoint=checkpoints.append, checkpoint_interval=None)
    assert checkpoints == []


def test_run_bff_soup_invokes_on_replication_scan_at_configured_interval():
    config = make_config(epochs=10, report_interval=100)
    scan_epochs = []

    def on_scan(universe, scores, sample_idx):
        scan_epochs.append(universe.epoch)
        assert scores.shape == sample_idx.shape

    run_bff_soup(
        config,
        on_replication_scan=on_scan,
        replication_scan_interval=4,
        replication_sample_size=10,
    )
    assert scan_epochs == [4, 8]


def test_run_bff_soup_does_not_scan_without_an_interval():
    config = make_config(epochs=10)
    calls = []
    run_bff_soup(config, on_replication_scan=calls.append, replication_scan_interval=None)
    assert calls == []


def test_run_bff_soup_replication_scan_sample_size_is_capped_at_population_size():
    config = make_config(epochs=4, report_interval=100)  # population_size=32
    sample_sizes = []
    run_bff_soup(
        config,
        on_replication_scan=lambda u, scores, idx: sample_sizes.append(len(idx)),
        replication_scan_interval=4,
        replication_sample_size=1000,  # larger than the population
    )
    assert sample_sizes == [32]
