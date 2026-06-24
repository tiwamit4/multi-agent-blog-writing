from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.outline_editor import plan_as_dict


def merge_metric_snapshots(previous: dict | None, current: dict) -> dict:
    if not previous:
        return current

    combined = dict(current)
    combined["elapsed_seconds"] = previous.get("elapsed_seconds", 0.0) + current.get(
        "elapsed_seconds", 0.0
    )
    old_metrics = previous.get("metrics", {})
    new_metrics = current.get("metrics", {})
    metrics = dict(new_metrics)
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "llm_calls",
        "estimated_cost_usd",
    ):
        metrics[key] = old_metrics.get(key, 0) + new_metrics.get(key, 0)
    for key in ("node_calls", "node_latency_seconds"):
        values = dict(old_metrics.get(key, {}))
        for node, value in new_metrics.get(key, {}).items():
            values[node] = values.get(node, 0) + value
        metrics[key] = values
    metrics["active_nodes"] = new_metrics.get("active_nodes", [])
    combined["metrics"] = metrics
    combined["logs"] = previous.get("logs", []) + current.get("logs", [])
    return combined


def render_metrics(snapshot: dict, title: str = "Usage and performance") -> None:
    metrics = snapshot.get("metrics", {})
    st.subheader(title)
    columns = st.columns(5)
    columns[0].metric("Input tokens", f"{metrics.get('input_tokens', 0):,}")
    columns[1].metric("Output tokens", f"{metrics.get('output_tokens', 0):,}")
    columns[2].metric("LLM calls", f"{metrics.get('llm_calls', 0):,}")
    columns[3].metric("Elapsed", f"{snapshot.get('elapsed_seconds', 0.0):.1f}s")
    columns[4].metric(
        "Est. Groq cost", f"${metrics.get('estimated_cost_usd', 0.0):.5f}"
    )
    st.caption(
        "Text cost estimate uses $0.59/M input tokens and $0.79/M output tokens for "
        "llama-3.3-70b-versatile. Tavily and Gemini charges are not included."
    )

    node_latency = metrics.get("node_latency_seconds", {})
    if node_latency:
        with st.expander("Per-agent LLM latency"):
            rows = [
                {
                    "agent": node,
                    "calls": metrics.get("node_calls", {}).get(node, 0),
                    "LLM latency (seconds)": round(seconds, 2),
                }
                for node, seconds in sorted(node_latency.items())
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def agent_progress_rows(snapshot: dict[str, Any]) -> list[dict]:
    phase = snapshot["phase"]
    state = snapshot.get("current_state", {})
    counts = snapshot.get("node_counts", {})
    active = set(snapshot.get("metrics", {}).get("active_nodes", []))
    plan = state.get("plan")
    plan_dict = plan_as_dict(plan) if plan else {}
    total_sections = len(plan_dict.get("tasks", []))
    completed_sections = len(state.get("sections") or [])

    def status(node: str, completed: bool = False, skipped: bool = False) -> str:
        if skipped:
            return "Skipped"
        if node in active:
            return "Running"
        if completed or counts.get(node, 0):
            return "Complete"
        return "Pending"

    if phase == "discovery":
        discovery_agents = [
            ("trend_scout", "Trend scout"),
            ("gap_analyst", "Content-gap analyst"),
            ("ranker", "Freshness and evidence ranker"),
        ]
        return [
            {
                "agent": label,
                "status": status(node, bool(counts.get(node))),
                "progress": "1/1" if counts.get(node) else "0/1",
            }
            for node, label in discovery_agents
        ]

    if phase == "planning":
        router_done = bool(counts.get("router"))
        needs_research = bool(state.get("needs_research"))
        research_done = bool(counts.get("research"))
        return [
            {
                "agent": "Router",
                "status": status("router", router_done),
                "progress": "1/1" if router_done else "0/1",
            },
            {
                "agent": "Researcher",
                "status": status(
                    "research", research_done, router_done and not needs_research
                ),
                "progress": (
                    "1/1"
                    if research_done
                    else ("—" if router_done and not needs_research else "0/1")
                ),
            },
            {
                "agent": "Planner",
                "status": status("orchestrator", bool(counts.get("orchestrator"))),
                "progress": "1/1" if counts.get("orchestrator") else "0/1",
            },
        ]

    writer_node = "regenerate_worker" if phase == "regeneration" else "worker"
    writer_label = (
        "Section regenerator" if phase == "regeneration" else "Section writers"
    )
    writer_target = 1 if phase == "regeneration" else total_sections
    writer_done = counts.get(writer_node, 0)
    return [
        {
            "agent": writer_label,
            "status": status(
                writer_node, writer_done >= writer_target and writer_target > 0
            ),
            "progress": f"{min(writer_done, writer_target)}/{writer_target}",
        },
        {
            "agent": "Merger and image agents",
            "status": status("reducer", bool(counts.get("reducer"))),
            "progress": "1/1" if counts.get("reducer") else "0/1",
        },
        {
            "agent": "Sections available",
            "status": "Updated" if completed_sections else "Pending",
            "progress": f"{completed_sections}/{total_sections}",
        },
    ]


def job_progress_fraction(snapshot: dict) -> float:
    rows = agent_progress_rows(snapshot)
    finished = sum(
        row["status"] in {"Complete", "Skipped", "Updated"} for row in rows
    )
    return min(1.0, finished / max(1, len(rows)))


def render_workflow_metrics() -> None:
    workflow_metrics = st.session_state.get("workflow_metrics")
    if workflow_metrics and not st.session_state.get("active_job"):
        with st.container(border=True):
            render_metrics(workflow_metrics, "Workflow total")
