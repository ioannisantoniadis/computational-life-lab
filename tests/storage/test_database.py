import pytest

from computational_life import __version__
from computational_life.storage.database import RunStore


@pytest.fixture
def store(tmp_path):
    with RunStore(tmp_path / "test.db") as s:
        yield s


def test_start_run_creates_a_row_with_expected_metadata(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="seed: 1\n", seed=1)
    run = store.get_run(run_id)
    assert run["experiment_name"] == "bff_soup"
    assert run["config_yaml"] == "seed: 1\n"
    assert run["seed"] == 1
    assert run["software_version"] == __version__
    assert run["status"] == "running"
    assert run["finished_at"] is None
    assert run["final_epoch"] is None


def test_get_run_unknown_id_raises_key_error(store):
    with pytest.raises(KeyError):
        store.get_run(999)


def test_record_and_retrieve_metrics_history(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="", seed=1)
    store.record_metrics(run_id, 0, {"epoch": 0, "unique_genomes": 512, "dominant_genome_frequency": 0.01})
    store.record_metrics(run_id, 10, {"epoch": 10, "unique_genomes": 480, "dominant_genome_frequency": 0.02})

    history = store.get_metrics_history(run_id)
    assert [row["epoch"] for row in history] == [0, 10]
    assert history[0]["unique_genomes"] == 512
    assert history[1]["dominant_genome_frequency"] == pytest.approx(0.02)


def test_metrics_ignore_non_numeric_and_epoch_keys(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="", seed=1)
    store.record_metrics(run_id, 0, {"epoch": 0, "unique_genomes": 5, "label": "not a number"})
    history = store.get_metrics_history(run_id)
    assert history == [{"epoch": 0, "unique_genomes": 5.0}]


def test_latest_metrics_returns_most_recent_epoch(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="", seed=1)
    store.record_metrics(run_id, 0, {"unique_genomes": 512})
    store.record_metrics(run_id, 5, {"unique_genomes": 500})
    assert store.latest_metrics(run_id)["epoch"] == 5


def test_latest_metrics_none_when_no_metrics_recorded(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="", seed=1)
    assert store.latest_metrics(run_id) is None


def test_finish_run_updates_status_and_final_epoch(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="", seed=1)
    store.finish_run(run_id, final_epoch=1000)
    run = store.get_run(run_id)
    assert run["status"] == "completed"
    assert run["final_epoch"] == 1000
    assert run["finished_at"] is not None


def test_finish_run_can_report_failure_status(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="", seed=1)
    store.finish_run(run_id, final_epoch=42, status="failed")
    assert store.get_run(run_id)["status"] == "failed"


def test_record_and_retrieve_events(store):
    run_id = store.start_run(experiment_name="bff_soup", config_text="", seed=1)
    store.record_event(run_id, 18392, "candidate_replicator_scan", {"top_score": 40, "sample_size": 200})
    store.record_event(run_id, 20000, "checkpoint_saved")

    events = store.get_events(run_id)
    assert len(events) == 2
    assert events[0]["epoch"] == 18392
    assert events[0]["kind"] == "candidate_replicator_scan"
    assert events[0]["payload"] == {"top_score": 40, "sample_size": 200}
    assert events[1]["payload"] is None


def test_list_runs_returns_all_runs_in_order(store):
    id1 = store.start_run(experiment_name="a", config_text="", seed=1)
    id2 = store.start_run(experiment_name="b", config_text="", seed=2)
    runs = store.list_runs()
    assert [r["id"] for r in runs] == [id1, id2]
    assert [r["experiment_name"] for r in runs] == ["a", "b"]


def test_metrics_are_isolated_per_run(store):
    run1 = store.start_run(experiment_name="a", config_text="", seed=1)
    run2 = store.start_run(experiment_name="b", config_text="", seed=2)
    store.record_metrics(run1, 0, {"unique_genomes": 10})
    store.record_metrics(run2, 0, {"unique_genomes": 20})
    assert store.latest_metrics(run1)["unique_genomes"] == 10
    assert store.latest_metrics(run2)["unique_genomes"] == 20


def test_reopening_existing_database_preserves_data(tmp_path):
    db_path = tmp_path / "persist.db"
    with RunStore(db_path) as s:
        run_id = s.start_run(experiment_name="bff_soup", config_text="", seed=7)
        s.record_metrics(run_id, 0, {"unique_genomes": 5})

    with RunStore(db_path) as s:
        run = s.get_run(run_id)
        assert run["seed"] == 7
        assert s.latest_metrics(run_id)["unique_genomes"] == 5
