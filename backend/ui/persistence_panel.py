"""Sidebar panels for loading saved markdown and persisted graph runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from blog_writer.persistence import DATABASE_PATH, run_store
from blog_writer.paths import PROJECT_DIR, RUNS_ROOT
from ui.job_monitor import persisted_snapshot, resume_job


RESUMABLE_RUN_STATUSES = {"created", "interrupted", "cancelled", "failed"}


def list_past_blogs() -> list[Path]:
    """Return saved markdown files from legacy root files and output runs."""
    legacy_files = [
        path
        for path in PROJECT_DIR.glob("*.md")
        if path.is_file() and path.name.lower() != "readme.md"
    ]
    run_files = list(RUNS_ROOT.glob("*/article.md")) if RUNS_ROOT.is_dir() else []
    files = legacy_files + [path for path in run_files if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def read_md_file(path: Path) -> str:
    """Read a markdown file for preview, replacing bad bytes if needed."""
    return path.read_text(encoding="utf-8", errors="replace")


def extract_title_from_md(markdown: str, fallback: str) -> str:
    """Extract the first H1 heading from markdown for display labels."""
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def render_past_blogs(job_is_running: bool) -> None:
    """Render controls for loading previously generated markdown files."""
    st.divider()
    st.subheader("Past blogs")
    past_files = list_past_blogs()
    if not past_files:
        st.caption("No saved blogs found (*.md in current folder).")
        return

    labels: list[str] = []
    files_by_label: dict[str, Path] = {}
    for path in past_files[:50]:
        try:
            markdown = read_md_file(path)
            title = extract_title_from_md(markdown, path.stem)
        except Exception:
            title = path.stem
        relative_path = path.relative_to(PROJECT_DIR)
        label = f"{title}  ·  {relative_path}"
        labels.append(label)
        files_by_label[label] = path
    selected_label = st.radio(
        "Select a blog to load",
        options=labels,
        index=0,
        label_visibility="collapsed",
    )
    if st.button("Load selected blog", disabled=job_is_running, width="stretch"):
        selected_path = files_by_label[selected_label]
        markdown = read_md_file(selected_path)
        st.session_state["last_out"] = {
            "plan": None,
            "evidence": [],
            "image_specs": [],
            "final": markdown,
        }
        st.session_state["draft_state"] = None
        st.session_state["workflow_metrics"] = None
        st.session_state["last_notice"] = (
            f"Loaded {selected_path.relative_to(PROJECT_DIR)}."
        )
        st.rerun()


def render_persistent_runs(job_is_running: bool) -> None:
    """Render controls for opening or resuming SQLite-backed graph runs."""
    st.divider()
    st.subheader("Persistent runs")
    persisted_runs = run_store.list_runs(limit=30)
    if not persisted_runs:
        st.caption("No checkpointed runs yet.")
        return

    run_labels: list[str] = []
    runs_by_label: dict[str, dict[str, Any]] = {}
    for record in persisted_runs:
        updated = str(record.get("updated_at", ""))[:16].replace("T", " ")
        topic_label = record.get("topic") or "Untitled"
        label = (
            f"{record['status']} · {record['phase']} · {topic_label} · "
            f"{updated} · {record['run_id'][:6]}"
        )
        run_labels.append(label)
        runs_by_label[label] = record
    selected_run_label = st.selectbox(
        "Saved run",
        options=run_labels,
        label_visibility="collapsed",
    )
    selected_run = runs_by_label[selected_run_label]
    run_action_columns = st.columns(2)
    if run_action_columns[0].button(
        "Open run",
        disabled=job_is_running,
        width="stretch",
    ):
        # Opening a run hydrates the UI without starting any graph execution.
        if selected_run["phase"] == "discovery":
            st.session_state["discovery_out"] = selected_run["state"]
            st.session_state["next_workspace"] = "Topic Discovery"
        else:
            st.session_state["draft_state"] = selected_run["state"]
            st.session_state["last_out"] = selected_run["state"]
        st.session_state["workflow_metrics"] = persisted_snapshot(selected_run)
        st.session_state["last_run_logs"] = selected_run.get("logs", [])
        st.session_state["last_error"] = selected_run.get("error")
        st.session_state["last_notice"] = (
            f"Opened {selected_run['phase']} run from SQLite."
        )
        st.rerun()
    if run_action_columns[1].button(
        "Resume run",
        disabled=(
            job_is_running or selected_run["status"] not in RESUMABLE_RUN_STATUSES
        ),
        width="stretch",
    ):
        resume_job(selected_run)
        st.rerun()
    st.caption(f"SQLite: `{DATABASE_PATH}`")
