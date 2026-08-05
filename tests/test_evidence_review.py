from __future__ import annotations

import pandas as pd
import pytest

from ui.evidence_review import (
    reviewed_evidence_from_ui,
    state_with_approved_evidence,
)


def test_reviewed_evidence_keeps_adds_and_removes_sources() -> None:
    rows = pd.DataFrame(
        [
            {
                "keep": True,
                "title": "Kept source",
                "url": "https://example.com/kept",
                "published_at": "2026-08-05",
                "source": "",
                "snippet": "Useful context",
            },
            {
                "keep": False,
                "title": "Removed source",
                "url": "https://example.com/removed",
                "published_at": "",
                "source": "",
                "snippet": "",
            },
        ]
    )

    reviewed = reviewed_evidence_from_ui(rows)

    assert len(reviewed) == 1
    assert reviewed[0].title == "Kept source"
    assert reviewed[0].source == "example.com"


def test_kept_sources_require_title_and_url() -> None:
    rows = pd.DataFrame(
        [{"keep": True, "title": "", "url": "https://example.com/source"}]
    )

    with pytest.raises(ValueError, match="title and URL"):
        reviewed_evidence_from_ui(rows)


def test_approved_evidence_resets_downstream_state(sample_state) -> None:
    sample_state.update(
        {
            "mode": "closed_book",
            "needs_research": False,
            "merged_md": "# Existing",
            "final": "# Existing",
            "sections": [(1, "old")],
        }
    )
    approved = reviewed_evidence_from_ui(
        pd.DataFrame(
            [
                {
                    "keep": True,
                    "title": "Manual source",
                    "url": "https://example.com/manual",
                }
            ]
        )
    )

    updated = state_with_approved_evidence(sample_state, approved)

    assert updated["mode"] == "hybrid"
    assert updated["needs_research"] is True
    assert updated["evidence"] == approved
    assert updated["sections"] == []
    assert updated["final"] == ""

