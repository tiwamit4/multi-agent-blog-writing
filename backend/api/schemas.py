"""Request and response schemas for the React/FastAPI interface."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from blog_writer.models import EvidenceItem, Plan


class StartEvidenceRequest(BaseModel):
    """User input for the first evidence-gathering phase."""

    topic: str = Field(..., min_length=1)
    as_of: date = Field(default_factory=date.today)
    recency_days: int = Field(default=7, ge=1, le=365)


class StartDiscoveryRequest(BaseModel):
    """Inputs for the existing topic-discovery workflow."""

    seed_topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    as_of: date = Field(default_factory=date.today)
    lookback_days: int = Field(default=30, ge=1, le=90)
    max_ideas: int = Field(default=8, ge=3, le=12)


class RunStartResponse(BaseModel):
    """Minimal response returned whenever a new graph phase starts."""

    run_id: str
    phase: str
    status: str


class SectionDraft(BaseModel):
    """One human-reviewed section draft for approval or regeneration."""

    task_id: int = Field(..., gt=0)
    markdown: str = Field(..., min_length=1)


class EvidenceApprovalRequest(BaseModel):
    """Human-approved evidence list used to generate an outline."""

    evidence: list[EvidenceItem] = Field(default_factory=list)


class OutlineApprovalRequest(BaseModel):
    """Human-approved outline used to generate section drafts."""

    plan: Plan


class SectionsApprovalRequest(BaseModel):
    """Human-approved section drafts used to build the final article."""

    sections: list[SectionDraft]


class RegenerateSectionRequest(BaseModel):
    """Request to rewrite one section while preserving current edits."""

    target_task_id: int = Field(..., gt=0)
    sections: list[SectionDraft] | None = None


class RunSnapshotResponse(BaseModel):
    """Serialized view of a live or persisted graph run."""

    run_id: str
    phase: str
    status: str
    elapsed_seconds: float = 0.0
    current_state: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    node_counts: dict[str, int] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

