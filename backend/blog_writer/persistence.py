"""SQLite checkpoint and run-registry persistence helpers."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from . import config
from .models import EvidenceItem, Plan


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = PROJECT_DIR / "data" / "blog_writer.sqlite3"
PROCESS_INSTANCE_ID = uuid4().hex


def _database_path() -> Path:
    """Resolve the database location from environment or project defaults."""
    configured = os.getenv("BLOG_WRITER_DB_PATH")
    if not configured:
        return DEFAULT_DATABASE_PATH
    path = Path(configured).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


DATABASE_PATH = _database_path()
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

ALLOWED_CHECKPOINT_TYPES = [
    ("blog_writer.models", "EvidenceItem"),
    ("blog_writer.models", "EvidencePack"),
    ("blog_writer.models", "GlobalImagePlan"),
    ("blog_writer.models", "ImageSpec"),
    ("blog_writer.models", "Plan"),
    ("blog_writer.models", "RouterDecision"),
    ("blog_writer.models", "Task"),
]


def checkpoint_serializer() -> JsonPlusSerializer:
    """Limit checkpoint deserialization to the project model classes."""
    return JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_CHECKPOINT_TYPES)


def _json_default(value: Any) -> Any:
    """Encode Pydantic models and common Python types for run metadata JSON."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_dumps(value: Any) -> str:
    """Serialize run metadata with the project-specific JSON fallback."""
    return json.dumps(value, default=_json_default, ensure_ascii=False)


def _json_loads(value: str | None, fallback: Any) -> Any:
    """Deserialize run metadata while allowing empty database fields."""
    if not value:
        return fallback
    return json.loads(value)


def restore_state_types(state: dict[str, Any]) -> dict[str, Any]:
    """Rehydrate persisted JSON state into Pydantic objects and tuple sections."""
    restored = dict(state)
    restored.setdefault("max_results_per_query", config.DEFAULT_MAX_RESULTS_PER_QUERY)
    restored.setdefault("research_errors", [])
    restored.setdefault("artifact_path", "")
    if isinstance(restored.get("plan"), dict):
        restored["plan"] = Plan.model_validate(restored["plan"])
    restored["evidence"] = [
        item if isinstance(item, EvidenceItem) else EvidenceItem.model_validate(item)
        for item in restored.get("evidence", [])
    ]
    restored["sections"] = [tuple(section) for section in restored.get("sections", [])]
    return restored


class RunStore:
    """Small SQLite repository for Streamlit-facing run metadata."""

    def __init__(self, path: Path) -> None:
        """Create a store backed by the given SQLite database path."""
        self.path = path
        self._setup()

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection configured for concurrent local writes."""
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _setup(self) -> None:
        """Create the run registry table and indexes when missing."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS blog_runs (
                    run_id TEXT PRIMARY KEY,
                    checkpoint_thread_id TEXT NOT NULL UNIQUE,
                    process_instance_id TEXT NOT NULL,
                    blog_id TEXT,
                    phase TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    node_counts_json TEXT NOT NULL,
                    logs_json TEXT NOT NULL,
                    error TEXT,
                    elapsed_seconds REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_blog_runs_updated_at
                    ON blog_runs(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_blog_runs_status
                    ON blog_runs(status);
                """
            )

    def mark_orphaned_runs(self) -> int:
        """Mark runs from older processes as interrupted on application startup."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE blog_runs
                SET status = 'interrupted', updated_at = ?
                WHERE status IN ('created', 'running', 'cancelling')
                  AND process_instance_id != ?
                """,
                (now, PROCESS_INSTANCE_ID),
            )
            return cursor.rowcount

    def create_run(
        self,
        *,
        run_id: str,
        checkpoint_thread_id: str,
        phase: str,
        state: dict[str, Any],
    ) -> None:
        """Insert the initial metadata row for a newly started graph phase."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO blog_runs (
                    run_id, checkpoint_thread_id, process_instance_id,
                    blog_id, phase, topic, status, state_json,
                    metrics_json, node_counts_json, logs_json,
                    error, elapsed_seconds, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'created', ?, '{}', '{}', '[]', NULL, 0, ?, ?)
                """,
                (
                    run_id,
                    checkpoint_thread_id,
                    PROCESS_INSTANCE_ID,
                    str(state.get("blog_id") or ""),
                    phase,
                    str(state.get("topic") or state.get("seed_topic") or ""),
                    _json_dumps(state),
                    now,
                    now,
                ),
            )

    def update_run(
        self,
        *,
        run_id: str,
        status: str,
        state: dict[str, Any],
        metrics: dict[str, Any],
        node_counts: dict[str, int],
        logs: list[str],
        elapsed_seconds: float,
        error: str | None,
    ) -> None:
        """Update a run row with the latest status, state, metrics, and logs."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE blog_runs
                SET process_instance_id = ?, status = ?, state_json = ?,
                    metrics_json = ?, node_counts_json = ?, logs_json = ?,
                    error = ?, elapsed_seconds = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    PROCESS_INSTANCE_ID,
                    status,
                    _json_dumps(state),
                    _json_dumps(metrics),
                    _json_dumps(node_counts),
                    _json_dumps(logs),
                    error,
                    elapsed_seconds,
                    now,
                    run_id,
                ),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Fetch and decode one persisted run by ID."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM blog_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._decode_row(row) if row else None

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        """Return recent runs newest-first for the sidebar controls."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM blog_runs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def get_blog_runs(self, blog_id: str) -> list[dict[str, str]]:
        """Find every phase belonging to one generated blog."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT run_id, checkpoint_thread_id, status FROM blog_runs WHERE blog_id = ?",
                (blog_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_blog(self, blog_id: str) -> int:
        """Remove finished run metadata and checkpoints for one blog."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT checkpoint_thread_id, status FROM blog_runs WHERE blog_id = ?",
                (blog_id,),
            ).fetchall()
            if any(row["status"] in {"created", "running", "cancelling"} for row in rows):
                raise ValueError("Wait for all blog phases to finish before deleting the blog.")
            threads = [row["checkpoint_thread_id"] for row in rows]
            tables = {
                row["name"]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            for table in ("writes", "checkpoints", "checkpoint_blobs"):
                if table in tables:
                    connection.executemany(
                        f"DELETE FROM {table} WHERE thread_id = ?",
                        [(thread_id,) for thread_id in threads],
                    )
            connection.execute("DELETE FROM blog_runs WHERE blog_id = ?", (blog_id,))
            return len(rows)

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a database row into the dictionary shape expected by the UI."""
        record = dict(row)
        record["state"] = restore_state_types(_json_loads(record.pop("state_json"), {}))
        record["metrics"] = _json_loads(record.pop("metrics_json"), {})
        record["node_counts"] = _json_loads(record.pop("node_counts_json"), {})
        record["logs"] = _json_loads(record.pop("logs_json"), [])
        return record


_checkpoint_connection = sqlite3.connect(
    DATABASE_PATH,
    timeout=30,
    check_same_thread=False,
)
_checkpoint_connection.execute("PRAGMA journal_mode=WAL")
_checkpoint_connection.execute("PRAGMA busy_timeout=30000")

checkpointer = SqliteSaver(_checkpoint_connection, serde=checkpoint_serializer())
run_store = RunStore(DATABASE_PATH)
run_store.mark_orphaned_runs()


__all__ = [
    "DATABASE_PATH",
    "PROCESS_INSTANCE_ID",
    "RunStore",
    "checkpointer",
    "checkpoint_serializer",
    "restore_state_types",
    "run_store",
]
