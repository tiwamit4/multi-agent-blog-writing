from __future__ import annotations

import os

import pytest

os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-key")

from blog_writer.models import Plan, Task


@pytest.fixture
def sample_plan() -> Plan:
    return Plan(
        blog_title="Reliable Agents",
        audience="Python developers",
        tone="Clear and practical",
        blog_kind="tutorial",
        constraints=["Use concrete examples"],
        tasks=[
            Task(
                id=index,
                title=f"Section {index}",
                goal=f"Explain concept {index}",
                bullets=["Motivation", "Implementation", "Verification"],
                target_words=200,
                tags=[f"topic-{index}"],
                requires_research=index == 2,
                requires_citations=index == 2,
            )
            for index in range(1, 6)
        ],
    )


@pytest.fixture
def sample_state(sample_plan: Plan) -> dict:
    return {
        "topic": "Reliable AI agents",
        "blog_id": "test-blog-123",
        "mode": "hybrid",
        "needs_research": True,
        "queries": ["reliable AI agents"],
        "max_results_per_query": 5,
        "research_errors": [],
        "evidence": [],
        "plan": sample_plan,
        "as_of": "2026-06-22",
        "recency_days": 45,
        "sections": [],
        "target_task_id": None,
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "artifact_path": "",
        "final": "",
    }
