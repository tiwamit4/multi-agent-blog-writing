from __future__ import annotations

from streamlit.testing.v1 import AppTest


def discovery_output() -> dict:
    return {
        "seed_topic": "AI agents",
        "as_of": "2026-06-22",
        "lookback_days": 30,
        "max_ideas": 8,
        "discovery_queries": ["AI agents latest developments 2026"],
        "raw_results": [],
        "discovery_errors": [],
        "idea_candidates": [],
        "ranked_ideas": [
            {
                "rank": 1,
                "title": "Operating reliable agent workflows",
                "angle": "Show concrete recovery and observability patterns",
                "why_trending": "Recent framework releases emphasize durable execution",
                "content_gap": "Most articles stop at toy agent demos",
                "gap_score": 5,
                "gap_strength": 100.0,
                "score": 88.0,
                "freshness_score": 90.0,
                "evidence_score": 82.0,
                "evidence_count": 2,
                "freshest_evidence_date": "2026-06-21",
                "keywords": ["agents", "durability"],
                "evidence_urls": [
                    "https://one.example/source",
                    "https://two.example/source",
                ],
                "evidence": [
                    {
                        "title": "Source one",
                        "url": "https://one.example/source",
                        "published_at": "2026-06-21",
                        "source": "one.example",
                    },
                    {
                        "title": "Source two",
                        "url": "https://two.example/source",
                        "published_at": "2026-06-20",
                        "source": "two.example",
                    },
                ],
            }
        ],
    }


def test_discovery_dashboard_and_blog_handoff() -> None:
    app = AppTest.from_file("bwa_frontend.py", default_timeout=30).run()
    app.radio[0].set_value("Topic Discovery").run()
    app.session_state["discovery_out"] = discovery_output()
    app.run()

    assert not app.exception, app.exception
    assert app.title[0].value == "Technical Topic Discovery"
    assert "Operating reliable agent workflows" in [
        heading.value for heading in app.markdown if "Operating reliable" in heading.value
    ][0]

    write_button = next(
        button for button in app.button if button.label == "Write this topic"
    )
    write_button.click().run()

    assert not app.exception, app.exception
    assert app.title[0].value == "Blog Writing Agent"
    topic_input = next(area for area in app.text_area if area.label == "Topic")
    assert "Operating reliable agent workflows" in topic_input.value
