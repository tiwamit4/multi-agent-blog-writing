"""Sidebar composition for blog creation and persisted-run controls."""

from __future__ import annotations

from datetime import date

import streamlit as st

from ui.persistence_panel import render_past_blogs, render_persistent_runs


def render_sidebar(job_is_running: bool) -> tuple[str, date, bool]:
    """Render the blog-writer sidebar and return the user's current inputs."""
    with st.sidebar:
        st.header("Create a blog")
        topic = st.text_area("Topic", height=120, key="blog_topic")
        as_of = st.date_input("As-of date", value=date.today())
        outline_button = st.button(
            "1. Generate outline",
            type="primary",
            disabled=job_is_running,
            width="stretch",
        )
        render_past_blogs(job_is_running)
        render_persistent_runs(job_is_running)

    return topic, as_of, outline_button
