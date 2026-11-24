from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import ActionResult, now


SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    scenario TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    actor TEXT NOT NULL,
    agent TEXT NOT NULL,
    tool TEXT NOT NULL,
    target TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    external_id TEXT,
    payload TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._ensure_column("experiments", "company", "company TEXT NOT NULL DEFAULT ''")
            self._ensure_column("actions", "payload", "payload TEXT")
            self._conn.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        """Best-effort migration for databases created before a column existed."""
        columns = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def reset(self) -> None:
        with self._lock:
            for table in ("actions", "metrics", "events", "experiments"):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.commit()

    def create_experiment(self, name: str, scenario: str, mode: str, company: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO experiments(name, company, scenario, mode, status, started_at) VALUES (?,?,?,?,?,?)",
                (name, company, scenario, mode, "running", now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def update_experiment(self, experiment_id: int, **fields: Any) -> None:
        if not fields:
            return
        keys = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [experiment_id]
        with self._lock:
            self._conn.execute(f"UPDATE experiments SET {keys} WHERE id=?", vals)
            self._conn.commit()

    def add_action(self, experiment_id: int, actor: str, agent: str, result: ActionResult) -> int:
        payload = json.dumps(result.payload or {}, ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO actions(experiment_id, actor, agent, tool, target, summary, status, error, external_id, payload, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    experiment_id, actor, agent, result.tool, result.target,
                    result.summary, result.status, result.error, result.external_id, payload, now(),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def add_metric(self, experiment_id: int, key: str, value: float, unit: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO metrics(experiment_id, key, value, unit, created_at) VALUES (?,?,?,?,?)",
                (experiment_id, key, float(value), unit, now()),
            )
            self._conn.commit()

    def add_event(self, experiment_id: int, type_: str, payload: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events(experiment_id, type, payload, created_at) VALUES (?,?,?,?)",
                (experiment_id, type_, payload, now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def latest_experiment(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM experiments ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def get_experiment(self, experiment_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        return dict(row) if row else None

    def list_actions(self, experiment_id: int, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM actions WHERE experiment_id=? ORDER BY id ASC LIMIT ?",
                (experiment_id, limit),
            ).fetchall()
        actions: list[dict[str, Any]] = []
        for row in rows:
            action = dict(row)
            raw = action.get("payload")
            if raw:
                try:
                    action["payload"] = json.loads(raw)
                except (TypeError, ValueError):
                    action["payload"] = {}
            else:
                action["payload"] = {}
            actions.append(action)
        return actions

    def list_metrics(self, experiment_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM metrics WHERE experiment_id=? ORDER BY id ASC",
                (experiment_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_events(self, experiment_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE experiment_id=? ORDER BY id ASC",
                (experiment_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_actions(self, experiment_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM actions WHERE experiment_id=?", (experiment_id,)
            ).fetchone()
        return int(row["n"]) if row else 0
