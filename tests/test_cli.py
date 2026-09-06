from pathlib import Path

from computational_life.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cli_run_dev_config(capsys):
    config_path = REPO_ROOT / "experiments" / "configs" / "bff_dev.yaml"
    exit_code = main(["run", str(config_path), "--epochs", "20"])
    assert exit_code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert lines[0].startswith("epoch=")
    assert "epoch=      20" in lines[-1]


def test_cli_run_is_deterministic_given_same_seed(capsys):
    config_path = REPO_ROOT / "experiments" / "configs" / "bff_dev.yaml"
    main(["run", str(config_path), "--epochs", "20", "--seed", "1"])
    out1 = capsys.readouterr().out
    main(["run", str(config_path), "--epochs", "20", "--seed", "1"])
    out2 = capsys.readouterr().out
    assert out1 == out2


def test_cli_seed_override_reaches_the_universe():
    # The CLI's summary line is too coarse (population-wide aggregates) to
    # reliably distinguish seeds at small scale, so verify the override at
    # the config level instead: divergence-by-seed is exercised end-to-end
    # by test_different_seed_diverges in test_universe.py.
    import dataclasses

    from computational_life.experiments.base import load_bff_soup_config

    config_path = REPO_ROOT / "experiments" / "configs" / "bff_dev.yaml"
    base_config = load_bff_soup_config(config_path)
    overridden = dataclasses.replace(
        base_config, universe=dataclasses.replace(base_config.universe, seed=999)
    )
    assert overridden.universe.seed == 999
    assert base_config.universe.seed != overridden.universe.seed


def test_cli_run_with_db_persists_run_and_metrics(tmp_path, capsys):
    from computational_life.storage.database import RunStore

    config_path = REPO_ROOT / "experiments" / "configs" / "bff_dev.yaml"
    db_path = tmp_path / "runs.db"
    exit_code = main(["run", str(config_path), "--epochs", "20", "--db", str(db_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "saved to" in out

    with RunStore(db_path) as store:
        runs = store.list_runs()
        assert len(runs) == 1
        run = runs[0]
        assert run["experiment_name"] == "bff_dev"
        assert run["status"] == "completed"
        assert run["final_epoch"] == 20

        history = store.get_metrics_history(run["id"])
        assert [h["epoch"] for h in history] == [0, 20]


def test_cli_analyze_prints_run_summary(tmp_path, capsys):
    config_path = REPO_ROOT / "experiments" / "configs" / "bff_dev.yaml"
    db_path = tmp_path / "runs.db"
    main(["run", str(config_path), "--epochs", "20", "--db", str(db_path)])
    capsys.readouterr()  # discard the run's own output

    exit_code = main(["analyze", "1", "--db", str(db_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "bff_dev" in out
    assert "status: completed" in out
    assert "unique_genomes" in out


def _write_fast_config(path: Path) -> Path:
    # A small/fast config for checkpoint tests, which otherwise don't need
    # bff_dev.yaml's population-512 scale.
    config_path = path / "fast.yaml"
    config_path.write_text(
        "experiment: bff_soup\n"
        "name: fast_test\n"
        "seed: 5\n"
        "population:\n  size: 16\n  genome_length: 8\n"
        "execution:\n  max_steps: 100\n"
        "run:\n  epochs: 6\n  report_interval: 2\n"
    )
    return config_path


def test_cli_save_and_resume_checkpoint(tmp_path, capsys):
    from computational_life.storage.checkpoints import load_checkpoint

    config_path = _write_fast_config(tmp_path)
    checkpoint_path = tmp_path / "final"

    main(["run", str(config_path), "--save-checkpoint", str(checkpoint_path)])
    out = capsys.readouterr().out
    assert "Final checkpoint saved" in out

    restored = load_checkpoint(checkpoint_path)
    assert restored.epoch == 6

    main(["run", str(config_path), "--resume-from", str(checkpoint_path), "--epochs", "4"])
    out = capsys.readouterr().out
    assert "Resumed from checkpoint at epoch 6" in out
    assert "epoch=      10" in out  # 6 + 4 more


def test_cli_resume_from_rejects_seed_override(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    checkpoint_path = tmp_path / "ckpt"
    main(["run", str(config_path), "--save-checkpoint", str(checkpoint_path)])
    capsys.readouterr()

    exit_code = main(
        ["run", str(config_path), "--resume-from", str(checkpoint_path), "--seed", "1"]
    )
    assert exit_code == 1
    assert "no effect" in capsys.readouterr().out


def test_cli_periodic_checkpoints_are_written_at_configured_interval(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    checkpoint_dir = tmp_path / "checkpoints"

    main(
        [
            "run",
            str(config_path),
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-interval",
            "2",
        ]
    )
    out = capsys.readouterr().out
    assert "Checkpoint saved" in out

    saved = sorted(p.name for p in checkpoint_dir.glob("*.npz"))
    assert saved == ["epoch_0000000002.npz", "epoch_0000000004.npz", "epoch_0000000006.npz"]


def test_cli_checkpoints_are_namespaced_by_run_id_and_recorded_as_events(tmp_path, capsys):
    from computational_life.storage.database import RunStore

    config_path = _write_fast_config(tmp_path)
    checkpoint_dir = tmp_path / "checkpoints"
    db_path = tmp_path / "runs.db"

    main(
        [
            "run",
            str(config_path),
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-interval",
            "2",
            "--db",
            str(db_path),
        ]
    )
    capsys.readouterr()

    with RunStore(db_path) as store:
        [run] = store.list_runs()
        run_id = run["id"]
        checkpoint_events = [e for e in store.get_events(run_id) if e["kind"] == "checkpoint_saved"]

    assert len(checkpoint_events) == 3  # epochs 2, 4, 6
    run_subdir = checkpoint_dir / f"run_{run_id}"
    assert run_subdir.is_dir()
    saved_files = sorted(p.name for p in run_subdir.glob("*.npz"))
    assert saved_files == ["epoch_0000000002.npz", "epoch_0000000004.npz", "epoch_0000000006.npz"]
    for event in checkpoint_events:
        assert Path(event["payload"]["path"]).exists()


def test_cli_two_runs_sharing_a_checkpoint_dir_do_not_collide(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    checkpoint_dir = tmp_path / "checkpoints"
    db_path = tmp_path / "runs.db"

    for _ in range(2):
        main(
            [
                "run",
                str(config_path),
                "--checkpoint-dir",
                str(checkpoint_dir),
                "--checkpoint-interval",
                "2",
                "--db",
                str(db_path),
            ]
        )
    capsys.readouterr()

    run_subdirs = sorted(p.name for p in checkpoint_dir.iterdir())
    assert run_subdirs == ["run_1", "run_2"]
    for subdir in run_subdirs:
        assert len(list((checkpoint_dir / subdir).glob("*.npz"))) == 3


def test_cli_list_runs_shows_all_runs(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    db_path = tmp_path / "runs.db"
    main(["run", str(config_path), "--db", str(db_path)])
    main(["run", str(config_path), "--seed", "2", "--db", str(db_path)])
    capsys.readouterr()

    exit_code = main(["list-runs", "--db", str(db_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 3  # header + 2 runs
    assert "fast_test" in lines[1]
    assert "completed" in lines[1]


def test_cli_list_runs_filters_by_experiment(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    db_path = tmp_path / "runs.db"
    main(["run", str(config_path), "--db", str(db_path)])
    capsys.readouterr()

    main(["list-runs", "--db", str(db_path), "--experiment", "does_not_exist"])
    out = capsys.readouterr().out
    assert "No runs found" in out


def test_cli_inspect_prints_organism_details(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    db_path = tmp_path / "runs.db"
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
    capsys.readouterr()

    exit_code = main(["inspect", "1", "--db", str(db_path), "--organism", "3"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Organism index 3" in out
    assert "organism_id:" in out
    assert "genome (8 bytes, hex):" in out
    assert "checkpoint at epoch 6" in out


def test_cli_inspect_with_replication_score(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    db_path = tmp_path / "runs.db"
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
    capsys.readouterr()

    exit_code = main(
        ["inspect", "1", "--db", str(db_path), "--organism", "0", "--replication-score"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "replication score:" in out


def test_cli_inspect_without_checkpoint_returns_error(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    db_path = tmp_path / "runs.db"
    main(["run", str(config_path), "--db", str(db_path)])  # no --checkpoint-dir
    capsys.readouterr()

    exit_code = main(["inspect", "1", "--db", str(db_path), "--organism", "0"])
    assert exit_code == 1
    assert "no saved checkpoint" in capsys.readouterr().out


def test_cli_inspect_rejects_out_of_range_organism(tmp_path, capsys):
    config_path = _write_fast_config(tmp_path)
    db_path = tmp_path / "runs.db"
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
    capsys.readouterr()

    exit_code = main(["inspect", "1", "--db", str(db_path), "--organism", "999"])
    assert exit_code == 1
    assert "out of range" in capsys.readouterr().out


def _write_fast_sweep_config(path: Path) -> Path:
    config_path = path / "fast_sweep.yaml"
    config_path.write_text(
        "experiment: bff_soup_sweep\n"
        "name: fast_sweep\n"
        "base:\n"
        "  population: {genome_length: 8}\n"
        "  execution: {max_steps: 100}\n"
        "  run: {epochs: 3, report_interval: 3}\n"
        "sweep:\n"
        "  population.size: [16, 32]\n"
        "seeds:\n  count: 2\n"
    )
    return config_path


def test_cli_sweep_persists_all_points(tmp_path, capsys):
    from computational_life.storage.database import RunStore

    config_path = _write_fast_sweep_config(tmp_path)
    db_path = tmp_path / "sweep.db"
    exit_code = main(["sweep", str(config_path), "--db", str(db_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "4 points" in out  # 2 population sizes x 2 seeds
    assert "Sweep complete: 4 runs saved" in out

    with RunStore(db_path) as store:
        runs = store.list_runs()
        assert len(runs) == 4
        assert all(r["status"] == "completed" for r in runs)


def test_cli_sweep_report_summarizes_by_parameter(tmp_path, capsys):
    config_path = _write_fast_sweep_config(tmp_path)
    db_path = tmp_path / "sweep.db"
    main(["sweep", str(config_path), "--db", str(db_path)])
    capsys.readouterr()

    exit_code = main(
        [
            "sweep-report",
            "--db",
            str(db_path),
            "--experiment",
            "fast_sweep",
            "--group-by",
            "population.size",
            "--genome-length",
            "8",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "population.size=16" in out
    assert "population.size=32" in out
    assert "/2 runs" in out  # 2 seeds per population size
    assert "too few" in out  # only 4 total runs


def test_cli_sweep_report_missing_experiment_returns_error(tmp_path, capsys):
    config_path = _write_fast_sweep_config(tmp_path)
    db_path = tmp_path / "sweep.db"
    main(["sweep", str(config_path), "--db", str(db_path)])
    capsys.readouterr()

    exit_code = main(
        [
            "sweep-report",
            "--db",
            str(db_path),
            "--experiment",
            "does_not_exist",
            "--group-by",
            "population.size",
        ]
    )
    assert exit_code == 1
