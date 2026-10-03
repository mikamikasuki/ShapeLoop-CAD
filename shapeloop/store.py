"""SQLite records; designs and artifacts live outside the source checkout."""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def data_directory() -> Path:
    return Path(os.environ.get("SHAPELOOP_DATA_DIR", str(Path.home() / ".local/share/shapeloop"))).expanduser().resolve()

class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "projects.sqlite"
        self.lock = threading.RLock()
        with self.connect() as conn:
            conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, project_id TEXT,
                data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS record_kind ON records(kind, project_id);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, event TEXT, created_at TEXT
            );
            """)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def insert(self, kind: str, data: dict, project_id: str | None = None, id: str | None = None) -> dict:
        record = dict(data)
        record.update(id=id or uuid.uuid4().hex, created_at=now(), updated_at=now())
        with self.lock, self.connect() as conn:
            conn.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
                         (record["id"], kind, project_id, json.dumps(record), record["created_at"], record["updated_at"]))
        return record

    def get(self, id: str, kind: str | None = None) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT kind, data FROM records WHERE id=?", (id,)).fetchone()
        if not row or (kind and row["kind"] != kind):
            raise KeyError(f"{kind or 'Record'} {id} not found")
        return json.loads(row["data"])

    def update(self, id: str, **changes: Any) -> dict:
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT data FROM records WHERE id=?", (id,)).fetchone()
            if not row:
                raise KeyError(id)
            record = json.loads(row["data"])
            record.update(changes, updated_at=now())
            conn.execute("UPDATE records SET data=?, updated_at=? WHERE id=?", (json.dumps(record), record["updated_at"], id))
        return record

    def list(self, kind: str, project_id: str | None = None) -> list[dict]:
        with self.connect() as conn:
            if project_id is None:
                rows = conn.execute("SELECT data FROM records WHERE kind=? ORDER BY created_at DESC", (kind,)).fetchall()
            else:
                rows = conn.execute("SELECT data FROM records WHERE kind=? AND project_id=? ORDER BY created_at ASC", (kind, project_id)).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def event(self, job_id: str, event: dict):
        with self.lock, self.connect() as conn:
            conn.execute("INSERT INTO events(job_id,event,created_at) VALUES (?,?,?)", (job_id,json.dumps(event),now()))

    def events(self, job_id: str, after: int = 0):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM events WHERE job_id=? AND seq>? ORDER BY seq", (job_id, after)).fetchall()
        return [{**dict(row), "event":json.loads(row["event"])} for row in rows]

    def recover_jobs(self):
        for job in self.list("job"):
            if job["status"] in {"queued", "running", "verifying", "cancelling"}:
                owner=job.get('owner_pid')
                if owner and owner!=os.getpid():
                    try:
                        os.kill(owner,0)
                        continue  # Another local service still owns this durable job.
                    except (ProcessLookupError,PermissionError):
                        pass
                self.update(job["id"], status="interrupted", error="Application stopped during this job. Retry to rebuild this revision.")
                if job.get("revision_id"):
                    self.update(job["revision_id"], status="interrupted")
                self.event(job["id"], {"status":"interrupted"})
