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
