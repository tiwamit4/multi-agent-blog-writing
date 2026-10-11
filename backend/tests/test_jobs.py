from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from blog_writer.jobs import GraphJob
from ui import job_monitor


@pytest.mark.parametrize("phase", [
    "discovery", "evidence", "planning", "writing", "section_regeneration",
    "regeneration", "finalizing",
])
def test_completed_phases_store_results_and_preserve_metric_totals(monkeypatch, phase) -> None:
    result = {"topic": "AI agents"}
    job = SimpleNamespace(result=result)
    session = {
        "active_job": job,
        "workflow_metrics": {"metrics": {"input_tokens": 100}},
    }
    monkeypatch.setattr(job_monitor.st, "session_state", session)
    snapshot = {
        "id": "completed-run", "phase": phase, "status": "completed",
        "metrics": {"input_tokens": 50},
    }

    assert job_monitor.handle_finished_job(job, snapshot) is True
    assert session["active_job"] is None
    if phase == "discovery":
        assert session["discovery_out"] is result
        assert "draft_state" not in session
    else:
        assert session["draft_state"] is result
        assert session["last_out"] is result
    expected_tokens = 50 if phase in {"discovery", "evidence"} else 150
    assert session["workflow_metrics"]["metrics"]["input_tokens"] == expected_tokens
    assert session["last_notice"]
    assert job_monitor.handle_finished_job(job, snapshot) is False
    assert session["workflow_metrics"]["metrics"]["input_tokens"] == expected_tokens


class MemoryRunStore:
    def __init__(self) -> None:
        self.records = []

    def create_run(self, **record) -> None:
        self.records.append({"operation": "create", **record})

    def update_run(self, **record) -> None:
        self.records.append({"operation": "update", **record})


class BlockingGraph:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def stream(self, inputs, *, config, stream_mode):
        self.started.set()
        self.release.wait(timeout=2)
        yield "values", inputs


def test_graph_job_cancellation_is_persisted(sample_state) -> None:
    graph = BlockingGraph()
    store = MemoryRunStore()
    job = GraphJob(graph, sample_state, "planning", store=store).start()
    assert graph.started.wait(timeout=1)

    job.cancel()
    graph.release.set()
    deadline = time.time() + 2
    while job.snapshot()["status"] not in {"cancelled", "failed"} and time.time() < deadline:
        time.sleep(0.01)

    assert job.snapshot()["status"] == "cancelled"
    assert store.records[-1]["status"] == "cancelled"


def test_resume_resets_handled_job_id(monkeypatch, sample_state) -> None:
    session = {
        "active_job": None,
        "handled_job_id": "same-run",
        "workflow_metrics": {},
    }

    class FakeJob:
        @classmethod
        def from_record(cls, graph, record):
            return cls()

        def start(self):
            return self

    monkeypatch.setattr(job_monitor.st, "session_state", session)
    monkeypatch.setattr(job_monitor, "GraphJob", FakeJob)
    record = {
        "run_id": "same-run",
        "phase": "planning",
        "state": sample_state,
    }

    job_monitor.resume_job(record)

    assert session["handled_job_id"] is None
    assert session["active_job"] is not None


def test_discovery_without_evidence_restarts_from_scout(monkeypatch) -> None:
    session = {
        "active_job": None,
        "handled_job_id": "failed-discovery",
        "workflow_metrics": {},
    }
    calls = {"new": 0, "resume": 0}

    class FakeJob:
        def __init__(self, graph, state, phase):
            calls["new"] += 1
            self.inputs = state

        @classmethod
        def from_record(cls, graph, record):
            calls["resume"] += 1
            return cls(graph, record["state"], record["phase"])

        def start(self):
            return self

    monkeypatch.setattr(job_monitor.st, "session_state", session)
    monkeypatch.setattr(job_monitor, "GraphJob", FakeJob)
    record = {
        "run_id": "failed-discovery",
        "phase": "discovery",
        "state": {
            "seed_topic": "LLM",
            "as_of": "2026-06-22",
            "lookback_days": 30,
            "max_ideas": 8,
            "discovery_queries": ["old query"],
            "raw_results": [],
            "discovery_errors": ["No module named tavily"],
            "idea_candidates": [],
            "ranked_ideas": [],
        },
    }

    job_monitor.resume_job(record)

    assert calls == {"new": 1, "resume": 0}
    assert session["active_job"].inputs["discovery_queries"] == []
    assert session["active_job"].inputs["discovery_errors"] == []
    assert "restarted" in session["last_notice"]


def test_already_handled_terminal_job_is_cleared_without_rehandling(monkeypatch) -> None:
    job = object()
    session = {
        "active_job": job,
        "handled_job_id": "run-1",
    }
    monkeypatch.setattr(job_monitor.st, "session_state", session)

    handled = job_monitor.handle_finished_job(
        job,
        {"id": "run-1", "status": "completed"},
    )

    assert handled is False
    assert session["active_job"] is None
