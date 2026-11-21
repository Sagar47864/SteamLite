"""SQLite persistence for completed Stream Mode sessions."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths


class SessionDatabase:
    def __init__(self) -> None:
        base = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / "streamlite.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        started_at TEXT NOT NULL,
                        ended_at TEXT NOT NULL,
                        game TEXT,
                        average_cpu REAL,
                        peak_cpu REAL,
                        average_gpu REAL,
                        peak_gpu REAL,
                        average_ram REAL,
                        peak_ram REAL,
                        network_dropped_percent REAL,
                        network_dropped_frames INTEGER,
                        rendering_lag_percent REAL,
                        encoding_lag_percent REAL,
                        stability INTEGER
                    )
                """)
                columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
                if "network_dropped_frames" not in columns:
                    connection.execute("ALTER TABLE sessions ADD COLUMN network_dropped_frames INTEGER")

    def save_session(self, session: dict[str, Any]) -> None:
        columns = (
            "started_at", "ended_at", "game", "average_cpu", "peak_cpu", "average_gpu", "peak_gpu",
            "average_ram", "peak_ram", "network_dropped_percent", "network_dropped_frames", "rendering_lag_percent",
            "encoding_lag_percent", "stability",
        )
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    f"INSERT INTO sessions ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    tuple(session.get(column) for column in columns),
                )

    def recent_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
