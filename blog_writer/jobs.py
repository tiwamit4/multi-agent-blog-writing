"""Background execution wrapper for Streamlit-triggered LangGraph runs."""

from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Any
from uuid import uuid4

from .metrics import UsageMetricsCallback
from .persistence import RunStore, run_store


TERMINAL_JOB_STATUSES = {"completed", "cancelled", "failed"}


class GraphJob:
    """Run a compiled graph in a background thread with cooperative cancellation."""

    def __init__(
        self,
        graph: Any,
        inputs: dict[str, Any],
        phase: str,
        *,
        run_id: str | None = None,
        checkpoint_thread_id: str | None = None,
        resume: bool = False,
        initial_metrics: dict[str, Any] | None = None,
        initial_node_counts: dict[str, int] | None = None,
        initial_logs: list[str] | None = None,
        initial_elapsed_seconds: float = 0.0,
        store: RunStore = run_store,
    ) -> None:
        """Prepare a graph job and create its durable run record when new."""
        self.id = run_id or uuid4().hex
        self.graph = graph
        self.inputs = inputs
        self.phase = phase
        self.checkpoint_thread_id = checkpoint_thread_id or f"{self.id}:{phase}"
        self.resume_from_checkpoint = resume
        self.store = store
        self.metrics = UsageMetricsCallback(initial_metrics)
        self.cancel_event = threading.Event()
        self._lock = threading.RLock()
        self._status = "created"
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._elapsed_before = float(initial_elapsed_seconds)
        self._current_state: dict[str, Any] = dict(inputs)
        self._result: dict[str, Any] | None = None
        self._error: str | None = None
        self._traceback: str | None = None
        self._node_counts: dict[str, int] = dict(initial_node_counts or {})
        self._logs: list[str] = list(initial_logs or [])
        self._thread = threading.Thread(target=self._run, daemon=True)
        if not resume:
            self.store.create_run(
                run_id=self.id,
                checkpoint_thread_id=self.checkpoint_thread_id,
                phase=self.phase,
                state=self.inputs,
            )

    @classmethod
    def from_record(
        cls,
        graph: Any,
        record: dict[str, Any],
        *,
        store: RunStore = run_store,
    ) -> "GraphJob":
        """Recreate a job object from a persisted run before resuming it."""
        return cls(
            graph,
            record["state"],
            record["phase"],
            run_id=record["run_id"],
            checkpoint_thread_id=record["checkpoint_thread_id"],
            resume=True,
            initial_metrics=record.get("metrics"),
            initial_node_counts=record.get("node_counts"),
            initial_logs=record.get("logs"),
            initial_elapsed_seconds=record.get("elapsed_seconds", 0.0),
            store=store,
        )

    def start(self) -> "GraphJob":
        """Start the background thread and mark the job as running."""
        with self._lock:
            if self._status != "created":
                raise RuntimeError("This job has already been started.")
            self._status = "running"
            self._started_at = time.perf_counter()
            self._finished_at = None
            self._error = None
            self._traceback = None
            if self.resume_from_checkpoint:
                self._logs.append("[resume] continuing from the latest SQLite checkpoint")
        self._persist()
        self._thread.start()
        return self

    def cancel(self) -> None:
        """Request cooperative cancellation after the current graph step returns."""
        self.cancel_event.set()
        with self._lock:
            if self._status == "running":
                self._status = "cancelling"
                self._logs.append("Cancellation requested; waiting for the active API call to return.")
        self._persist()

    @property
    def result(self) -> dict[str, Any] | None:
        """Return the final graph state when the job has completed successfully."""
        with self._lock:
            return self._result

    def _run(self) -> None:
        """Stream graph updates, persist progress, and capture terminal status."""
        stream = None
        final_state = None
        config = {
            "callbacks": [self.metrics],
            "configurable": {"thread_id": self.checkpoint_thread_id},
        }
        try:
            stream_input: dict[str, Any] | None = self.inputs
            if self.resume_from_checkpoint:
                # LangGraph resumes from stored checkpoint state when input is None.
                checkpoint = self.graph.get_state(config)
                if not checkpoint.values:
                    raise RuntimeError("No LangGraph checkpoint exists for this run.")
                if not checkpoint.next:
                    final_state = dict(checkpoint.values)
                    with self._lock:
                        self._result = final_state
                        self._current_state = final_state
                        self._status = "completed"
                        self._logs.append("[resume] checkpoint was already complete")
                    return
                stream_input = None

            stream = self.graph.stream(
                stream_input,
                config=config,
                stream_mode=["updates", "values"],
            )
            for stream_kind, payload in stream:
                if self.cancel_event.is_set():
                    with self._lock:
                        self._status = "cancelled"
                    self._persist()
                    return

                with self._lock:
                    if stream_kind == "values" and isinstance(payload, dict):
                        # Values events carry the latest full state snapshot.
                        self._current_state = payload
                        final_state = payload
                    elif stream_kind == "updates" and isinstance(payload, dict):
                        # Updates events identify which graph node just ran.
                        for node in payload:
                            if not str(node).startswith("__"):
                                self._node_counts[node] = self._node_counts.get(node, 0) + 1
                        self._logs.append(
                            f"[updates] {json.dumps(payload, default=str)[:1200]}"
                        )
                self._persist()

            if self.cancel_event.is_set():
                with self._lock:
                    self._status = "cancelled"
                self._persist()
                return
            if final_state is None:
                raise RuntimeError("The graph completed without returning a final state.")

            with self._lock:
                self._result = final_state
                self._current_state = final_state
                self._status = "completed"
                self._logs.append("[final] received final state")
            self._persist()
        except Exception as error:
            with self._lock:
                self._status = "failed"
                self._error = str(error)
                self._traceback = traceback.format_exc()
                self._logs.append(f"[error] {error}")
            self._persist()
        finally:
            if stream is not None and hasattr(stream, "close"):
                try:
                    stream.close()
                except Exception:
                    pass
            with self._lock:
                self._finished_at = time.perf_counter()
            self._persist()

    def _persist(self) -> None:
        """Persist the latest snapshot into the run registry table."""
        snapshot = self.snapshot()
        self.store.update_run(
            run_id=self.id,
            status=snapshot["status"],
            state=snapshot["current_state"],
            metrics=snapshot["metrics"],
            node_counts=snapshot["node_counts"],
            logs=snapshot["logs"],
            elapsed_seconds=snapshot["elapsed_seconds"],
            error=snapshot["error"],
        )

    def snapshot(self) -> dict[str, Any]:
        """Build a thread-safe view of job state for the UI and database."""
        with self._lock:
            now = self._finished_at or time.perf_counter()
            current_elapsed = now - self._started_at if self._started_at is not None else 0.0
            elapsed = self._elapsed_before + current_elapsed
            return {
                "id": self.id,
                "checkpoint_thread_id": self.checkpoint_thread_id,
                "phase": self.phase,
                "status": self._status,
                "elapsed_seconds": elapsed,
                "current_state": dict(self._current_state),
                "error": self._error,
                "traceback": self._traceback,
                "node_counts": dict(self._node_counts),
                "logs": list(self._logs),
                "metrics": self.metrics.snapshot(),
            }


__all__ = ["GraphJob", "TERMINAL_JOB_STATUSES"]
