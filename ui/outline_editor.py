"""Editable outline UI and conversion back into validated Plan objects."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from blog_writer import config
from blog_writer.graph import writing_app
from blog_writer.models import Plan, Task


def plan_as_dict(plan: Any) -> dict[str, Any]:
    """Normalize Pydantic or persisted plan values into a plain dictionary."""
    if hasattr(plan, "model_dump"):
        return plan.model_dump()
    if isinstance(plan, dict):
        return plan
    return json.loads(json.dumps(plan, default=str))


def task_rows(plan: Any) -> pd.DataFrame:
    """Convert plan tasks into rows accepted by Streamlit's data editor."""
    rows = []
    for task in plan_as_dict(plan).get("tasks", []):
        rows.append(
            {
                "id": task.get("id"),
                "title": task.get("title", ""),
                "goal": task.get("goal", ""),
                "bullets": "\n".join(task.get("bullets") or []),
                "target_words": task.get("target_words", config.DEFAULT_TARGET_WORDS),
                "tags": ", ".join(task.get("tags") or []),
                "research": bool(task.get("requires_research")),
                "citations": bool(task.get("requires_citations")),
                "code": bool(task.get("requires_code")),
            }
        )
    return pd.DataFrame(rows)


def edited_plan_from_ui(
    blog_title: str,
    audience: str,
    tone: str,
    blog_kind: str,
    constraints_text: str,
    edited_tasks: pd.DataFrame,
) -> Plan:
    """Build and validate a Plan from the user's edited table values."""
    tasks = []
    for _, row in edited_tasks.iterrows():
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        bullets = [
            line.strip().lstrip("- ").strip()
            for line in str(row.get("bullets") or "").splitlines()
            if line.strip().lstrip("- ").strip()
        ]
        tags = [
            tag.strip()
            for tag in str(row.get("tags") or "").split(",")
            if tag.strip()
        ]
        tasks.append(
            Task(
                id=int(row["id"]),
                title=title,
                goal=str(row.get("goal") or "").strip(),
                bullets=bullets,
                target_words=int(
                    row.get("target_words") or config.DEFAULT_TARGET_WORDS
                ),
                tags=tags,
                requires_research=bool(row.get("research", False)),
                requires_citations=bool(row.get("citations", False)),
                requires_code=bool(row.get("code", False)),
            )
        )

    task_ids = [task.id for task in tasks]
    if not tasks:
        raise ValueError("The outline must contain at least one section.")
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Every outline section must have a unique ID.")

    return Plan(
        blog_title=blog_title.strip(),
        audience=audience.strip(),
        tone=tone.strip(),
        blog_kind=blog_kind,
        constraints=[
            line.strip() for line in constraints_text.splitlines() if line.strip()
        ],
        tasks=tasks,
    )


def render_outline_editor(draft_state: dict[str, Any] | None, job_is_running: bool) -> None:
    """Render the outline editor and start writing after user approval."""
    if (
        not draft_state
        or not draft_state.get("plan")
        or draft_state.get("sections")
        or draft_state.get("final")
        or job_is_running
    ):
        return

    plan_dict = plan_as_dict(draft_state["plan"])
    editor_key = str(draft_state.get("blog_id") or "draft")
    with st.container(border=True):
        st.header("Review and edit the outline")
        title_column, kind_column = st.columns([3, 1])
        edited_title = title_column.text_input(
            "Blog title",
            value=plan_dict.get("blog_title", ""),
            key=f"outline_title_{editor_key}",
        )
        kinds = ["explainer", "tutorial", "news_roundup", "comparison", "system_design"]
        current_kind = plan_dict.get("blog_kind", "explainer")
        edited_kind = kind_column.selectbox(
            "Blog kind",
            kinds,
            index=kinds.index(current_kind) if current_kind in kinds else 0,
            key=f"outline_kind_{editor_key}",
        )
        audience_column, tone_column = st.columns(2)
        edited_audience = audience_column.text_input(
            "Audience",
            value=plan_dict.get("audience", ""),
            key=f"outline_audience_{editor_key}",
        )
        edited_tone = tone_column.text_input(
            "Tone",
            value=plan_dict.get("tone", ""),
            key=f"outline_tone_{editor_key}",
        )
        edited_constraints = st.text_area(
            "Constraints (one per line)",
            value="\n".join(plan_dict.get("constraints") or []),
            key=f"outline_constraints_{editor_key}",
        )
        st.caption("Edit bullets as one item per line. Rows can be added or removed.")
        edited_tasks = st.data_editor(
            task_rows(draft_state["plan"]),
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            key=f"outline_tasks_{editor_key}",
            column_config={
                "id": st.column_config.NumberColumn("ID", min_value=1, step=1, required=True),
                "title": st.column_config.TextColumn("Section title", required=True),
                "goal": st.column_config.TextColumn("Goal", required=True, width="large"),
                "bullets": st.column_config.TextColumn("Bullets", required=True, width="large"),
                "target_words": st.column_config.NumberColumn(
                    "Words",
                    min_value=config.TASK_MIN_TARGET_WORDS,
                    max_value=config.TASK_MAX_TARGET_WORDS,
                    step=10,
                ),
                "tags": st.column_config.TextColumn("Tags"),
                "research": st.column_config.CheckboxColumn("Research"),
                "citations": st.column_config.CheckboxColumn("Citations"),
                "code": st.column_config.CheckboxColumn("Code"),
            },
        )

        if st.button("3. Write section drafts", type="primary", width="stretch"):
            try:
                edited_plan = edited_plan_from_ui(
                    edited_title,
                    edited_audience,
                    edited_tone,
                    edited_kind,
                    edited_constraints,
                    edited_tasks,
                )
            except (ValidationError, ValueError, TypeError) as error:
                st.error(f"Please fix the outline: {error}")
            else:
                # Reset downstream fields so section writing starts from the edit.
                writing_state = dict(draft_state)
                writing_state.update(
                    {
                        "plan": edited_plan,
                        "sections": [],
                        "target_task_id": None,
                        "merged_md": "",
                        "md_with_placeholders": "",
                        "image_specs": [],
                        "artifact_path": "",
                        "final": "",
                    }
                )
                st.session_state["draft_state"] = writing_state
                # Local import avoids a module cycle during Streamlit startup.
                from ui.job_monitor import start_job

                start_job(writing_app, writing_state, "writing")
                st.rerun()
