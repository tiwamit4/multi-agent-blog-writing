from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from blog_writer.graph import (
    build_discovery_graph,
    build_evidence_graph,
    build_finalizing_graph,
    build_planning_graph,
    build_section_draft_regeneration_graph,
    build_section_regeneration_graph,
    build_writing_graph,
)
from blog_writer.router import route_next


def test_route_next_uses_normalized_research_state() -> None:
    assert route_next({"needs_research": True}) == "research"
    assert route_next({"needs_research": False}) == "orchestrator"


def test_all_phase_graphs_compile_with_an_in_memory_checkpointer() -> None:
    checkpointer = InMemorySaver()
    assert build_discovery_graph(checkpointer)
    assert build_evidence_graph(checkpointer)
    assert build_finalizing_graph(checkpointer)
    assert build_planning_graph(checkpointer)
    assert build_section_draft_regeneration_graph(checkpointer)
    assert build_writing_graph(checkpointer)
    assert build_section_regeneration_graph(checkpointer)
