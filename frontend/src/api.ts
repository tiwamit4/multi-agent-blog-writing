import type { EvidenceItem, Plan, RunSnapshot, SectionDraft } from "./types";

const API_BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function startEvidence(topic: string, asOf: string) {
  return request<{ run_id: string; phase: string; status: string }>("/runs/evidence", {
    method: "POST",
    body: JSON.stringify({ topic, as_of: asOf, recency_days: 7 })
  });
}

export function getRun(runId: string) {
  return request<RunSnapshot>(`/runs/${runId}`);
}

export function approveSources(runId: string, evidence: EvidenceItem[]) {
  return request<{ run_id: string; phase: string; status: string }>(
    `/runs/${runId}/approve-sources`,
    {
      method: "POST",
      body: JSON.stringify({ evidence })
    }
  );
}

export function approveOutline(runId: string, plan: Plan) {
  return request<{ run_id: string; phase: string; status: string }>(
    `/runs/${runId}/approve-outline`,
    {
      method: "POST",
      body: JSON.stringify({ plan })
    }
  );
}

export function regenerateSection(
  runId: string,
  targetTaskId: number,
  sections: SectionDraft[]
) {
  return request<{ run_id: string; phase: string; status: string }>(
    `/runs/${runId}/regenerate-section`,
    {
      method: "POST",
      body: JSON.stringify({ target_task_id: targetTaskId, sections })
    }
  );
}

export function approveSections(runId: string, sections: SectionDraft[]) {
  return request<{ run_id: string; phase: string; status: string }>(
    `/runs/${runId}/approve-sections`,
    {
      method: "POST",
      body: JSON.stringify({ sections })
    }
  );
}

export function listRuns() {
  return request<RunSnapshot[]>("/runs?limit=50");
}

export function startDiscovery(seedTopic: string, asOf: string, lookbackDays: number, maxIdeas: number) {
  return request<{ run_id: string; phase: string; status: string }>("/runs/discovery", {
    method: "POST",
    body: JSON.stringify({ seed_topic: seedTopic, as_of: asOf, lookback_days: lookbackDays, max_ideas: maxIdeas })
  });
}

export function cancelRun(runId: string) {
  return request<RunSnapshot>(`/runs/${runId}/cancel`, { method: "POST" });
}

export function deleteBlog(runId: string) {
  return request<{ deleted_runs: number }>(`/runs/${runId}/blog`, { method: "DELETE" });
}
