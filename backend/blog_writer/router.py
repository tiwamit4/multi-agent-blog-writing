"""Research-routing node that decides whether a topic needs fresh evidence."""

from langchain_core.messages import HumanMessage, SystemMessage

from . import config
from .clients import llm
from .models import RouterDecision, State
from .prompt import ROUTER_SYSTEM_PROMPT


def router_node(state: State) -> dict:
    """Classify the topic and produce bounded search settings for research."""
    decider = llm.with_structured_output(
        RouterDecision, method="json_schema", strict=True
    )
    decision = decider.invoke(
        [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=f"Topic: {state['topic']}\nAs-of date: {state['as_of']}"),
        ]
    )

    if decision.mode == "open_book":
        recency_days = 7
    elif decision.mode == "hybrid":
        recency_days = 45
    else:
        recency_days = 3650

    queries = decision.queries[: config.ROUTER_QUERY_MAX]
    max_results = max(
        1,
        min(decision.max_results_per_query, config.MAX_RESULTS_PER_QUERY),
    )

    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "queries": queries,
        "max_results_per_query": max_results,
        "recency_days": recency_days,
    }


def route_next(state: State) -> str:
    """Choose the next graph node based on the router's normalized decision."""
    return "research" if state["needs_research"] else "orchestrator"
