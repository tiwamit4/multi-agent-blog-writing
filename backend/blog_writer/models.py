"""Pydantic schemas and LangGraph state definitions for the blog workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator, model_validator

from . import config


class Task(BaseModel):
    """One planned blog section that can be written by a worker node."""

    id: int = Field(..., gt=0)
    title: str
    goal: str = Field(..., description="One sentence describing what the reader should do/understand.")
    bullets: List[str] = Field(
        ...,
        min_length=config.TASK_MIN_BULLETS,
        max_length=config.TASK_MAX_BULLETS,
    )
    target_words: int = Field(
        ...,
        ge=config.TASK_MIN_TARGET_WORDS,
        le=config.TASK_MAX_TARGET_WORDS,
        description=(
            f"Target words ({config.TASK_MIN_TARGET_WORDS}-"
            f"{config.TASK_MAX_TARGET_WORDS})."
        ),
    )
    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False

    @field_validator("title", "goal")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """Reject empty section titles and goals before graph execution."""
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("bullets")
    @classmethod
    def validate_bullets(cls, values: List[str]) -> List[str]:
        """Normalize bullet text and reject blank bullet items."""
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("bullets must not contain empty items")
        return cleaned


class Plan(BaseModel):
    """Full outline reviewed by the user before section writing starts."""

    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task] = Field(
        ...,
        min_length=config.PLAN_MIN_TASKS,
        max_length=config.PLAN_MAX_TASKS,
    )

    @field_validator("blog_title", "audience", "tone")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """Reject empty outline metadata fields."""
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_unique_task_ids(self) -> "Plan":
        """Ensure section IDs can safely merge parallel worker outputs."""
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task IDs must be unique")
        return self


class EvidenceItem(BaseModel):
    """Grounded source record selected from Tavily search results."""

    title: str
    url: str
    published_at: Optional[str] = None
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    """Structured routing result produced by the router LLM."""

    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: List[str] = Field(default_factory=list)
    max_results_per_query: int = Field(
        config.DEFAULT_MAX_RESULTS_PER_QUERY,
        ge=1,
        le=config.MAX_RESULTS_PER_QUERY,
    )

    @model_validator(mode="after")
    def normalize_research_flag(self) -> "RouterDecision":
        """Keep the boolean flag consistent with the selected route mode."""
        self.needs_research = self.mode != "closed_book"
        return self


class EvidencePack(BaseModel):
    """Structured evidence selection returned by the research selector."""

    evidence: List[EvidenceItem] = Field(default_factory=list)


class ImageSpec(BaseModel):
    """One planned technical image and its placeholder metadata."""

    placeholder: str = Field(..., description="e.g. [[IMAGE_1]]")
    filename: str = Field(..., description="Save under output/images/, e.g. qkv_flow.png")
    alt: str
    caption: str
    prompt: str = Field(..., description="Prompt to send to the image model.")
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "medium"

    @field_validator("placeholder")
    @classmethod
    def validate_placeholder(cls, value: str) -> str:
        """Restrict placeholders to the three positions the renderer supports."""
        if value not in {"[[IMAGE_1]]", "[[IMAGE_2]]", "[[IMAGE_3]]"}:
            raise ValueError("placeholder must be [[IMAGE_1]], [[IMAGE_2]], or [[IMAGE_3]]")
        return value

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        """Prevent directory traversal and non-PNG image filenames."""
        value = value.strip()
        path = Path(value)
        if not value or path.name != value or path.suffix.lower() != ".png":
            raise ValueError("filename must be a plain .png filename")
        return value

    @field_validator("alt", "caption", "prompt")
    @classmethod
    def validate_image_text(cls, value: str) -> str:
        """Require useful alt text, captions, and generation prompts."""
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class GlobalImagePlan(BaseModel):
    """Article markdown plus optional image specifications."""

    md_with_placeholders: str
    images: List[ImageSpec] = Field(default_factory=list, max_length=3)


def merge_sections(
    existing: List[tuple[int, str]],
    updates: List[tuple[int, str]],
) -> List[tuple[int, str]]:
    """Merge parallel worker results while replacing regenerated sections by ID."""
    merged = dict(existing)
    merged.update(dict(updates))
    return sorted(merged.items(), key=lambda item: item[0])


class State(TypedDict):
    """Shared LangGraph state passed between blog-writing nodes."""

    topic: str
    blog_id: str
    mode: str
    needs_research: bool
    queries: List[str]
    max_results_per_query: int
    research_errors: List[str]
    evidence: List[EvidenceItem]
    plan: Optional[Plan]
    as_of: str
    recency_days: int
    sections: Annotated[List[tuple[int, str]], merge_sections]
    target_task_id: Optional[int]
    merged_md: str
    md_with_placeholders: str
    image_specs: List[dict]
    artifact_path: str
    final: str
