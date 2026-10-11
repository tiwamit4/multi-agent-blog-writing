"""Tavily search, evidence selection, and source-grounding logic."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage

from . import config
from .clients import llm
from .models import EvidenceItem, EvidencePack, State
from .prompt import RESEARCH_SYSTEM_PROMPT

TAVILY_TIMEOUT_SECONDS = config.TAVILY_TIMEOUT_SECONDS
TAVILY_MAX_ATTEMPTS = config.TAVILY_MAX_ATTEMPTS
RESEARCH_WORKERS = config.RESEARCH_WORKERS


def _tavily_search(
    query: str,
    max_results: int = config.DEFAULT_MAX_RESULTS_PER_QUERY,
    *,
    topic: str = "general",
    days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[dict]:
    """Run one Tavily query with retries and normalize result fields."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set.")

    from tavily import TavilyClient

    last_error: Exception | None = None
    for attempt in range(1, TAVILY_MAX_ATTEMPTS + 1):
        try:
            response = TavilyClient(api_key=api_key).search(
                query=query,
                max_results=max_results,
                search_depth="advanced",
                topic=topic,
                days=days if topic == "news" else None,
                start_date=start_date,
                end_date=end_date,
                include_raw_content=False,
                timeout=TAVILY_TIMEOUT_SECONDS,
            )
            results = response.get("results", []) if isinstance(response, dict) else []
            out: List[dict] = []
            for result in results:
                url = str(result.get("url") or "").strip()
                if not url:
                    continue
                out.append(
                    {
                        "title": str(result.get("title") or "").strip(),
                        "url": url,
                        "snippet": str(
                            result.get("content")
                            or result.get("snippet")
                            or result.get("raw_content")
                            or ""
                        ).strip()[: config.RAW_SEARCH_SNIPPET_CHARS],
                        "published_at": (
                            published.isoformat()
                            if (published := _iso_to_date(
                                result.get("published_date") or result.get("published_at")
                            )) else None
                        ),
                        "source": result.get("source")
                        or urlparse(url).netloc,
                        "score": float(result.get("score") or 0.0),
                    }
                )
            return out
        except Exception as error:
            last_error = error
            if attempt < TAVILY_MAX_ATTEMPTS:
                time.sleep(0.5 * (2 ** (attempt - 1)))

    raise RuntimeError(
        f"Tavily search failed for query {query!r} after "
        f"{TAVILY_MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def _iso_to_date(value: Optional[str]) -> Optional[date]:
    """Parse date-like strings while tolerating missing or malformed values."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        try:
            return parsedate_to_datetime(value).date()
        except (TypeError, ValueError, OverflowError):
            return None


def _ground_evidence(raw: List[dict], pack: EvidencePack) -> List[EvidenceItem]:
    """Accept only selected URLs and content that came from Tavily."""
    raw_by_url = {
        str(item.get("url") or "").strip(): item
        for item in raw
        if str(item.get("url") or "").strip()
    }
    grounded: dict[str, EvidenceItem] = {}
    for selected in pack.evidence:
        source_item = raw_by_url.get(selected.url)
        if source_item is None:
            continue
        grounded[selected.url] = EvidenceItem(
            title=str(source_item.get("title") or selected.title).strip(),
            url=selected.url,
            published_at=(
                published.isoformat()
                if (published := _iso_to_date(source_item.get("published_at")))
                else None
            ),
            snippet=str(source_item.get("snippet") or "").strip(),
            source=str(source_item.get("source") or selected.source or "").strip()
            or None,
        )
    return list(grounded.values())


def _fallback_evidence_from_raw(
    raw: List[dict], limit: int = config.FALLBACK_EVIDENCE_LIMIT
) -> EvidencePack:
    """Use grounded Tavily results when structured evidence extraction fails."""
    sorted_results = sorted(
        raw,
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )
    evidence = [
        EvidenceItem(
            title=str(item.get("title") or url).strip(),
            url=url,
            published_at=item.get("published_at"),
            source=item.get("source"),
        )
        for item in sorted_results[:limit]
        if (url := str(item.get("url") or "").strip())
    ]
    return EvidencePack(evidence=evidence)


def _filter_open_book_evidence(
    evidence: List[EvidenceItem], as_of_value: str, recency_days: int
) -> List[EvidenceItem]:
    """Keep only dated evidence inside the recency window for newsy topics."""
    as_of = date.fromisoformat(as_of_value)
    cutoff = as_of - timedelta(days=recency_days)
    return [
        item
        for item in evidence
        if (published := _iso_to_date(item.published_at))
        and cutoff <= published <= as_of
    ]


def research_node(state: State) -> dict:
    """Collect search results and return evidence safe for downstream citation."""
    queries = (state.get("queries") or [])[: config.RESEARCH_MAX_QUERIES]
    max_results = max(
        1,
        min(
            int(state.get("max_results_per_query", config.DEFAULT_MAX_RESULTS_PER_QUERY)),
            config.MAX_RESULTS_PER_QUERY,
        ),
    )
    raw: List[dict] = []
    errors: List[str] = []
    search_options = {}
    if state.get("mode") == "open_book":
        as_of = date.fromisoformat(state["as_of"])
        search_options = {
            "topic": "news",
            "start_date": (as_of - timedelta(days=int(state["recency_days"]))).isoformat(),
            "end_date": as_of.isoformat(),
        }

    with ThreadPoolExecutor(max_workers=min(RESEARCH_WORKERS, max(1, len(queries)))) as pool:
        futures = {
            pool.submit(_tavily_search, query, max_results, **search_options): query
            for query in queries
        }
        for future in as_completed(futures):
            query = futures[future]
            try:
                raw.extend(future.result())
            except Exception as error:
                errors.append(f"{query}: {error}")

    if not raw:
        if not errors:
            errors.append("Web search returned no results for the requested queries.")
        return {"evidence": [], "research_errors": errors}

    # The selector sees trimmed raw results; final snippets still come from Tavily.
    prompt_results = [
        {
            **item,
            "snippet": str(item.get("snippet") or "")[
                : config.RESEARCH_PROMPT_SNIPPET_CHARS
            ],
        }
        for item in raw[: config.RESEARCH_PROMPT_RESULT_LIMIT]
    ]
    extractor = llm.with_structured_output(
        EvidencePack, method="json_schema", strict=True
    )
    try:
        pack = extractor.invoke(
            [
                SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"As-of date: {state['as_of']}\n"
                        f"Recency days: {state['recency_days']}\n\n"
                        "<UNTRUSTED_SEARCH_RESULTS>\n"
                        f"{json.dumps(prompt_results, ensure_ascii=False)}\n"
                        "</UNTRUSTED_SEARCH_RESULTS>"
                    )
                ),
            ]
        )
    except Exception as error:
        errors.append(
            "Evidence selector failed; using grounded raw search results. "
            f"Error: {str(error)[:300]}"
        )
        pack = _fallback_evidence_from_raw(raw)

    evidence = _ground_evidence(raw, pack)
    if state.get("mode") == "open_book":
        evidence = _filter_open_book_evidence(
            evidence,
            state["as_of"],
            int(state["recency_days"]),
        )
        if not evidence:
            errors.append(
                "Search returned sources, but none of the selected sources had a "
                "verified publication date inside the requested date window."
            )

    return {"evidence": evidence, "research_errors": errors}
