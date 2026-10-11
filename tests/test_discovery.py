from __future__ import annotations

from blog_writer import discovery
from blog_writer.discovery import DiscoveryIdea


def test_discovery_expands_ambiguous_ai_ml_topic() -> None:
    queries = discovery.discovery_queries("AI ML", "2026-10-08")
    assert all("artificial intelligence and machine learning" in query for query in queries)
    assert "AI ML" not in " ".join(queries)


def result(url: str, published_at: str, title: str = "Source") -> dict:
    return {
        "title": title,
        "url": url,
        "snippet": "Technical evidence",
        "published_at": published_at,
        "source": url.split("/")[2],
    }


def idea(title: str, urls: list[str], gap_score: int = 4) -> DiscoveryIdea:
    return DiscoveryIdea(
        title=title,
        angle="A concrete implementation angle",
        why_trending="Recent releases and engineering discussion",
        content_gap="Existing articles omit operational tradeoffs",
        gap_score=gap_score,
        evidence_urls=urls,
        keywords=["agents", "operations"],
    )


def test_ground_ideas_rejects_unknown_urls_and_duplicate_titles() -> None:
    raw = [
        result("https://one.example/source", "2026-06-20"),
        result("https://two.example/source", "2026-06-19"),
    ]
    ideas = [
        idea(
            "Grounded idea",
            [
                "https://one.example/source",
                "https://two.example/source",
                "https://invented.invalid/source",
            ],
        ),
        idea(
            "Grounded idea",
            ["https://one.example/source", "https://two.example/source"],
        ),
        idea(
            "Insufficient evidence",
            ["https://one.example/source", "https://invented.invalid/source"],
        ),
    ]

    grounded = discovery._ground_ideas(ideas, raw, max_ideas=8)

    assert len(grounded) == 1
    assert grounded[0]["evidence_urls"] == [
        "https://one.example/source",
        "https://two.example/source",
    ]


def test_rank_ideas_prefers_fresh_diverse_evidence() -> None:
    raw = [
        result("https://one.example/fresh", "2026-06-21"),
        result("https://two.example/fresh", "2026-06-20"),
        result("https://one.example/old", "2026-01-01"),
        result("https://one.example/old-2", "2026-01-02"),
    ]
    candidates = [
        idea(
            "Fresh opportunity",
            ["https://one.example/fresh", "https://two.example/fresh"],
        ).model_dump(),
        idea(
            "Old opportunity",
            ["https://one.example/old", "https://one.example/old-2"],
            gap_score=5,
        ).model_dump(),
    ]

    ranked = discovery.rank_ideas(candidates, raw, "2026-06-22", 30)

    assert [item["title"] for item in ranked] == [
        "Fresh opportunity",
        "Old opportunity",
    ]
    assert ranked[0]["rank"] == 1
    assert ranked[0]["freshness_score"] > ranked[1]["freshness_score"]
    assert ranked[0]["evidence_score"] > ranked[1]["evidence_score"]


def test_trend_scout_keeps_partial_results(monkeypatch) -> None:
    def fake_search(
        query: str,
        max_results: int,
        *,
        topic: str = "general",
        days: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        if "limitations" in query:
            raise RuntimeError("temporary outage")
        return [
            result(
                f"https://source.example/{abs(hash(query))}",
                "2026-06-20",
                query,
            )
        ]

    monkeypatch.setattr(discovery, "_tavily_search", fake_search)
    state = {
        "seed_topic": "AI agents",
        "as_of": "2026-06-22",
        "lookback_days": 30,
    }

    output = discovery.trend_scout_node(state)

    assert len(output["discovery_queries"]) == 5
    assert len(output["raw_results"]) == 4
    assert len(output["discovery_errors"]) == 1
    assert all(item.get("discovery_query") for item in output["raw_results"])
