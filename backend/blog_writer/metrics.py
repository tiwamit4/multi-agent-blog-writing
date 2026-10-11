"""Token, latency, and estimated Groq cost accounting for graph runs."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler


GROQ_INPUT_COST_PER_MILLION = 0.80
GROQ_OUTPUT_COST_PER_MILLION = 4.00


def _token_usage(response: Any) -> dict[str, int]:
    """Extract token counts across provider-specific LangChain response shapes."""
    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") or llm_output.get("usage") or {}

    if not usage:
        for generation_group in getattr(response, "generations", []) or []:
            for generation in generation_group:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                if usage:
                    break
            if usage:
                break

    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
    total_tokens = usage.get("total_tokens", input_tokens + output_tokens) or 0
    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total_tokens),
    }


class UsageMetricsCallback(BaseCallbackHandler):
    """Collect thread-safe token and per-node LLM latency metrics."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        """Seed metrics from an optional persisted snapshot."""
        initial = initial or {}
        self._lock = threading.Lock()
        self._runs: dict[UUID, tuple[float, str]] = {}
        self._input_tokens = int(initial.get("input_tokens", 0))
        self._output_tokens = int(initial.get("output_tokens", 0))
        self._total_tokens = int(initial.get("total_tokens", 0))
        self._llm_calls = int(initial.get("llm_calls", 0))
        self._node_calls: dict[str, int] = defaultdict(int, initial.get("node_calls", {}))
        self._node_latency: dict[str, float] = defaultdict(
            float,
            initial.get("node_latency_seconds", {}),
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Track when an LLM call starts and which LangGraph node owns it."""
        node = str((metadata or {}).get("langgraph_node") or "llm")
        with self._lock:
            self._runs[run_id] = (time.perf_counter(), node)

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Accumulate token counts and latency when an LLM call finishes."""
        usage = _token_usage(response)
        with self._lock:
            started_at, node = self._runs.pop(run_id, (time.perf_counter(), "llm"))
            self._input_tokens += usage["input_tokens"]
            self._output_tokens += usage["output_tokens"]
            self._total_tokens += usage["total_tokens"]
            self._llm_calls += 1
            self._node_calls[node] += 1
            self._node_latency[node] += time.perf_counter() - started_at

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Forget failed calls so active-node reporting does not get stuck."""
        with self._lock:
            self._runs.pop(run_id, None)

    def snapshot(self) -> dict[str, Any]:
        """Return a thread-safe metrics summary for UI display and persistence."""
        with self._lock:
            estimated_cost = (
                self._input_tokens * GROQ_INPUT_COST_PER_MILLION
                + self._output_tokens * GROQ_OUTPUT_COST_PER_MILLION
            ) / 1_000_000
            return {
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "total_tokens": self._total_tokens,
                "llm_calls": self._llm_calls,
                "estimated_cost_usd": estimated_cost,
                "node_calls": dict(self._node_calls),
                "node_latency_seconds": dict(self._node_latency),
                "active_nodes": sorted({node for _, node in self._runs.values()}),
            }
