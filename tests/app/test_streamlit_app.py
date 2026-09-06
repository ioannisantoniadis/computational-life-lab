"""Headless smoke test for the Streamlit dashboard.

Runs the actual app script (not a reimplementation of it) via Streamlit's
AppTest harness, so a broken import or a widget wired to the wrong session
key fails a fast pytest run instead of only showing up when someone
happens to click around in a browser.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"


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
    assert len(at.dataframe) == 1


def _create_stored_run_with_checkpoint(tmp_path) -> tuple[Path, int]:
    """Runs the real CLI to produce a genuine --db + --checkpoint-dir run,
    the same way a long overnight run would -- rather than hand-building
    fixtures that might not match what the CLI actually produces.
    """
    from computational_life.cli import main

    config_path = tmp_path / "fast.yaml"
    config_path.write_text(
        "experiment: bff_soup\n"
        "name: loadable_test\n"
        "seed: 9\n"
        "population:\n  size: 16\n  genome_length: 8\n"
        "execution:\n  max_steps: 100\n"
        "run:\n  epochs: 6\n  report_interval: 2\n"
    )
    db_path = tmp_path / "loadable.db"
    checkpoint_dir = tmp_path / "checkpoints"
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


def test_load_stored_run_restores_population_and_history(tmp_path, capsys):
    db_path, run_id = _create_stored_run_with_checkpoint(tmp_path)
    capsys.readouterr()

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    at.text_input(key="load_db_path").set_value(str(db_path)).run(timeout=30)
    assert not at.exception

    run_select = at.selectbox(key="load_run_label")
    assert f"#{run_id}" in run_select.options[0]
    run_select.select(run_select.options[0]).run(timeout=30)

    next(b for b in at.button if b.label == "Load this run").click().run(timeout=30)
    assert not at.exception

    # The run finished at epoch 6, with its last checkpoint also at epoch 6.
    epoch_metric = at.metric[0]
    assert epoch_metric.value == "6"
    assert any("Viewing run #1" in info.value for info in at.info)


def test_load_stored_run_can_be_resumed_by_stepping(tmp_path, capsys):
    db_path, run_id = _create_stored_run_with_checkpoint(tmp_path)
    capsys.readouterr()

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    at.text_input(key="load_db_path").set_value(str(db_path)).run(timeout=30)
    run_select = at.selectbox(key="load_run_label")
    run_select.select(run_select.options[0]).run(timeout=30)
    next(b for b in at.button if b.label == "Load this run").click().run(timeout=30)

    next(ni for ni in at.number_input if ni.label == "Epochs per step").set_value(3).run(
        timeout=30
    )
    next(b for b in at.button if b.label == "Step").click().run(timeout=30)
    assert not at.exception

    epoch_metric = at.metric[0]
    assert epoch_metric.value == "9"  # 6 (loaded) + 3 more


def test_load_stored_run_without_checkpoint_shows_error(tmp_path):
    from computational_life.cli import main

    config_path = tmp_path / "fast.yaml"
    config_path.write_text(
        "experiment: bff_soup\nname: no_checkpoint\nseed: 1\n"
        "population:\n  size: 8\n  genome_length: 8\n"
        "execution:\n  max_steps: 50\n"
        "run:\n  epochs: 2\n"
    )
    db_path = tmp_path / "no_checkpoint.db"
    main(["run", str(config_path), "--db", str(db_path)])  # no --checkpoint-dir

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    at.text_input(key="load_db_path").set_value(str(db_path)).run(timeout=30)
    run_select = at.selectbox(key="load_run_label")
    run_select.select(run_select.options[0]).run(timeout=30)
    next(b for b in at.button if b.label == "Load this run").click().run(timeout=30)

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
