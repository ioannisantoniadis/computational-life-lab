"""SQLite persistence for experiment runs (spec section 23).

Stores exactly what's needed to reproduce and analyze a run later:
the experiment name, the full raw config, the seed, the software
version, and a metrics/events history. Deliberately does *not* store
per-step interpreter traces -- only the periodic snapshots a run already
computes for reporting (spec: "avoid writing every interpreter
instruction to SQLite").

Metrics are stored in a tidy long format (run_id, epoch, name, value)
rather than one column per metric, so adding a new metric later never
requires a schema migration.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .. import __version__

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_name TEXT NOT NULL,
    config_yaml TEXT NOT NULL,
    seed INTEGER NOT NULL,
    software_version TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    final_epoch INTEGER,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS metrics (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    epoch INTEGER NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_run_epoch ON metrics(run_id, epoch);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    epoch INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
"""


class RunStore:
    """A SQLite-backed store for experiment run metadata, metrics, and events."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> RunStore:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def start_run(self, *, experiment_name: str, config_text: str, seed: int) -> int:
        """Register a new run and return its id."""
        cur = self._conn.execute(
            "INSERT INTO runs (experiment_name, config_yaml, seed, software_version, "
            "started_at, status) VALUES (?, ?, ?, ?, ?, 'running')",
            (experiment_name, config_text, seed, __version__, time.time()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def record_metrics(self, run_id: int, epoch: int, metrics: dict) -> None:
        rows = [
            (run_id, epoch, name, float(value))
            for name, value in metrics.items()
            if name != "epoch" and isinstance(value, (int, float))
        ]
        self._conn.executemany(
            "INSERT INTO metrics (run_id, epoch, name, value) VALUES (?, ?, ?, ?)", rows
        )
        self._conn.commit()

    def record_event(self, run_id: int, epoch: int, kind: str, payload: dict | None = None) -> None:
        self._conn.execute(
            "INSERT INTO events (run_id, epoch, kind, payload) VALUES (?, ?, ?, ?)",
            (run_id, epoch, kind, json.dumps(payload) if payload is not None else None),
        )
        self._conn.commit()

    def finish_run(self, run_id: int, final_epoch: int, *, status: str = "completed") -> None:
        self._conn.execute(
            "UPDATE runs SET finished_at = ?, final_epoch = ?, status = ? WHERE id = ?",
            (time.time(), final_epoch, status, run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: int) -> dict:
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"No run with id {run_id}")
        return dict(row)

    def list_runs(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def get_events(self, run_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT epoch, kind, payload FROM events WHERE run_id = ? ORDER BY epoch", (run_id,)
        ).fetchall()
        return [
            {
                "epoch": row["epoch"],
                "kind": row["kind"],
                "payload": json.loads(row["payload"]) if row["payload"] else None,
            }
            for row in rows
        ]

    def get_metrics_history(self, run_id: int) -> list[dict]:
        """Metrics pivoted to one row per epoch: [{"epoch": 0, "name1": v, ...}, ...]."""
        rows = self._conn.execute(
            "SELECT epoch, name, value FROM metrics WHERE run_id = ? ORDER BY epoch", (run_id,)
        ).fetchall()
        by_epoch: dict[int, dict] = {}
        for row in rows:
            record = by_epoch.setdefault(row["epoch"], {"epoch": row["epoch"]})
            record[row["name"]] = row["value"]
        return [by_epoch[epoch] for epoch in sorted(by_epoch)]

    def latest_metrics(self, run_id: int) -> dict | None:
        history = self.get_metrics_history(run_id)
        return history[-1] if history else None
