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
