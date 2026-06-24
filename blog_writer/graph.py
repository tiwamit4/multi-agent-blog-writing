from langgraph.graph import END, START, StateGraph

from .discovery import (
    DiscoveryState,
    gap_analyst_node,
    ranker_node,
    trend_scout_node,
)
from .images import decide_images, generate_and_place_images
from .models import State
from .persistence import checkpointer
from .research import research_node
from .router import route_next, router_node
from .writing import (
    fanout,
    merge_content,
    orchestrator_node,
    regenerate_worker_node,
    worker_node,
)


def build_reducer_subgraph():
    graph = StateGraph(State)
    graph.add_node("merge_content", merge_content)
    graph.add_node("decide_images", decide_images)
    graph.add_node("generate_and_place_images", generate_and_place_images)
    graph.add_edge(START, "merge_content")
    graph.add_edge("merge_content", "decide_images")
    graph.add_edge("decide_images", "generate_and_place_images")
    graph.add_edge("generate_and_place_images", END)
    return graph.compile()


def build_graph(graph_checkpointer=checkpointer):
    graph = StateGraph(State)
    graph.add_node("router", router_node)
    graph.add_node("research", research_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("worker", worker_node)
    graph.add_node("reducer", build_reducer_subgraph())

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_next,
        {"research": "research", "orchestrator": "orchestrator"},
    )
    graph.add_edge("research", "orchestrator")
    graph.add_conditional_edges("orchestrator", fanout, ["worker"])
    graph.add_edge("worker", "reducer")
    graph.add_edge("reducer", END)
    return graph.compile(checkpointer=graph_checkpointer)


def build_planning_graph(graph_checkpointer=checkpointer):
    graph = StateGraph(State)
    graph.add_node("router", router_node)
    graph.add_node("research", research_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_next,
        {"research": "research", "orchestrator": "orchestrator"},
    )
    graph.add_edge("research", "orchestrator")
    graph.add_edge("orchestrator", END)
    return graph.compile(checkpointer=graph_checkpointer)


def build_writing_graph(graph_checkpointer=checkpointer):
    graph = StateGraph(State)
    graph.add_node("approved_outline", lambda state: {})
    graph.add_node("worker", worker_node)
    graph.add_node("reducer", build_reducer_subgraph())
    graph.add_edge(START, "approved_outline")
    graph.add_conditional_edges("approved_outline", fanout, ["worker"])
    graph.add_edge("worker", "reducer")
    graph.add_edge("reducer", END)
    return graph.compile(checkpointer=graph_checkpointer)


def build_section_regeneration_graph(graph_checkpointer=checkpointer):
    graph = StateGraph(State)
    graph.add_node("regenerate_worker", regenerate_worker_node)
    graph.add_node("reducer", build_reducer_subgraph())
    graph.add_edge(START, "regenerate_worker")
    graph.add_edge("regenerate_worker", "reducer")
    graph.add_edge("reducer", END)
    return graph.compile(checkpointer=graph_checkpointer)


def build_discovery_graph(graph_checkpointer=checkpointer):
    graph = StateGraph(DiscoveryState)
    graph.add_node("trend_scout", trend_scout_node)
    graph.add_node("gap_analyst", gap_analyst_node)
    graph.add_node("ranker", ranker_node)
    graph.add_edge(START, "trend_scout")
    graph.add_edge("trend_scout", "gap_analyst")
    graph.add_edge("gap_analyst", "ranker")
    graph.add_edge("ranker", END)
    return graph.compile(checkpointer=graph_checkpointer)


app = build_graph()
planning_app = build_planning_graph()
writing_app = build_writing_graph()
section_regeneration_app = build_section_regeneration_graph()
discovery_app = build_discovery_graph()

__all__ = [
    "app",
    "discovery_app",
    "planning_app",
    "section_regeneration_app",
    "writing_app",
    "build_graph",
    "build_discovery_graph",
    "build_planning_graph",
    "build_reducer_subgraph",
    "build_section_regeneration_graph",
    "build_writing_graph",
]
