from __future__ import annotations

import pytest

from blog_writer.models import EvidenceItem
from blog_writer.writing import (
    _select_relevant_evidence,
    _strip_invalid_citation_urls,
    _validate_citation_urls,
    regenerate_worker_node,
    worker_payload,
)


def test_worker_payload_selects_relevant_evidence_and_keeps_snippet(sample_state) -> None:
    relevant = EvidenceItem(
        title="Section 2 implementation",
        url="https://example.com/relevant",
        snippet="Implementation details for topic-2",
    )
    unrelated = EvidenceItem(
        title="Cooking recipes",
        url="https://example.com/unrelated",
        snippet="Bread and soup",
    )
    sample_state["evidence"] = [unrelated, relevant]
    task = sample_state["plan"].tasks[1]

    payload = worker_payload(sample_state, task)

    assert payload["evidence"][0]["url"] == relevant.url
    assert payload["evidence"][0]["snippet"] == relevant.snippet
    assert _select_relevant_evidence([unrelated, relevant], task)[0] == relevant


def test_unapproved_citation_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="not present"):
        _validate_citation_urls(
            "Claim [Source](https://invented.invalid/source)",
            {"https://example.com/allowed"},
        )


def test_invalid_citation_urls_are_stripped_before_validation() -> None:
    cleaned = _strip_invalid_citation_urls(
        (
            "Good [Source](https://example.com/allowed). "
            "Bad [placeholder](https://example.com/fake). "
            "Empty [Not found](https://)."
        ),
        {"https://example.com/allowed"},
    )

    assert "[Source](https://example.com/allowed)" in cleaned
    assert "placeholder" in cleaned
    assert "https://example.com/fake" not in cleaned
    assert "[Not found](https://)" not in cleaned
    _validate_citation_urls(cleaned, {"https://example.com/allowed"})


def test_section_regeneration_updates_only_requested_task(monkeypatch, sample_state) -> None:
    sample_state["target_task_id"] = 3

    def fake_worker(payload: dict) -> dict:
        return {"sections": [(payload["task"]["id"], "## Regenerated")]}

    monkeypatch.setattr("blog_writer.writing.worker_node", fake_worker)

    result = regenerate_worker_node(sample_state)

    assert result == {"sections": [(3, "## Regenerated")]}
