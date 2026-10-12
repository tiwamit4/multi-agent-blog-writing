"""FastAPI entrypoint for serving the blog workflow to a React frontend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

from blog_writer.app_logging import configure_terminal_logging
from blog_writer.graph import (
    discovery_app,
    evidence_app,
    finalizing_app,
    planning_app,
    section_draft_regeneration_app,
    writing_app,
)
from blog_writer.jobs import GraphJob, TERMINAL_JOB_STATUSES
from blog_writer.persistence import run_store
from blog_writer.paths import IMAGES_ROOT, RUNS_ROOT
from blog_writer.blog_deletion import (
    BlogDeleteConflictError,
    BlogNotFoundError,
    delete_saved_blog as delete_blog_record,
)
from blog_writer.workflow import (
    initial_state,
    state_with_evidence as _state_with_evidence,
    state_with_plan as _state_with_plan,
    state_with_sections as _state_with_sections,
)

from .schemas import (
    EvidenceApprovalRequest,
    OutlineApprovalRequest,
    RegenerateSectionRequest,
    RunSnapshotResponse,
    RunStartResponse,
    SectionsApprovalRequest,
    StartEvidenceRequest,
    StartDiscoveryRequest,
)


app = FastAPI(title="Multi-Agent Blog Writer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

configure_terminal_logging()
ACTIVE_JOBS: dict[str, GraphJob] = {}


def _jsonable(value: Any) -> Any:
    """Convert Pydantic models, tuples, and Paths into API-safe JSON values."""
    return jsonable_encoder(value, custom_encoder={Path: str})


def _snapshot_response(snapshot: dict[str, Any]) -> RunSnapshotResponse:
    """Normalize live job snapshots and persisted records into one response shape."""
    return RunSnapshotResponse(
        run_id=snapshot.get("id") or snapshot.get("run_id"),
        phase=snapshot["phase"],
        status=snapshot["status"],
        elapsed_seconds=float(snapshot.get("elapsed_seconds", 0.0)),
        current_state=_jsonable(snapshot.get("current_state") or snapshot.get("state") or {}),
        error=snapshot.get("error"),
        node_counts=_jsonable(snapshot.get("node_counts", {})),
        logs=list(snapshot.get("logs", [])),
        metrics=_jsonable(snapshot.get("metrics", {})),
    )


def _get_snapshot(run_id: str) -> RunSnapshotResponse:
    """Return a live job snapshot, falling back to the durable run registry."""
    job = ACTIVE_JOBS.get(run_id)
    if job is not None:
        return _snapshot_response(job.snapshot())

    record = run_store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return _snapshot_response(record)


def _state_for_next_phase(run_id: str) -> dict[str, Any]:
    """Load raw typed terminal state before starting the next approved phase."""
    job = ACTIVE_JOBS.get(run_id)
    if job is not None:
        snapshot = job.snapshot()
        status = snapshot["status"]
        state = snapshot["current_state"]
    else:
        record = run_store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        status = record["status"]
        state = record["state"]

    if status not in TERMINAL_JOB_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Run is still active. Wait for it to finish before approval.",
        )
    if status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Run must be completed before approval; current status is {status}.",
        )
    return dict(state)


def _start_phase(graph: Any, state: dict[str, Any], phase: str) -> RunStartResponse:
    """Start a graph phase and remember it for live polling."""
    job = GraphJob(graph, state, phase).start()
    ACTIVE_JOBS[job.id] = job
    snapshot = job.snapshot()
    return RunStartResponse(
        run_id=snapshot["id"],
        phase=snapshot["phase"],
        status=snapshot["status"],
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Return a basic liveness response for the React dev server."""
    return {"status": "ok"}


@app.post("/runs/evidence", response_model=RunStartResponse)
def start_evidence_run(payload: StartEvidenceRequest) -> RunStartResponse:
    """Start routing plus optional research for a new blog topic."""
    return _start_phase(
        evidence_app,
        initial_state(payload.topic, payload.as_of, payload.recency_days),
        "evidence",
    )


@app.post("/runs/discovery", response_model=RunStartResponse)
def start_discovery_run(payload: StartDiscoveryRequest) -> RunStartResponse:
    """Discover and rank technical topics using the shared agent graph."""
    state = {
        "seed_topic": payload.seed_topic,
        "as_of": payload.as_of.isoformat(),
        "lookback_days": payload.lookback_days,
        "max_ideas": payload.max_ideas,
        "discovery_queries": [],
        "raw_results": [],
        "discovery_errors": [],
        "idea_candidates": [],
        "ranked_ideas": [],
    }
    return _start_phase(discovery_app, state, "discovery")


@app.get("/runs", response_model=list[RunSnapshotResponse])
def list_runs(limit: int = 20) -> list[RunSnapshotResponse]:
    """List recent persisted runs for the React sidebar."""
    safe_limit = max(1, min(limit, 100))
    return [_snapshot_response(record) for record in run_store.list_runs(safe_limit)]


@app.get("/runs/{run_id}", response_model=RunSnapshotResponse)
def get_run(run_id: str) -> RunSnapshotResponse:
    """Fetch the latest state for a live or persisted run."""
    return _get_snapshot(run_id)


@app.delete("/runs/{run_id}/blog")
def delete_saved_blog(run_id: str) -> dict[str, int]:
    """Delete an inactive blog and its generated files across all phases."""
    try:
        deleted_runs = delete_blog_record(
            run_id, store=run_store, active_jobs=ACTIVE_JOBS,
            runs_root=RUNS_ROOT, images_root=IMAGES_ROOT,
        )
    except BlogNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BlogDeleteConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"deleted_runs": deleted_runs}


@app.post("/runs/{run_id}/cancel", response_model=RunSnapshotResponse)
def cancel_run(run_id: str) -> RunSnapshotResponse:
    """Cancel an active background graph job."""
    job = ACTIVE_JOBS.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Active run not found.")
    job.cancel()
    return _snapshot_response(job.snapshot())


@app.post("/runs/{run_id}/approve-sources", response_model=RunStartResponse)
def approve_sources(
    run_id: str,
    payload: EvidenceApprovalRequest,
) -> RunStartResponse:
    """Start outline generation from human-approved sources."""
    state = _state_for_next_phase(run_id)
    return _start_phase(
        planning_app,
        _state_with_evidence(state, payload.evidence),
        "planning",
    )


@app.post("/runs/{run_id}/approve-outline", response_model=RunStartResponse)
def approve_outline(
    run_id: str,
    payload: OutlineApprovalRequest,
) -> RunStartResponse:
    """Start section draft generation from a human-approved outline."""
    state = _state_for_next_phase(run_id)
    return _start_phase(writing_app, _state_with_plan(state, payload.plan), "writing")


@app.post("/runs/{run_id}/regenerate-section", response_model=RunStartResponse)
def regenerate_section(
    run_id: str,
    payload: RegenerateSectionRequest,
) -> RunStartResponse:
    """Regenerate one section draft while preserving reviewed edits."""
    state = _state_for_next_phase(run_id)
    if payload.sections is not None:
        state = _state_with_sections(
            state,
            [(section.task_id, section.markdown) for section in payload.sections],
        )
    state["target_task_id"] = payload.target_task_id
    return _start_phase(
        section_draft_regeneration_app,
        state,
        "section_regeneration",
    )


@app.post("/runs/{run_id}/approve-sections", response_model=RunStartResponse)
def approve_sections(
    run_id: str,
    payload: SectionsApprovalRequest,
) -> RunStartResponse:
    """Start final article assembly from human-approved section drafts."""
    state = _state_for_next_phase(run_id)
    sections = [(section.task_id, section.markdown) for section in payload.sections]
    return _start_phase(finalizing_app, _state_with_sections(state, sections), "finalizing")
