"""Headless smoke test for the Streamlit dashboard.

Runs the actual app script (not a reimplementation of it) via Streamlit's
AppTest harness, so a broken import or a widget wired to the wrong session
key fails a fast pytest run instead of only showing up when someone
happens to click around in a browser.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"


@pytest.fixture(autouse=True)
def _isolated_runs_dir(tmp_path, monkeypatch):
    """Every dashboard run now registers itself in a real database from
    the moment it's created (see _register_new_run in streamlit_app.py),
    not just when some opt-in feature is enabled -- so without this,
    every test in this file would write real rows and checkpoint files
    into the actual project's runs/ directory. Redirects via the same
    env var streamlit_app.py itself reads, since AppTest re-execs the
    script in a fresh module namespace on every run -- monkeypatching an
    imported module's attribute wouldn't reach that separate execution.
    """
    monkeypatch.setenv("COMPUTATIONAL_LIFE_RUNS_DIR", str(tmp_path / "runs"))
    return tmp_path / "runs"


def test_app_loads_without_exception():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    assert not at.exception


def test_app_shows_initial_epoch_zero():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    assert not at.exception
    epoch_metric = at.metric[0]
    assert epoch_metric.value == "0"


def test_step_button_advances_epoch():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    step_button = next(b for b in at.button if b.label == "Step")
    step_button.click().run(timeout=30)
    assert not at.exception
    epoch_metric = at.metric[0]
    assert epoch_metric.value == "10"  # default epochs-per-step


def test_genome_inspector_shows_selected_organism():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    at.number_input(key="inspector_index").set_value(3).run(timeout=30)
    assert not at.exception
    # Organism ID metric should reflect the freshly initialized population,
    # where slot i starts out holding organism id i.
    organism_id_metric = at.metric[4]  # after the 4 top-level status metrics
    assert organism_id_metric.value == "3"


def test_execution_debugger_load_and_step():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    load_button = next(b for b in at.button if b.label == "Load pair into debugger")
    load_button.click().run(timeout=30)
    assert not at.exception

    step_button = next(b for b in at.button if b.key == "debug_step")
    step_button.click().run(timeout=30)
    assert not at.exception

    step_metric = next(m for m in at.metric if m.label == "Step")
    assert step_metric.value == "1"


def test_execution_debugger_run_to_halt_then_reset():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    next(b for b in at.button if b.label == "Load pair into debugger").click().run(timeout=30)
    next(b for b in at.button if b.key == "debug_run").click().run(timeout=30)
    assert not at.exception

    next(b for b in at.button if b.key == "debug_reset").click().run(timeout=30)
    assert not at.exception
    step_metric = next(m for m in at.metric if m.label == "Step")
    assert step_metric.value == "0"


def test_lineage_tracking_toggle_shows_ancestor_metrics():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    at.checkbox(key="track_lineage").set_value(True).run(timeout=30)
    assert not at.exception

    next(ni for ni in at.number_input if ni.label == "Epochs per step").set_value(1).run(
        timeout=30
    )
    step_button = next(b for b in at.button if b.label == "Step")
    step_button.click().run(timeout=30)
    assert not at.exception

    ancestors_metric = next(m for m in at.metric if m.label == "Recorded ancestors")
    descendants_metric = next(m for m in at.metric if m.label == "Recorded descendants")
    # Organism 0 (the default inspector selection) is one epoch old here,
    # so it should have exactly 2 recorded parents and 0 descendants yet.
    assert ancestors_metric.value == "2"
    assert descendants_metric.value == "0"

    # With 2 recorded ancestors, the lineage graph (organism + its 2
    # parents = 3 nodes) should render without exception.
    assert any("DAG, not a strict" in c.value for c in at.caption)


def test_replication_score_button_computes_and_displays_score():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    score_button = next(b for b in at.button if b.key == "compute_replication")
    score_button.click().run(timeout=60)
    assert not at.exception

    score_metric = next(m for m in at.metric if m.label == "Replication score")
    numerator, _, denominator = score_metric.value.partition(" / ")
    assert 0 <= int(numerator) <= int(denominator)


def test_replicator_scan_runs_and_shows_results():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    sample_size_input = next(
        ni for ni in at.number_input if ni.label == "Sample size"
    )
    max_steps_input = next(
        ni for ni in at.number_input if ni.label == "Max steps per execution"
    )
    sample_size_input.set_value(20)
    max_steps_input.set_value(200)
    at.run(timeout=30)

    scan_button = next(b for b in at.button if b.label == "Run scan")
    scan_button.click().run(timeout=60)
    assert not at.exception
    # One dataframe is always present now (the sidebar's "Browse runs"
    # table); this scan adds a second one for its results.
    assert len(at.dataframe) == 2


def test_auto_scan_checkbox_reveals_interval_and_sample_size_inputs():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    assert not any(ni.key == "auto_scan_interval" for ni in at.number_input)

    at.checkbox(key="auto_scan").set_value(True).run(timeout=30)
    assert not at.exception
    assert any(ni.key == "auto_scan_interval" for ni in at.number_input)
    assert any(ni.key == "auto_scan_sample_size" for ni in at.number_input)


def test_auto_scan_runs_during_step_and_shows_last_result(monkeypatch):
    # Forces a fast, fixed score instead of relying on genuine replication
    # emergence in one epoch -- this test is about the periodic-scan and
    # session-state wiring, not real replication (same rationale as the
    # CLI's equivalent test in tests/test_cli.py).
    def fake_replication_scores(candidates, **kwargs):
        import numpy as np

        return np.zeros(candidates.shape[0], dtype=np.int64)

    monkeypatch.setattr(
        "computational_life.analysis.replication.replication_scores", fake_replication_scores
    )

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    at.checkbox(key="auto_scan").set_value(True).run(timeout=30)
    at.number_input(key="auto_scan_interval").set_value(1).run(timeout=30)
    at.number_input(key="auto_scan_sample_size").set_value(5).run(timeout=30)
    next(ni for ni in at.number_input if ni.label == "Epochs per step").set_value(1).run(
        timeout=30
    )

    step_button = next(b for b in at.button if b.label == "Step")
    step_button.click().run(timeout=30)
    assert not at.exception
    assert any("Last auto-scan: epoch 1" in c.value for c in at.caption)


def test_auto_scan_flags_first_candidate_detection(monkeypatch):
    def fake_replication_scores(candidates, **kwargs):
        import numpy as np

        return np.full(candidates.shape[0], candidates.shape[1])  # perfect score every time

    monkeypatch.setattr(
        "computational_life.analysis.replication.replication_scores", fake_replication_scores
    )

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    at.checkbox(key="auto_scan").set_value(True).run(timeout=30)
    at.number_input(key="auto_scan_interval").set_value(1).run(timeout=30)
    next(ni for ni in at.number_input if ni.label == "Epochs per step").set_value(1).run(
        timeout=30
    )

    step_button = next(b for b in at.button if b.label == "Step")
    step_button.click().run(timeout=30)
    assert not at.exception
    assert any("Candidate replicator first detected at epoch 1" in s.value for s in at.success)

    # Stepping again shouldn't re-flag -- only the first detection is notable.
    step_button.click().run(timeout=30)
    assert sum(1 for s in at.success if "first detected" in s.value) == 1


def _create_stored_run_with_checkpoint(runs_dir: Path) -> tuple[Path, int]:
    """Runs the real CLI to produce a genuine --db + --checkpoint-dir run
    inside the (isolated, per-test) runs directory, the same way a long
    overnight run would -- rather than hand-building fixtures that might
    not match what the CLI actually produces. Placing it under
    ``runs_dir`` (the _isolated_runs_dir fixture's directory) means the
    dashboard's own "Browse runs" table auto-discovers it, exactly as it
    would discover a real run under the project's actual runs/.
    """
    from computational_life.cli import main

    runs_dir.mkdir(parents=True, exist_ok=True)
    config_path = runs_dir / "fast.yaml"
    config_path.write_text(
        "experiment: bff_soup\n"
        "name: loadable_test\n"
        "seed: 9\n"
        "population:\n  size: 16\n  genome_length: 8\n"
        "execution:\n  max_steps: 100\n"
        "run:\n  epochs: 6\n  report_interval: 2\n"
    )
    db_path = runs_dir / "loadable.db"
    checkpoint_dir = runs_dir / "checkpoints"
    main(
        [
            "run",
            str(config_path),
            "--db",
            str(db_path),
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-interval",
            "2",
        ]
    )
    return db_path, 1  # first run in a fresh database always gets id 1


def _select_and_load_run(at: AppTest, experiment_name: str) -> None:
    """Simulate selecting a row in the "Browse runs" table and clicking
    its "Load run #..." button. AppTest has no click-a-dataframe-row
    helper, but st.dataframe's own selection state can be set
    programmatically through session_state (the same mechanism a real
    click updates), per Streamlit's own docs for DataframeState -- but
    that injected selection only takes effect for the one script rerun
    immediately after it's set (a real frontend click would re-send it
    on every subsequent interaction; a bare programmatic override
    doesn't), so it has to be re-asserted right before the run that
    processes the button click too, not only once up front.
    """
    table = at.dataframe[0].value
    row_index = int(table.index[table["experiment"] == experiment_name][0])
    run_id = int(table.loc[row_index, "id"])
    at.session_state["runs_browser_table"] = {"selection": {"rows": [row_index]}}
    at.run(timeout=30)

    load_button = next(
        b for b in at.button if b.label == f"Load run #{run_id} ({experiment_name})"
    )
    at.session_state["runs_browser_table"] = {"selection": {"rows": [row_index]}}
    load_button.click().run(timeout=30)


def test_load_stored_run_restores_population_and_history(capsys, _isolated_runs_dir):
    _create_stored_run_with_checkpoint(_isolated_runs_dir)
    capsys.readouterr()

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    _select_and_load_run(at, "loadable_test")
    assert not at.exception

    # The run finished at epoch 6, with its last checkpoint also at epoch 6.
    epoch_metric = at.metric[0]
    assert epoch_metric.value == "6"
    assert any("Viewing run #1" in info.value for info in at.info)


def test_load_stored_run_can_be_resumed_by_stepping(capsys, _isolated_runs_dir):
    _create_stored_run_with_checkpoint(_isolated_runs_dir)
    capsys.readouterr()

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    _select_and_load_run(at, "loadable_test")

    next(ni for ni in at.number_input if ni.label == "Epochs per step").set_value(3).run(
        timeout=30
    )
    next(b for b in at.button if b.label == "Step").click().run(timeout=30)
    assert not at.exception

    epoch_metric = at.metric[0]
    assert epoch_metric.value == "9"  # 6 (loaded) + 3 more


def test_reset_immediately_registers_a_run_id():
    # "the same process as the back-end": a run started here should get
    # a real run_id right away, before any stepping -- not only once
    # some opt-in feature is switched on.
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    assert not at.exception
    assert any(c.value.startswith("**Run #") for c in at.caption)

    reset_button = next(b for b in at.button if "Reset" in b.label)
    reset_button.click().run(timeout=30)
    assert not at.exception
    assert any(c.value.startswith("**Run #") for c in at.caption)


def test_checkpoint_interval_input_always_visible_and_persists_to_disk(_isolated_runs_dir):
    from computational_life.storage.database import RunStore

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    # No checkbox to enable first -- persistence is on by default now.
    assert any(ni.key == "checkpoint_interval" for ni in at.number_input)

    at.number_input(key="checkpoint_interval").set_value(10).run(timeout=30)
    next(ni for ni in at.number_input if ni.label == "Epochs per step").set_value(10).run(
        timeout=30
    )
    next(b for b in at.button if b.label == "Step").click().run(timeout=30)
    assert not at.exception
    assert any("Last checkpoint: epoch 10" in c.value for c in at.caption)

    db_path = _isolated_runs_dir / "dashboard_runs.db"
    with RunStore(db_path) as store:
        events = store.get_events(1)
    checkpoint_events = [e for e in events if e["kind"] == "checkpoint_saved"]
    assert len(checkpoint_events) == 1
    assert checkpoint_events[0]["epoch"] == 10
    assert Path(checkpoint_events[0]["payload"]["path"]).exists()


def test_metrics_are_persisted_every_step_not_only_at_checkpoints(_isolated_runs_dir):
    # checkpoint_interval defaults to 500; a single small Step should
    # still leave a metrics row behind, since metrics recording isn't
    # gated by the (much heavier) checkpoint cadence.
    from computational_life.storage.database import RunStore

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    next(ni for ni in at.number_input if ni.label == "Epochs per step").set_value(3).run(
        timeout=30
    )
    next(b for b in at.button if b.label == "Step").click().run(timeout=30)
    assert not at.exception

    db_path = _isolated_runs_dir / "dashboard_runs.db"
    with RunStore(db_path) as store:
        history = store.get_metrics_history(1)
    assert any(row["epoch"] == 3 for row in history)


def test_browse_runs_lists_runs_across_multiple_databases(_isolated_runs_dir):
    _create_stored_run_with_checkpoint(_isolated_runs_dir)

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    assert not at.exception

    table = at.dataframe[0].value
    # The freshly (re)initialized default session (in dashboard_runs.db)
    # and the CLI-produced run (in loadable.db) should both be listed,
    # tagged with their own database.
    assert "bff_dev" in table["experiment"].values
    assert "loadable_test" in table["experiment"].values
    assert table["database"].nunique() == 2


def test_load_stored_run_without_checkpoint_shows_error(_isolated_runs_dir):
    from computational_life.cli import main

    _isolated_runs_dir.mkdir(parents=True, exist_ok=True)
    config_path = _isolated_runs_dir / "fast.yaml"
    config_path.write_text(
        "experiment: bff_soup\nname: no_checkpoint\nseed: 1\n"
        "population:\n  size: 8\n  genome_length: 8\n"
        "execution:\n  max_steps: 50\n"
        "run:\n  epochs: 2\n"
    )
    db_path = _isolated_runs_dir / "no_checkpoint.db"
    main(["run", str(config_path), "--db", str(db_path)])  # no --checkpoint-dir

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    _select_and_load_run(at, "no_checkpoint")

    assert not at.exception
    assert any("no saved checkpoint" in e.value for e in at.error)


def _create_two_stored_runs(tmp_path) -> Path:
    from computational_life.cli import main

    config_path = tmp_path / "fast.yaml"
    config_path.write_text(
        "experiment: bff_soup\n"
        "name: compare_test\n"
        "seed: 1\n"
        "population:\n  size: 16\n  genome_length: 8\n"
        "execution:\n  max_steps: 100\n"
        "run:\n  epochs: 4\n  report_interval: 2\n"
    )
    db_path = tmp_path / "compare.db"
    main(["run", str(config_path), "--db", str(db_path)])
    main(["run", str(config_path), "--seed", "2", "--db", str(db_path)])
    return db_path


def test_compare_runs_populates_run_selector(tmp_path, capsys):
    db_path = _create_two_stored_runs(tmp_path)
    capsys.readouterr()

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    at.text_input(key="compare_db_path").set_value(str(db_path)).run(timeout=30)
    assert not at.exception

    run_multiselect = at.multiselect(key="compare_run_labels")
    assert len(run_multiselect.options) == 2


def test_compare_runs_selecting_runs_renders_without_exception(tmp_path, capsys):
    db_path = _create_two_stored_runs(tmp_path)
    capsys.readouterr()

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    at.text_input(key="compare_db_path").set_value(str(db_path)).run(timeout=30)

    run_multiselect = at.multiselect(key="compare_run_labels")
    run_multiselect.set_value(run_multiselect.options).run(timeout=30)
    assert not at.exception

    metric_select = at.selectbox(key="compare_metric")
    metric_select.select("unique_genomes").run(timeout=30)
    assert not at.exception


def test_reset_reinitializes_deterministically():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    step_button = next(b for b in at.button if b.label == "Step")
    step_button.click().run(timeout=30)

    reset_button = next(b for b in at.button if "Reset" in b.label)
    reset_button.click().run(timeout=30)
    assert not at.exception
    epoch_metric = at.metric[0]
    assert epoch_metric.value == "0"
