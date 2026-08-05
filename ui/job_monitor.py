"""Streamlit controls for starting, resuming, monitoring, and finishing jobs."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from blog_writer.graph import (
    discovery_app,
    evidence_app,
    finalizing_app,
    planning_app,
    section_draft_regeneration_app,
    section_regeneration_app,
    writing_app,
)
from blog_writer.jobs import GraphJob, TERMINAL_JOB_STATUSES
from ui.metrics_panel import (
    agent_progress_rows,
    job_progress_fraction,
    merge_metric_snapshots,
    render_metrics,
)


PHASE_GRAPHS = {
    "discovery": discovery_app,
    "evidence": evidence_app,
    "finalizing": finalizing_app,
    "planning": planning_app,
    "section_regeneration": section_draft_regeneration_app,
    "writing": writing_app,
    "regeneration": section_regeneration_app,
}


def start_job(graph: Any, state: dict[str, Any], phase: str) -> None:
    """Start a new background graph job if no other job is active."""
    current = st.session_state.get("active_job")
    if current and current.snapshot()["status"] not in TERMINAL_JOB_STATUSES:
        raise RuntimeError("Another generation job is already running.")
    st.session_state["handled_job_id"] = None
    st.session_state["active_job"] = GraphJob(graph, state, phase).start()
    st.session_state["last_error"] = None
    st.session_state["last_notice"] = None


def resume_job(record: dict[str, Any]) -> None:
    """Resume a persisted run or restart discovery when no checkpoint evidence exists."""
    current = st.session_state.get("active_job")
    if current and current.snapshot()["status"] not in TERMINAL_JOB_STATUSES:
        raise RuntimeError("Another generation job is already running.")
    graph = PHASE_GRAPHS.get(record["phase"])
    if graph is None:
        raise ValueError(f"Unknown persisted phase: {record['phase']}")
    st.session_state["handled_job_id"] = None
    restart_discovery = (
        record["phase"] == "discovery"
        and not record["state"].get("raw_results")
    )
    if restart_discovery:
        # Discovery cannot resume from a failed evidence-less scout, so restart cleanly.
        saved_state = record["state"]
        discovery_state = {
            "seed_topic": saved_state["seed_topic"],
            "as_of": saved_state["as_of"],
            "lookback_days": int(saved_state.get("lookback_days", 30)),
            "max_ideas": int(saved_state.get("max_ideas", 8)),
            "discovery_queries": [],
            "raw_results": [],
            "discovery_errors": [],
            "idea_candidates": [],
            "ranked_ideas": [],
        }
        st.session_state["active_job"] = GraphJob(
            graph,
            discovery_state,
            "discovery",
        ).start()
        record_state = discovery_state
    else:
        st.session_state["active_job"] = GraphJob.from_record(graph, record).start()
        record_state = record["state"]
    if record["phase"] == "discovery":
        st.session_state["discovery_out"] = record_state
        st.session_state["next_workspace"] = "Topic Discovery"
    else:
        st.session_state["draft_state"] = record["state"]
        st.session_state["last_out"] = record["state"]
    st.session_state["workflow_metrics"] = None
    st.session_state["last_error"] = None
    if restart_discovery:
        st.session_state["last_notice"] = (
            "The failed discovery run had no evidence, so it was restarted from "
            "the trend-scout step."
        )
    else:
        st.session_state["last_notice"] = (
            f"Resuming {record['phase']} from SQLite checkpoint."
        )


def persisted_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    """Adapt a database run record to the live job snapshot shape."""
    return {
        "id": record["run_id"],
        "phase": record["phase"],
        "status": record["status"],
        "elapsed_seconds": record.get("elapsed_seconds", 0.0),
        "current_state": record["state"],
        "error": record.get("error"),
        "node_counts": record.get("node_counts", {}),
        "logs": record.get("logs", []),
        "metrics": record.get("metrics", {}),
    }


def handle_finished_job(job: GraphJob, snapshot: dict) -> bool:
    """Move a terminal job into Streamlit session state exactly once."""
    if st.session_state.get("handled_job_id") == snapshot["id"]:
        if st.session_state.get("active_job") is job:
            st.session_state["active_job"] = None
        return False

    st.session_state["handled_job_id"] = snapshot["id"]
    st.session_state["last_run_logs"] = snapshot.get("logs", [])
    if snapshot["status"] == "completed":
        result = job.result
        if result is None:
            st.session_state["last_error"] = "The job completed without a result."
        else:
            if snapshot["phase"] == "discovery":
                st.session_state["discovery_out"] = result
                st.session_state["workflow_metrics"] = snapshot
                st.session_state["last_notice"] = (
                    "Topic discovery completed and ranked ideas are ready."
                )
            elif snapshot["phase"] == "evidence":
                st.session_state["draft_state"] = result
                st.session_state["last_out"] = result
                st.session_state["workflow_metrics"] = snapshot
                st.session_state["last_notice"] = (
                    "Sources are ready; review, add, or remove them before outlining."
                )
            elif snapshot["phase"] == "planning":
                st.session_state["draft_state"] = result
                st.session_state["last_out"] = result
                st.session_state["workflow_metrics"] = merge_metric_snapshots(
                    st.session_state.get("workflow_metrics"), snapshot
                )
                st.session_state["last_notice"] = (
                    "Outline ready; review and edit it before writing."
                )
            elif snapshot["phase"] == "writing":
                st.session_state["draft_state"] = result
                st.session_state["last_out"] = result
                st.session_state["workflow_metrics"] = merge_metric_snapshots(
                    st.session_state.get("workflow_metrics"), snapshot
                )
                st.session_state["last_notice"] = (
                    "Section drafts are ready; review, edit, or regenerate them."
                )
            elif snapshot["phase"] == "section_regeneration":
                st.session_state["draft_state"] = result
                st.session_state["last_out"] = result
                st.session_state["workflow_metrics"] = merge_metric_snapshots(
                    st.session_state.get("workflow_metrics"), snapshot
                )
                st.session_state["last_notice"] = (
                    "Section regenerated; review the updated draft before finalizing."
                )
            else:
                st.session_state["draft_state"] = result
                st.session_state["last_out"] = result
                st.session_state["workflow_metrics"] = merge_metric_snapshots(
                    st.session_state.get("workflow_metrics"), snapshot
                )
                action = (
                    "Section regenerated"
                    if snapshot["phase"] == "regeneration"
                    else "Blog generated"
                )
                st.session_state["last_notice"] = f"{action} successfully."
    elif snapshot["status"] == "cancelled":
        st.session_state["workflow_metrics"] = merge_metric_snapshots(
            st.session_state.get("workflow_metrics"), snapshot
        )
        st.session_state["last_notice"] = (
            "Generation cancelled. The active API call may have finished before "
            "cancellation took effect."
        )
    else:
        st.session_state["workflow_metrics"] = merge_metric_snapshots(
            st.session_state.get("workflow_metrics"), snapshot
        )
        st.session_state["last_error"] = snapshot.get("error") or "Generation failed."
    st.session_state["active_job"] = None
    return True


@st.fragment(run_every=0.75)
def render_job_monitor() -> None:
    """Render live job progress and process terminal states on rerun."""
    job = st.session_state.get("active_job")
    if not job:
        return

    snapshot = job.snapshot()
    status_label = snapshot["status"].replace("_", " ").title()
    with st.container(border=True):
        heading, action = st.columns([4, 1])
        heading.subheader(f"{snapshot['phase'].title()} - {status_label}")
        if snapshot["status"] in {"running", "cancelling"}:
            if action.button(
                "Cancel generation",
                key=f"cancel_{snapshot['id']}",
                disabled=snapshot["status"] == "cancelling",
                width="stretch",
            ):
                job.cancel()
                st.rerun(scope="fragment")
        st.progress(job_progress_fraction(snapshot))
        st.dataframe(
            pd.DataFrame(agent_progress_rows(snapshot)),
            hide_index=True,
            width="stretch",
        )
        render_metrics(snapshot, "Current operation")
        if snapshot["status"] == "cancelling":
            st.info(
                "Cancellation requested. It will take effect after the active API "
                "request returns."
            )

    if snapshot["status"] in TERMINAL_JOB_STATUSES:
        if handle_finished_job(job, snapshot):
            st.rerun(scope="app")

