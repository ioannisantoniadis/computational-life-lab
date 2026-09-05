from pathlib import Path

import pytest

from computational_life.experiments.base import load_bff_soup_config

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = REPO_ROOT / "experiments" / "configs"


def test_load_bff_baseline_config():
    config = load_bff_soup_config(CONFIGS / "bff_baseline.yaml")
    assert config.name == "bff_baseline"
    assert config.seed == 12345
    assert config.universe.population_size == 131_072
    assert config.universe.genome_length == 64
    assert config.universe.max_steps == 8192
    assert config.universe.mutation_enabled is False
    assert config.epochs == 20_000
    assert config.report_interval == 100


def test_load_bff_dev_config():
    config = load_bff_soup_config(CONFIGS / "bff_dev.yaml")
    assert config.universe.population_size == 512
    assert config.epochs == 200


def test_rejects_wrong_experiment_kind(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("experiment: not_bff_soup\nseed: 1\n")
    with pytest.raises(ValueError):
        load_bff_soup_config(bad)


def test_defaults_when_sections_missing(tmp_path):
    minimal = tmp_path / "minimal.yaml"
    minimal.write_text("experiment: bff_soup\nseed: 7\n")
    config = load_bff_soup_config(minimal)
    assert config.universe.population_size == 131_072
    assert config.universe.mutation_enabled is False
    assert config.epochs == 1000
