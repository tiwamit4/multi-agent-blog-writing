"""Human-in-the-loop source review before outline generation."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from blog_writer.graph import planning_app
from blog_writer.models import EvidenceItem
from blog_writer.workflow import state_with_evidence as state_with_approved_evidence
from ui.job_monitor import start_job


def _clean_cell(value: Any) -> str:
    """Normalize Streamlit table values while treating blanks and NaN as empty."""
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def _source_from_url(url: str) -> str:
    """Infer a compact source label from a URL when the user leaves it blank."""
    hostname = urlparse(url).netloc.lower()
    return hostname.removeprefix("www.") or "manual"


def evidence_as_dict(item: Any) -> dict[str, Any]:
    """Normalize Pydantic or persisted evidence into a plain dictionary."""
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return dict(item)


def evidence_rows(evidence: list[Any]) -> pd.DataFrame:
    """Convert evidence items into editable rows with a review checkbox."""
    rows = []
    for item in evidence:
        item_dict = evidence_as_dict(item)
        rows.append(
            {
                "keep": True,
                "title": item_dict.get("title", ""),
                "url": item_dict.get("url", ""),
                "published_at": item_dict.get("published_at", ""),
                "source": item_dict.get("source", ""),
                "snippet": item_dict.get("snippet", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["keep", "title", "url", "published_at", "source", "snippet"],
    )


def evidence_signature(evidence: list[Any]) -> str:
    """Build a stable key suffix so newly researched sources refresh the editor."""
    payload = [evidence_as_dict(item) for item in evidence]
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()[:10]


def reviewed_evidence_from_ui(edited_rows: pd.DataFrame) -> list[EvidenceItem]:
    """Build validated evidence items from kept rows in the review table."""
    reviewed: list[EvidenceItem] = []
    for _, row in edited_rows.iterrows():
        keep_value = row.get("keep", True)
        keep = True if pd.isna(keep_value) else bool(keep_value)
        fields = {
            "title": _clean_cell(row.get("title")),
            "url": _clean_cell(row.get("url")),
            "published_at": _clean_cell(row.get("published_at")) or None,
            "source": _clean_cell(row.get("source")),
            "snippet": _clean_cell(row.get("snippet")) or None,
        }
        has_content = any(value for value in fields.values())
        if not keep or not has_content:
            continue
        if not fields["title"] or not fields["url"]:
            raise ValueError("Each kept source must include at least a title and URL.")
        fields["source"] = fields["source"] or _source_from_url(fields["url"])
        reviewed.append(EvidenceItem(**fields))
    return reviewed


def render_evidence_review(
    draft_state: dict[str, Any] | None,
    job_is_running: bool,
) -> None:
    """Render source approval controls before outline generation can begin."""
    if (
        not draft_state
        or draft_state.get("plan")
        or draft_state.get("sections")
        or draft_state.get("final")
        or job_is_running
    ):
        return

    evidence = draft_state.get("evidence") or []
    editor_key = (
        f"{draft_state.get('blog_id') or 'draft'}_{evidence_signature(evidence)}"
    )

    with st.container(border=True):
        st.header("Review research sources")
        mode = draft_state.get("mode") or "closed_book"
        st.caption(
            f"Router mode: {mode}. Keep useful sources, remove weak ones, or add "
            "manual sources before the outline is generated."
        )

        research_errors = draft_state.get("research_errors") or []
        if research_errors:
            with st.expander(
                f"Research warnings ({len(research_errors)})",
                expanded=True,
            ):
                for error in research_errors:
                    st.warning(error)

        queries = draft_state.get("queries") or []
        if queries:
            with st.expander("Search queries"):
                for query in queries:
                    st.write(f"- {query}")

        if not evidence and draft_state.get("needs_research"):
            st.warning("No sources were returned. Add sources manually or continue closed-book.")
        elif not evidence:
            st.info("The router selected closed-book mode. Add sources here if you want grounding.")

        edited_sources = st.data_editor(
            evidence_rows(evidence),
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            key=f"evidence_sources_{editor_key}",
            column_config={
                "keep": st.column_config.CheckboxColumn("Keep"),
                "title": st.column_config.TextColumn("Title", required=True),
                "url": st.column_config.LinkColumn("URL", required=True),
                "published_at": st.column_config.TextColumn("Published"),
                "source": st.column_config.TextColumn("Source"),
                "snippet": st.column_config.TextColumn("Snippet", width="large"),
            },
        )

        if st.button(
            "2. Approve sources and generate outline",
            type="primary",
            width="stretch",
        ):
            try:
                approved_evidence = reviewed_evidence_from_ui(edited_sources)
                planning_state = state_with_approved_evidence(
                    draft_state,
                    approved_evidence,
                )
            except (ValidationError, ValueError, TypeError) as error:
                st.error(f"Please fix the sources: {error}")
            else:
                st.session_state["draft_state"] = planning_state
                start_job(planning_app, planning_state, "planning")
                st.rerun()

