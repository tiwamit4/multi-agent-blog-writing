"""Shared state creation and approval transitions for Streamlit and the API."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from . import config
from .models import EvidenceItem, Plan


def initial_state(topic: str, as_of: date, recency_days: int = 7) -> dict[str, Any]:
    """Create a fresh graph state for a new blog run."""
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
        "recency_days": recency_days,
        "sections": [],
        "target_task_id": None,
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "artifact_path": "",
        "final": "",
    }


def reset_article_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Clear generated article fields while preserving sections and task selection."""
    updated = dict(state)
    updated.update({
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "artifact_path": "",
        "final": "",
    })
    return updated


def reset_downstream_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Clear derived article fields and any previous regeneration selection."""
    updated = reset_article_fields(state)
    updated["target_task_id"] = None
    return updated


def state_with_evidence(
    state: dict[str, Any],
    evidence: list[EvidenceItem],
) -> dict[str, Any]:
    """Attach human-approved evidence and clear later workflow results."""
    updated = reset_downstream_fields(state)
    mode = state.get("mode") or "closed_book"
    if evidence and mode == "closed_book":
        mode = "hybrid"
    if not evidence:
        mode = "closed_book"
    updated.update(
        {
            "mode": mode,
            "needs_research": bool(evidence),
            "evidence": evidence,
            "plan": None,
            "sections": [],
        }
    )
    return updated


def state_with_plan(state: dict[str, Any], plan: Plan) -> dict[str, Any]:
    """Attach a human-approved outline and clear generated sections."""
    updated = reset_downstream_fields(state)
    updated.update({"plan": plan, "sections": []})
    return updated


def state_with_sections(
    state: dict[str, Any],
    sections: list[tuple[int, str]],
) -> dict[str, Any]:
    """Attach human-approved section markdown in deterministic task order."""
    updated = reset_downstream_fields(state)
    updated["sections"] = sorted(sections, key=lambda item: item[0])
    return updated
