from datetime import date

from blog_writer.workflow import initial_state, reset_article_fields, state_with_plan, state_with_sections


def test_new_runs_have_independent_ids_and_mutable_defaults() -> None:
    first = initial_state("  AI agents  ", date(2026, 10, 8))
    second = initial_state("Another topic", date(2026, 10, 8), 30)
    first["queries"].append("query")

    assert first["topic"] == "AI agents"
    assert first["as_of"] == "2026-10-08"
    assert first["recency_days"] == 7
    assert second["recency_days"] == 30
    assert first["blog_id"] != second["blog_id"]
    assert second["queries"] == []


def test_outline_approval_clears_stale_artifacts_without_mutating_input(sample_state, sample_plan) -> None:
    sample_state.update(final="old article", sections=[(1, "old section")], target_task_id=1)
    approved = state_with_plan(sample_state, sample_plan)

    assert approved["plan"] is sample_plan
    assert approved["final"] == ""
    assert approved["sections"] == []
    assert approved["target_task_id"] is None
    assert sample_state["final"] == "old article"
    assert sample_state["sections"] == [(1, "old section")]


def test_article_reset_preserves_task_selection_but_section_approval_clears_it(sample_state) -> None:
    sample_state.update(final="old article", target_task_id=2)
    reset = reset_article_fields(sample_state)
    sections = [(2, "second"), (1, "first")]
    approved = state_with_sections(sample_state, sections)

    assert reset["target_task_id"] == 2
    assert reset["final"] == ""
    assert approved["target_task_id"] is None
    assert approved["sections"] == [(1, "first"), (2, "second")]
    assert sections == [(2, "second"), (1, "first")]
