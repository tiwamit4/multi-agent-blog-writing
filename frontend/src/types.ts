export type EvidenceItem = {
  title: string;
  url: string;
  published_at?: string | null;
  snippet?: string | null;
  source?: string | null;
};

export type Task = {
  id: number;
  title: string;
  goal: string;
  bullets: string[];
  target_words: number;
  tags: string[];
  requires_research: boolean;
  requires_citations: boolean;
  requires_code: boolean;
};

export type Plan = {
  blog_title: string;
  audience: string;
  tone: string;
  blog_kind: "explainer" | "tutorial" | "news_roundup" | "comparison" | "system_design";
  constraints: string[];
  tasks: Task[];
};

export type SectionDraft = {
  task_id: number;
  markdown: string;
};

export type RunState = {
  blog_id?: string;
  seed_topic?: string;
  as_of?: string;
  discovery_queries?: string[];
  discovery_errors?: string[];
  ranked_ideas?: DiscoveryIdea[];
  topic?: string;
  mode?: string;
  queries?: string[];
  research_errors?: string[];
  evidence?: EvidenceItem[];
  plan?: Plan | null;
  sections?: [number, string][];
  final?: string;
};

export type DiscoveryIdea = {
  rank: number;
  title: string;
  angle: string;
  why_trending: string;
  content_gap: string;
  score: number;
  freshness_score: number;
  evidence_score: number;
  gap_strength: number;
  evidence_count: number;
  freshest_evidence_date?: string | null;
  keywords?: string[];
  evidence?: EvidenceItem[];
};

export type RunSnapshot = {
  run_id: string;
  phase: string;
  status: string;
  elapsed_seconds: number;
  current_state: RunState;
  error?: string | null;
  node_counts: Record<string, number>;
  logs: string[];
  metrics: Record<string, unknown>;
};

