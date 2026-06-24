from __future__ import annotations

import pytest
from pydantic import ValidationError

from blog_writer import config
from blog_writer.models import Plan, RouterDecision, Task


def make_task(task_id: int = 1, **overrides) -> Task:
    values = {
        "id": task_id,
        "title": f"Task {task_id}",
        "goal": "Explain the behavior",
        "bullets": ["First", "Second", "Third"],
        "target_words": 200,
    }
    values.update(overrides)
    return Task(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 0),
        ("title", "  "),
        ("target_words", config.TASK_MIN_TARGET_WORDS - 1),
        ("target_words", config.TASK_MAX_TARGET_WORDS + 1),
    ],
)
def test_task_constraints(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        make_task(**{field: value})


def test_plan_requires_configured_task_count_and_unique_ids() -> None:
    with pytest.raises(ValidationError):
        Plan(
            blog_title="Title",
            audience="Developers",
            tone="Clear",
            tasks=[make_task(index) for index in range(1, config.PLAN_MIN_TASKS)],
        )

    with pytest.raises(ValidationError):
        Plan(
            blog_title="Title",
            audience="Developers",
            tone="Clear",
            tasks=[
                make_task(index)
                for index in range(1, config.PLAN_MAX_TASKS + 2)
            ],
        )

    with pytest.raises(ValidationError):
        Plan(
            blog_title="Title",
            audience="Developers",
            tone="Clear",
            tasks=[make_task(index) for index in [1, 2, 3, 4, 4]],
        )


def test_router_decision_normalizes_research_flag() -> None:
    open_book = RouterDecision(
        needs_research=False,
        mode="open_book",
        reason="Current topic",
    )
    closed_book = RouterDecision(
        needs_research=True,
        mode="closed_book",
        reason="Evergreen topic",
    )
    assert open_book.needs_research is True
    assert closed_book.needs_research is False
