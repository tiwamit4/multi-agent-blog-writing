import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import App from "../src/App";
import OutlineEditor from "../src/OutlineEditor";
import type { Plan } from "../src/types";
import { DiscoveryResults, discoveryPrompt } from "../src/DiscoveryWorkspace";
import type { DiscoveryIdea, RunSnapshot } from "../src/types";

test("initial workspace shows blog creation and saved-run controls", () => {
  const html = renderToStaticMarkup(<App />);
  for (const label of ["Blog Writing Agent", "Create a blog", "Past blogs", "Persistent runs", "Gather evidence"]) {
    expect(html).toContain(label);
  }
  expect(html).not.toContain("Usage and performance");
});

test("discovery results show ranked ideas, grounded sources and blog handoff", () => {
  const idea: DiscoveryIdea = { rank: 1, title: "Durable agents", angle: "Recovery patterns", content_gap: "Operational examples",
    why_trending: "Recent releases", score: 88, freshness_score: 90, evidence_score: 85, gap_strength: 80,
    evidence_count: 1, evidence: [{ title: "Primary source", url: "https://example.com/source" }] };
  const run: RunSnapshot = { run_id: "discovery-1", phase: "discovery", status: "completed", elapsed_seconds: 1,
    current_state: { ranked_ideas: [idea], as_of: "2026-10-12" }, metrics: {}, logs: [], node_counts: {} };
  const html = renderToStaticMarkup(<DiscoveryResults run={run} onWrite={() => {}} />);
  expect(html).toContain("Durable agents");
  expect(html).toContain("https://example.com/source");
  expect(html).toContain("Write this topic");
  expect(discoveryPrompt(idea)).toBe("Durable agents\n\nRecommended angle: Recovery patterns\nContent gap to address: Operational examples");
});

test("outline review renders editable plan fields and section options", () => {
  const plan: Plan = {
    blog_title: "A safe <outline>", audience: "Developers", tone: "Practical", blog_kind: "tutorial",
    constraints: ["Use examples"],
    tasks: [{ id: 1, title: "Getting started", goal: "Explain setup", bullets: ["Install", "Run"],
      target_words: 300, tags: ["setup"], requires_research: true, requires_citations: false, requires_code: true }]
  };
  const html = renderToStaticMarkup(<OutlineEditor value={JSON.stringify(plan)} onChange={() => {}} />);
  expect(html).toContain("A safe &lt;outline&gt;");
  expect(html).toContain('value="300"');
  expect(html).toContain("Getting started");
  expect(html).toContain("Citations");
  expect(html).not.toContain("code-editor");
});
