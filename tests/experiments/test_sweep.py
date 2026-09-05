import pytest

from computational_life.experiments.sweep import (
    SweepConfig,
    collect_sweep_results,
    load_sweep_config,
    run_sweep,
    summarize_by_parameter,
)
from computational_life.storage.database import RunStore

BASE_RAW = {
    "population": {"size": 16, "genome_length": 8},
    "execution": {"max_steps": 100},
    "run": {"epochs": 3, "report_interval": 3},
}


def make_sweep_config(**overrides) -> SweepConfig:
    params = dict(
        name="test_sweep",
        base_raw=BASE_RAW,
        sweep_params={"population.size": [16, 32]},
        seeds=[1, 2],
    )
    params.update(overrides)
    return SweepConfig(**params)


def test_points_cross_products_sweep_values_and_seeds():
    config = make_sweep_config()
    points = config.points()
    assert len(points) == 4  # 2 population sizes x 2 seeds
    combos = {(p.overrides["population.size"], p.overrides["seed"]) for p in points}
    assert combos == {(16, 1), (16, 2), (32, 1), (32, 2)}


def test_points_apply_dotted_overrides_to_the_parsed_config():
    config = make_sweep_config()
    points = config.points()
    sizes = {p.config.universe.population_size for p in points}
    assert sizes == {16, 32}
    # genome_length comes from base_raw, untouched by the sweep.
    assert all(p.config.universe.genome_length == 8 for p in points)


def test_points_with_no_sweep_params_is_one_point_per_seed():
    config = make_sweep_config(sweep_params={})
    points = config.points()
    assert len(points) == 2
    assert points[0].overrides == {"seed": 1}


def test_seeds_from_explicit_list(tmp_path):
    path = tmp_path / "sweep.yaml"
    path.write_text(
        "experiment: bff_soup_sweep\n"
        "name: my_sweep\n"
        "base:\n  population: {size: 8, genome_length: 8}\n"
        "  execution: {max_steps: 50}\n  run: {epochs: 2}\n"
        "sweep:\n  population.size: [8, 16]\n"
        "seeds:\n  list: [10, 20, 30]\n"
    )
    config = load_sweep_config(path)
    assert config.seeds == [10, 20, 30]
    assert len(config.points()) == 6


def test_seeds_from_count_and_start(tmp_path):
    path = tmp_path / "sweep.yaml"
    path.write_text(
        "experiment: bff_soup_sweep\n"
        "name: my_sweep\n"
        "base:\n  population: {size: 8, genome_length: 8}\n"
        "  execution: {max_steps: 50}\n  run: {epochs: 2}\n"
        "sweep: {}\n"
        "seeds:\n  count: 3\n  start: 5\n"
    )
    config = load_sweep_config(path)
    assert config.seeds == [5, 6, 7]


def test_load_sweep_config_rejects_wrong_experiment_kind(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("experiment: bff_soup\nname: x\n")
    with pytest.raises(ValueError):
        load_sweep_config(path)


def test_run_sweep_persists_one_run_per_point_with_events_and_metrics(tmp_path):
    config = make_sweep_config(sweep_params={"population.size": [16]}, seeds=[1, 2])
    with RunStore(tmp_path / "sweep.db") as store:
        run_ids = run_sweep(config, store)
        assert len(run_ids) == 2

        for run_id in run_ids:
            run = store.get_run(run_id)
            assert run["status"] == "completed"
            assert run["experiment_name"] == "test_sweep"

            events = store.get_events(run_id)
            kinds = {e["kind"] for e in events}
            assert "sweep_point" in kinds
            assert "replication_scan" in kinds

            history = store.get_metrics_history(run_id)
            assert any("best_replication_score" in row for row in history)


def test_run_sweep_calls_on_point_done_for_every_point(tmp_path):
    config = make_sweep_config(sweep_params={"population.size": [16, 32]}, seeds=[1])
    calls = []
    with RunStore(tmp_path / "sweep.db") as store:
        run_sweep(config, store, on_point_done=lambda point, run_id, universe, score: calls.append(
            (point.overrides["population.size"], run_id, universe.epoch, score)
        ))
    assert len(calls) == 2
    assert {c[0] for c in calls} == {16, 32}


def test_collect_and_summarize_sweep_results(tmp_path):
    config = make_sweep_config(sweep_params={"population.size": [16, 32]}, seeds=[1, 2])
    with RunStore(tmp_path / "sweep.db") as store:
        run_sweep(config, store)
        results = collect_sweep_results(store, "test_sweep")

    assert len(results) == 4
    assert all("population.size" in r and "best_replication_score" in r for r in results)

    summary = summarize_by_parameter(results, "population.size", genome_length=8)
    assert {row["population.size"] for row in summary} == {16, 32}
    for row in summary:
        assert row["n_runs"] == 2  # 2 seeds per population size
        assert 0.0 <= row["p_candidate_replicator"] <= 1.0


def test_collect_sweep_results_ignores_other_experiments(tmp_path):
    config = make_sweep_config(sweep_params={"population.size": [16]}, seeds=[1])
    with RunStore(tmp_path / "sweep.db") as store:
        run_sweep(config, store)
        store.start_run(experiment_name="unrelated", config_text="", seed=0)
        results = collect_sweep_results(store, "test_sweep")
    assert len(results) == 1
