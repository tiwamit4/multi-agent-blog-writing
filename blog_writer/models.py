from __future__ import annotations

from pathlib import Path
from typing import Annotated, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator, model_validator


class Task(BaseModel):
    id: int = Field(..., gt=0)
    title: str
    goal: str = Field(..., description="One sentence describing what the reader should do/understand.")
    bullets: List[str] = Field(..., min_length=3, max_length=6)
    target_words: int = Field(..., ge=120, le=550, description="Target words (120–550).")
    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False

    @field_validator("title", "goal")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("bullets")
    @classmethod
    def validate_bullets(cls, values: List[str]) -> List[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("bullets must not contain empty items")
        return cleaned


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task] = Field(..., min_length=5, max_length=9)

    @field_validator("blog_title", "audience", "tone")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_unique_task_ids(self) -> "Plan":
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task IDs must be unique")
        return self


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: List[str] = Field(default_factory=list)
    max_results_per_query: int = Field(5, ge=1, le=10)

    @model_validator(mode="after")
    def normalize_research_flag(self) -> "RouterDecision":
        self.needs_research = self.mode != "closed_book"
        return self


class EvidencePack(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)


class ImageSpec(BaseModel):
    placeholder: str = Field(..., description="e.g. [[IMAGE_1]]")
    filename: str = Field(..., description="Save under images/, e.g. qkv_flow.png")
    alt: str
    caption: str
    prompt: str = Field(..., description="Prompt to send to the image model.")
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "medium"

    @field_validator("placeholder")
    @classmethod
    def validate_placeholder(cls, value: str) -> str:
        if value not in {"[[IMAGE_1]]", "[[IMAGE_2]]", "[[IMAGE_3]]"}:
            raise ValueError("placeholder must be [[IMAGE_1]], [[IMAGE_2]], or [[IMAGE_3]]")
        return value

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        value = value.strip()
        path = Path(value)
        if not value or path.name != value or path.suffix.lower() != ".png":
            raise ValueError("filename must be a plain .png filename")
        return value

    @field_validator("alt", "caption", "prompt")
    @classmethod
    def validate_image_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class GlobalImagePlan(BaseModel):
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
