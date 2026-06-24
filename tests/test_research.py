from __future__ import annotations

from blog_writer.models import EvidenceItem, EvidencePack
from blog_writer import research


def test_ground_evidence_rejects_unknown_urls_and_preserves_source_content() -> None:
    raw = [
        {
            "title": "Original title",
            "url": "https://example.com/allowed",
            "snippet": "Grounded source excerpt",
            "published_at": "2026-06-20",
            "source": "example.com",
        }
    ]
    pack = EvidencePack(
        evidence=[
            EvidenceItem(
                title="Changed title",
                url="https://example.com/allowed",
                published_at="2099-01-01",
                snippet="Invented excerpt",
            ),
            EvidenceItem(
                title="Unknown",
                url="https://attacker.invalid/invented",
            ),
        ]
    )

    grounded = research._ground_evidence(raw, pack)

    assert [item.url for item in grounded] == ["https://example.com/allowed"]
    assert grounded[0].title == "Original title"
    assert grounded[0].published_at == "2026-06-20"
    assert grounded[0].snippet == "Grounded source excerpt"


def test_open_book_filter_excludes_old_unknown_and_future_dates() -> None:
    evidence = [
        EvidenceItem(title="Current", url="https://example.com/current", published_at="2026-06-20"),
        EvidenceItem(title="Old", url="https://example.com/old", published_at="2026-05-01"),
        EvidenceItem(title="Future", url="https://example.com/future", published_at="2026-06-23"),
        EvidenceItem(title="Unknown", url="https://example.com/unknown"),
    ]

    filtered = research._filter_open_book_evidence(evidence, "2026-06-22", 7)

    assert [item.title for item in filtered] == ["Current"]


def test_research_keeps_partial_results_and_reports_failures(monkeypatch) -> None:
    def fake_search(query: str, max_results: int) -> list[dict]:
        if query == "broken query":
            raise RuntimeError("temporary search outage")
        return [
            {
                "title": "Useful source",
                "url": "https://example.com/useful",
                "snippet": "Useful grounded content",
                "published_at": "2026-06-20",
                "source": "example.com",
            }
        ]

    class FakeExtractor:
        def invoke(self, messages):
            return EvidencePack(
                evidence=[
                    EvidenceItem(
                        title="Useful source",
                        url="https://example.com/useful",
                    ),
                    EvidenceItem(
                        title="Invented source",
                        url="https://invented.invalid/source",
                    ),
                ]
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeExtractor()

    monkeypatch.setattr(research, "_tavily_search", fake_search)
    monkeypatch.setattr(research, "llm", FakeLLM())
    state = {
        "queries": ["working query", "broken query"],
        "max_results_per_query": 5,
        "as_of": "2026-06-22",
        "recency_days": 7,
        "mode": "open_book",
    }

    result = research.research_node(state)

    assert [item.url for item in result["evidence"]] == ["https://example.com/useful"]
    assert len(result["research_errors"]) == 1
    assert "broken query" in result["research_errors"][0]
