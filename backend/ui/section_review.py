"""Human-in-the-loop review controls for generated section drafts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import streamlit as st

from blog_writer.graph import finalizing_app, section_draft_regeneration_app
from blog_writer.workflow import reset_article_fields as reset_downstream_article_fields
from ui.job_monitor import start_job
from ui.outline_editor import plan_as_dict


def section_map_from_state(state: dict[str, Any]) -> dict[int, str]:
    """Convert state sections into a lookup keyed by outline task ID."""
    sections: dict[int, str] = {}
    for task_id, markdown in state.get("sections") or []:
        sections[int(task_id)] = str(markdown or "")
    return sections


def section_signature(sections: dict[int, str]) -> str:
    """Build a short stable key suffix so regenerated drafts refresh the editor."""
    serialized = json.dumps(sections, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()[:10]


def reviewed_sections(
    tasks: list[dict[str, Any]],
    edited_sections: dict[int, str],
) -> list[tuple[int, str]]:
    """Return edited section markdown in outline order."""
    return [
        (int(task["id"]), edited_sections.get(int(task["id"]), "").strip())
        for task in tasks
    ]


def render_section_review(
    draft_state: dict[str, Any] | None,
    job_is_running: bool,
) -> None:
    """Render editable section drafts and require approval before finalizing."""
    if (
        not draft_state
        or not draft_state.get("plan")
        or not draft_state.get("sections")
        or draft_state.get("final")
        or job_is_running
    ):
        return

    plan_dict = plan_as_dict(draft_state["plan"])
    tasks = plan_dict.get("tasks") or []
    saved_sections = section_map_from_state(draft_state)
    signature = section_signature(saved_sections)
    editor_key = f"{draft_state.get('blog_id') or 'draft'}_{signature}"
    edited_sections: dict[int, str] = {}
    regenerate_task_id: int | None = None

    with st.container(border=True):
        st.header("Review generated sections")
        st.caption(
            "Edit any section, regenerate only the section that needs work, then approve "
            "the drafts to build the final article."
        )

        for task in tasks:
            task_id = int(task["id"])
            task_title = str(task.get("title") or f"Section {task_id}")
            with st.expander(f"{task_id}. {task_title}", expanded=True):
                edited_sections[task_id] = st.text_area(
                    "Section markdown",
                    value=saved_sections.get(task_id, ""),
                    height=320,
                    key=f"section_md_{editor_key}_{task_id}",
                )
                if st.button(
                    "Regenerate this section",
                    key=f"regenerate_section_{editor_key}_{task_id}",
                    width="stretch",
                ):
                    regenerate_task_id = task_id

        if regenerate_task_id is not None:
            regeneration_state = reset_downstream_article_fields(draft_state)
            regeneration_state.update(
                {
                    "sections": reviewed_sections(tasks, edited_sections),
                    "target_task_id": regenerate_task_id,
                }
            )
            start_job(
                section_draft_regeneration_app,
                regeneration_state,
                "section_regeneration",
            )
            st.rerun()

        if st.button(
            "4. Approve sections and build final article",
            type="primary",
            width="stretch",
        ):
            approved_sections = reviewed_sections(tasks, edited_sections)
            empty_sections = [
                str(task.get("title") or task["id"])
                for task_id, markdown in approved_sections
                if not markdown
                for task in tasks
                if int(task["id"]) == task_id
            ]
            if empty_sections:
                st.error(
                    "Please add content or regenerate these empty sections: "
                    + ", ".join(empty_sections)
                )
            else:
                finalizing_state = reset_downstream_article_fields(draft_state)
                finalizing_state.update(
                    {
                        "sections": approved_sections,
                        "target_task_id": None,
                    }
                )
                start_job(finalizing_app, finalizing_state, "finalizing")
                st.rerun()
