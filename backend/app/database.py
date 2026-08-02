from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import settings


class JobRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.database_path
        self._lock = threading.Lock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL,
                    message TEXT,
                    options TEXT NOT NULL,
                    outputs TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    settings TEXT NOT NULL DEFAULT '{}',
                    analysis TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.commit()
        self._discover_projects()

    def create(self, job_id: str, project_id: str, project_name: str, options: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, 'queued', 0, 'Queued', NULL, ?, '[]', ?, ?)",
                (job_id, project_id, project_name, json.dumps(options), now, now),
            )
            db.commit()
        return self.get(job_id)

    def update(self, job_id: str, **values: Any) -> dict[str, Any]:
        allowed = {"status", "progress", "stage", "message", "outputs"}
        values = {key: value for key, value in values.items() if key in allowed}
        if "outputs" in values:
            values["outputs"] = json.dumps(values["outputs"])
        values["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._lock, self._connect() as db:
            db.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*values.values(), job_id))
            db.commit()
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._decode(dict(row))

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode(dict(row)) for row in rows]

    def recover_interrupted(self) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status='failed', stage='Interrupted', message='The server stopped during rendering' "
                "WHERE status IN ('queued', 'analyzing', 'rendering')"
            )
            db.commit()

    def create_project(self, project_id: str, name: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO projects (id,name,status,settings,analysis,created_at,updated_at) VALUES (?,?,'draft','{}','{}',?,?)",
                (project_id, name, now, now),
            )
            db.commit()
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(project_id)
        return self._decode_project(dict(row))

    def list_projects(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode_project(dict(row)) for row in rows]

    def update_project(self, project_id: str, **values: Any) -> dict[str, Any]:
        allowed = {"name", "status", "settings", "analysis"}
        values = {key: value for key, value in values.items() if key in allowed}
        for key in ("settings", "analysis"):
            if key in values:
                values[key] = json.dumps(values[key])
        values["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key}=?" for key in values)
        with self._lock, self._connect() as db:
            cursor = db.execute(f"UPDATE projects SET {assignments} WHERE id=?", (*values.values(), project_id))
            if cursor.rowcount == 0:
                raise KeyError(project_id)
            db.commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM jobs WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            db.commit()

    def _discover_projects(self) -> None:
        settings.projects_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            known = {row[0] for row in db.execute("SELECT id FROM projects")}
            now = datetime.now(UTC).isoformat()
            for root in settings.projects_dir.iterdir():
                name_file = root / "project.name"
                if root.is_dir() and root.name not in known and name_file.exists():
                    name = name_file.read_text(encoding="utf-8", errors="replace").strip() or "Untitled"
                    stamp = datetime.fromtimestamp(root.stat().st_mtime, UTC).isoformat()
                    db.execute("INSERT INTO projects VALUES (?,?,'draft','{}','{}',?,?)", (root.name, name, stamp, stamp or now))
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        row["outputs"] = json.loads(row["outputs"])
        row["options"] = json.loads(row["options"])
        return row

    @staticmethod
    def _decode_project(row: dict[str, Any]) -> dict[str, Any]:
        row["settings"] = json.loads(row["settings"] or "{}")
        row["analysis"] = json.loads(row["analysis"] or "{}")
        return row


repository = JobRepository()
