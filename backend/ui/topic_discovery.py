"""Streamlit UI for discovering and handing off technical topic ideas."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from blog_writer.graph import discovery_app
from ui.job_monitor import start_job
from ui.persistence_panel import render_persistent_runs


def initial_discovery_state(
    seed_topic: str,
    as_of: date,
    lookback_days: int,
    max_ideas: int,
) -> dict[str, Any]:
    """Create the initial state for a topic-discovery graph run."""
    return {
        "seed_topic": seed_topic.strip(),
        "as_of": as_of.isoformat(),
        "lookback_days": lookback_days,
        "max_ideas": max_ideas,
        "discovery_queries": [],
        "raw_results": [],
        "discovery_errors": [],
        "idea_candidates": [],
        "ranked_ideas": [],
    }


def render_discovery_sidebar(job_is_running: bool) -> None:
    """Render discovery controls and start a discovery job on submit."""
    with st.sidebar:
        st.header("Discover technical topics")
        seed_topic = st.text_input(
            "Technology or domain",
            placeholder="e.g. AI agents, vLLM, platform engineering",
            key="discovery_seed_topic",
        )
        as_of = st.date_input(
            "Discovery date",
            value=date.today(),
            key="discovery_as_of",
        )
        lookback_days = st.select_slider(
            "Freshness window",
            options=[7, 14, 30, 60, 90],
            value=30,
            format_func=lambda value: f"{value} days",
            key="discovery_lookback",
        )
        max_ideas = st.slider(
            "Ideas to return",
            min_value=3,
            max_value=12,
            value=8,
            key="discovery_max_ideas",
        )
        discover = st.button(
            "Discover and rank topics",
            type="primary",
            disabled=job_is_running,
            width="stretch",
        )
        render_persistent_runs(job_is_running)

    if discover:
        if not seed_topic.strip():
            st.warning("Enter a technology or domain to explore.")
            return
        st.session_state["discovery_out"] = None
        st.session_state["workflow_metrics"] = None
        start_job(
            discovery_app,
            initial_discovery_state(
                seed_topic,
                as_of,
                int(lookback_days),
                int(max_ideas),
            ),
            "discovery",
        )
        st.rerun()


def _idea_rows(ideas: list[dict]) -> pd.DataFrame:
    """Convert ranked idea dictionaries into dashboard table rows."""
    return pd.DataFrame(
        [
            {
                "Rank": idea.get("rank"),
                "Topic": idea.get("title"),
                "Overall": idea.get("score"),
                "Freshness": idea.get("freshness_score"),
                "Evidence": idea.get("evidence_score"),
                "Gap": idea.get("gap_strength"),
                "Sources": idea.get("evidence_count"),
                "Freshest source": idea.get("freshest_evidence_date") or "Unknown",
            }
            for idea in ideas
        ]
    )


def render_discovery_results(out: dict[str, Any] | None) -> None:
    """Render discovery scores, evidence links, and blog handoff controls."""
    st.caption(
        "The dashboard searches current technical coverage, identifies under-served "
        "angles, grounds every idea in source URLs, and ranks ideas deterministically."
    )
    if not out:
        st.info(
            "Choose a technology or domain in the sidebar to discover article opportunities."
        )
        return

    errors = out.get("discovery_errors") or []
    if errors:
        with st.expander(f"Search warnings ({len(errors)})"):
            for error in errors:
                st.warning(error)

    ideas = out.get("ranked_ideas") or []
    if not ideas:
        st.info("This run does not have ranked topic ideas yet.")
        return

    summary = st.columns(4)
    summary[0].metric("Ranked ideas", len(ideas))
    summary[1].metric(
        "Top score",
        f"{max(float(idea.get('score', 0)) for idea in ideas):.1f}/100",
    )
    summary[2].metric(
        "Evidence links",
        sum(int(idea.get("evidence_count", 0)) for idea in ideas),
    )
    summary[3].metric(
        "Strongest gap",
        f"{max(float(idea.get('gap_strength', 0)) for idea in ideas):.0f}/100",
    )

    minimum_score = st.slider(
        "Minimum overall score",
        min_value=0,
        max_value=100,
        value=0,
        key=f"discovery_score_filter_{out.get('as_of', 'run')}",
    )
    visible_ideas = [
        idea for idea in ideas if float(idea.get("score", 0)) >= minimum_score
    ]
    rows = _idea_rows(visible_ideas)
    st.dataframe(rows, hide_index=True, width="stretch")

    if not rows.empty:
        chart_data = rows.rename(
            columns={
                "Topic": "topic",
                "Freshness": "freshness",
                "Evidence": "evidence",
                "Overall": "score",
                "Gap": "gap",
            }
        )
        st.scatter_chart(
            chart_data,
            x="freshness",
            y="evidence",
            size="score",
            color="gap",
        )
        st.caption(
            "Bubble position compares freshness and evidence strength; size represents "
            "overall score and color represents the estimated content-gap strength."
        )

    st.subheader("Ranked opportunities")
    for idea in visible_ideas:
        with st.container(border=True):
            st.markdown(f"### #{idea['rank']} — {idea['title']}")
            score_columns = st.columns(4)
            score_columns[0].metric("Overall", f"{idea['score']:.1f}")
            score_columns[1].metric("Freshness", f"{idea['freshness_score']:.1f}")
            score_columns[2].metric("Evidence", f"{idea['evidence_score']:.1f}")
            score_columns[3].metric("Gap", f"{idea['gap_strength']:.1f}")
            st.write("**Recommended angle:**", idea["angle"])
            st.write("**Why it is timely:**", idea["why_trending"])
            st.write("**Content gap:**", idea["content_gap"])
            if idea.get("keywords"):
                st.caption("Keywords: " + ", ".join(idea["keywords"]))

            with st.expander(f"Evidence ({idea['evidence_count']} sources)"):
                for source in idea.get("evidence", []):
                    published = source.get("published_at") or "date unknown"
                    label = source.get("title") or source.get("source") or source["url"]
                    st.markdown(f"- [{label}]({source['url']}) — {published}")

            if st.button(
                "Write this topic",
                key=f"write_discovered_topic_{idea['rank']}",
                width="stretch",
            ):
                # Handoff stores a rich prompt in the blog-writer topic box.
                st.session_state["blog_topic"] = (
                    f"{idea['title']}\n\n"
                    f"Recommended angle: {idea['angle']}\n"
                    f"Content gap to address: {idea['content_gap']}"
                )
                st.session_state["next_workspace"] = "Blog Writer"
                st.session_state["last_notice"] = (
                    "The selected discovery idea is ready in the blog topic field."
                )
                st.rerun()

    with st.expander("Discovery queries"):
        for query in out.get("discovery_queries") or []:
            st.markdown(f"- {query}")

    st.caption(
        "Overall score = 45% freshness + 40% evidence strength + 15% content-gap strength."
    )
