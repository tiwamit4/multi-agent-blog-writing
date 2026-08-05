"""Streamlit entrypoint that composes the blog writer and discovery UI."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import streamlit as st

from blog_writer import config
from blog_writer.app_logging import configure_terminal_logging
from blog_writer.graph import evidence_app
from blog_writer.jobs import TERMINAL_JOB_STATUSES
from ui.job_monitor import render_job_monitor, start_job
from ui.metrics_panel import render_workflow_metrics
from ui.evidence_review import render_evidence_review
from ui.outline_editor import render_outline_editor
from ui.results import render_results
from ui.section_review import render_section_review
from ui.sidebar import render_sidebar
from ui.topic_discovery import render_discovery_results, render_discovery_sidebar


def initial_state(topic: str, as_of: date) -> dict[str, Any]:
    """Create the default LangGraph state for a new blog-planning run."""
    return {
        "topic": topic.strip(),
        "blog_id": uuid4().hex[:12],
        "mode": "",
        "needs_research": False,
        "queries": [],
        "max_results_per_query": config.DEFAULT_MAX_RESULTS_PER_QUERY,
        "research_errors": [],
        "evidence": [],
        "plan": None,
        "as_of": as_of.isoformat(),
        "recency_days": 7,
        "sections": [],
        "target_task_id": None,
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "artifact_path": "",
        "final": "",
    }


def initialize_session_state() -> None:
    """Initialize Streamlit session keys used across reruns and fragments."""
    defaults = {
        "active_job": None,
        "draft_state": None,
        "handled_job_id": None,
        "last_error": None,
        "last_notice": None,
        "last_out": None,
        "last_run_logs": [],
        "workflow_metrics": None,
        "workspace": "Blog Writer",
        "next_workspace": None,
        "blog_topic": "",
        "discovery_out": None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def main() -> None:
    """Render the selected workspace and dispatch new background jobs."""
    configure_terminal_logging()
    st.set_page_config(page_title="LangGraph Blog Writer", layout="wide")
    initialize_session_state()

    # `next_workspace` lets callbacks switch tabs on the following rerun.
    requested_workspace = st.session_state.get("next_workspace")
    if requested_workspace:
        st.session_state["workspace"] = requested_workspace
        st.session_state["next_workspace"] = None
    workspace = st.sidebar.radio(
        "Workspace",
        ["Blog Writer", "Topic Discovery"],
        key="workspace",
    )

    active_job = st.session_state.get("active_job")
    # The UI disables new starts while a background graph is still active.
    job_is_running = bool(
        active_job and active_job.snapshot()["status"] not in TERMINAL_JOB_STATUSES
    )

    if workspace == "Topic Discovery":
        st.title("Technical Topic Discovery")
        render_discovery_sidebar(job_is_running)
        render_job_monitor()
        if st.session_state.get("last_error"):
            st.error(st.session_state["last_error"])
        if st.session_state.get("last_notice"):
            st.success(st.session_state["last_notice"])
        render_workflow_metrics()
        render_discovery_results(st.session_state.get("discovery_out"))
        return

    st.title("Blog Writing Agent")
    topic, as_of, outline_button = render_sidebar(job_is_running)
    if outline_button:
        if not topic.strip():
            st.warning("Please enter a topic.")
        else:
            st.session_state["draft_state"] = None
            st.session_state["last_out"] = None
            st.session_state["workflow_metrics"] = None
            start_job(evidence_app, initial_state(topic, as_of), "evidence")
            st.rerun()

    render_job_monitor()

    if st.session_state.get("last_error"):
        st.error(st.session_state["last_error"])
    if st.session_state.get("last_notice"):
        st.success(st.session_state["last_notice"])

    render_evidence_review(st.session_state.get("draft_state"), job_is_running)
    render_outline_editor(st.session_state.get("draft_state"), job_is_running)
    render_section_review(st.session_state.get("draft_state"), job_is_running)
    render_workflow_metrics()
    render_results(st.session_state.get("last_out"), job_is_running)


if __name__ == "__main__":
    main()
