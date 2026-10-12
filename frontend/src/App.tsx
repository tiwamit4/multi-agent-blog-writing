import { useEffect, useMemo, useRef, useState } from "react";
import ArticlePreview from "./ArticlePreview";
import {
  approveOutline,
  approveSections,
  approveSources,
  getRun,
  regenerateSection,
  startEvidence,
  listRuns,
  cancelRun,
  deleteBlog
} from "./api";
import DiscoveryWorkspace from "./DiscoveryWorkspace";
import OutlineEditor from "./OutlineEditor";
import type { EvidenceItem, Plan, RunSnapshot, SectionDraft } from "./types";

const terminalStatuses = new Set(["completed", "cancelled", "failed", "interrupted"]);

function today() {
  return new Date().toISOString().slice(0, 10);
}

function sectionDraftsFromRun(run: RunSnapshot | null): SectionDraft[] {
  return (run?.current_state.sections ?? []).map(([taskId, markdown]) => ({
    task_id: taskId,
    markdown
  }));
}

export default function App() {
  const [workspace, setWorkspace] = useState("Blog Writer");
  const [handoff, setHandoff] = useState({ topic: "", date: "", version: 0 });
  return <>
    <div hidden={workspace !== "Blog Writer"}><BlogWriterApp workspace={workspace} onWorkspace={setWorkspace} handoff={handoff} /></div>
    <div hidden={workspace !== "Topic Discovery"}><DiscoveryWorkspace onWorkspace={setWorkspace} onWrite={(topic, date) => {
      setHandoff(previous => ({ topic, date, version: previous.version + 1 }));
      setWorkspace("Blog Writer");
    }} /></div>
  </>;
}

function BlogWriterApp({ workspace, onWorkspace, handoff }: {
  workspace: string; onWorkspace: (value: string) => void;
  handoff: { topic: string; date: string; version: number };
}) {
  const [savedRuns, setSavedRuns] = useState<RunSnapshot[]>([]);
  const [historyError, setHistoryError] = useState("");
  const [resultTab, setResultTab] = useState("Preview");
  const [busy, setBusy] = useState(false);
  const [topic, setTopic] = useState("");
  const [asOf, setAsOf] = useState(today());
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const hydratedRunId = useRef<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [planJson, setPlanJson] = useState("");
  const [sections, setSections] = useState<SectionDraft[]>([]);
  const isActive = Boolean(runId && (!run || run.run_id !== runId || !terminalStatuses.has(run.status)));

  useEffect(() => {
    if (handoff.version) { setTopic(handoff.topic); setAsOf(handoff.date); }
  }, [handoff]);

  async function refreshHistory() {
    try { setSavedRuns((await listRuns()).filter(item => item.phase !== "discovery")); setHistoryError(""); }
    catch { setHistoryError("Could not load saved runs. Check that the API is running."); }
  }

  useEffect(() => { void refreshHistory(); }, [run?.status]);

  function openRun(snapshot: RunSnapshot) {
    hydratedRunId.current = null;
    setRun(snapshot);
    setRunId(snapshot.run_id);
    setTopic(snapshot.current_state.topic ?? "");
    setError("");
    setPollError("");
  }

  async function removeBlog(snapshot: RunSnapshot) {
    const title = snapshot.current_state.plan?.blog_title ?? snapshot.current_state.topic ?? "this blog";
    if (!window.confirm(`Delete "${title}" and all its saved runs, article, and images? This cannot be undone.`)) return;
    await performAction(async () => {
      await deleteBlog(snapshot.run_id);
      if (run && run.current_state.blog_id === snapshot.current_state.blog_id) {
        setRun(null);
        setRunId("");
        setEvidence([]);
        setPlanJson("");
        setSections([]);
      }
      setSavedRuns(previous => previous.filter(item => item.current_state.blog_id !== snapshot.current_state.blog_id));
      await refreshHistory();
    });
  }

  useEffect(() => {
    if (!runId) return;
    if (run?.run_id === runId && terminalStatuses.has(run.status)) return;
    let stopped = false;

    async function poll() {
      try {
        const snapshot = await getRun(runId);
        if (stopped) return;
        setRun(snapshot);
        setPollError("");
      } catch (err) {
        if (!stopped) setPollError(err instanceof Error ? err.message : String(err));
      }
    }

    poll();
    const timer = window.setInterval(poll, 1500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [runId, run?.run_id, run?.status]);

  useEffect(() => {
    if (!run || run.status !== "completed" || hydratedRunId.current === run.run_id) return;
    hydratedRunId.current = run.run_id;
    if (run.phase === "evidence") {
      setEvidence(run.current_state.evidence ?? []);
    }
    if (run.phase === "planning" && run.current_state.plan) {
      setPlanJson(JSON.stringify(run.current_state.plan, null, 2));
    }
    if (["writing", "section_regeneration"].includes(run.phase)) {
      setSections(sectionDraftsFromRun(run));
    }
  }, [run]);

  const canReviewEvidence = run?.phase === "evidence" && run.status === "completed";
  const canReviewOutline = run?.phase === "planning" && run.status === "completed";
  const canReviewSections =
    (run?.phase === "writing" || run?.phase === "section_regeneration") &&
    run.status === "completed";
  const finalMarkdown = run?.current_state.final ?? "";
  const finalRunId = run?.run_id ?? "";
  const plan = run?.current_state.plan ?? null;
  const tasksById = useMemo(() => {
    const entries = (plan?.tasks ?? []).map((task) => [task.id, task.title] as const);
    return new Map(entries);
  }, [plan]);

  async function performAction(action: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  }

  async function startRun() {
    if (!topic.trim()) {
      setError("Enter a topic first.");
      return;
    }
    setEvidence([]); setPlanJson(""); setSections([]);
    const result = await startEvidence(topic.trim(), asOf);
    setRun(null);
    setPollError("");
    setRunId(result.run_id);
  }

  async function approveEvidenceStep() {
    const kept = evidence.filter((item) => item.title.trim() && item.url.trim());
    const result = await approveSources(runId, kept);
    setRun(null);
    setPollError("");
    setRunId(result.run_id);
  }

  async function approveOutlineStep() {
    const parsedPlan = JSON.parse(planJson) as Plan;
    const result = await approveOutline(runId, parsedPlan);
    setRun(null);
    setPollError("");
    setRunId(result.run_id);
  }

  async function regenerateSectionStep(taskId: number) {
    const result = await regenerateSection(runId, taskId, sections);
    setRun(null);
    setPollError("");
    setRunId(result.run_id);
  }

  async function approveSectionsStep() {
    const result = await approveSections(runId, sections);
    setRun(null);
    setPollError("");
    setRunId(result.run_id);
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <label>Workspace<select value={workspace} onChange={event => onWorkspace(event.target.value)}>
          <option>Blog Writer</option><option>Topic Discovery</option>
        </select></label>
        <h2>Create a blog</h2>
        <label>
          Topic
          <textarea
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            rows={4}
            placeholder="Enter a topic for your blog"
          />
        </label>
        <label>
          As-of date
          <input value={asOf} type="date" onChange={(event) => setAsOf(event.target.value)} />
        </label>
        <button className="primary" disabled={isActive || busy} onClick={() => void performAction(startRun)}>
          1. Gather evidence
        </button>
        <div className="sidebar-group">
          <h3>Past blogs</h3>
          {savedRuns.some(item => item.current_state.final) ? savedRuns.filter(item => item.current_state.final).map(item => (
            <div className="saved-blog-row" key={item.run_id}>
              <button className="history-item" disabled={isActive || busy} onClick={() => openRun(item)}>{item.current_state.plan?.blog_title ?? item.current_state.topic ?? "Saved blog"}</button>
              <button className="delete-button" type="button" aria-label={`Delete ${item.current_state.plan?.blog_title ?? item.current_state.topic ?? "saved blog"}`} disabled={isActive || busy} onClick={() => void removeBlog(item)}>Delete</button>
            </div>
          )) : <p className="caption">No saved blogs found.</p>}
        </div>
        <div className="sidebar-group">
          <h3>Persistent runs</h3>
          <button disabled={busy} onClick={() => void refreshHistory()}>Refresh runs</button>
          {historyError && <p role="alert" className="caption">{historyError}</p>}
          {savedRuns.map(item => <div className="saved-blog-row" key={item.run_id}>
            <button className="history-item" disabled={isActive || busy} onClick={() => openRun(item)}>
              {item.current_state.topic ?? item.run_id.slice(0, 8)}<small>{item.phase} · {item.status}</small>
            </button>
            {terminalStatuses.has(item.status) && <button className="delete-button" type="button"
              aria-label={`Delete ${item.status} run for ${item.current_state.topic ?? item.run_id.slice(0, 8)}`}
              disabled={isActive || busy} onClick={() => void removeBlog(item)}>Delete</button>}
          </div>)}
          {!savedRuns.length && !historyError && <p className="caption">No saved runs yet.</p>}
        </div>
        {runId && (
          <div className="run-meta">
            <span>Run</span>
            <code>{runId.slice(0, 8)}</code>
          </div>
        )}
      </aside>

      <section className="workspace">
        <h1>Blog Writing Agent</h1>
        {(error || pollError || run?.error) && (
          <div role="alert" className="notice error">{error || pollError || run?.error}</div>
        )}

        {run && <div className="status-bar">
          <div>
            <span className="label">Phase</span>
            <strong>{run?.phase ?? "idle"}</strong>
          </div>
          <div>
            <span className="label">Status</span>
            <strong>{run?.status ?? "ready"}</strong>
          </div>
          <div>
            <span className="label">Elapsed</span>
            <strong>{run ? `${run.elapsed_seconds.toFixed(1)}s` : "0.0s"}</strong>
          </div>
        </div>}

        {!run && <p className="empty-state">Enter a topic in the sidebar and select ?1. Gather evidence? to begin.</p>}
        {isActive && <div className="notice running" role="status"><span className="spinner" /> Running {run?.phase}?
          <button disabled={busy} onClick={() => void performAction(async () => { setRun(await cancelRun(runId)); })}>Cancel run</button>
        </div>}

        {canReviewEvidence && (
          <section className="panel">
            <header>
              <h2>Human Evidence Review</h2>
              <button onClick={() => setEvidence([...evidence, { title: "", url: "" }])}>
                Add source
              </button>
            </header>
            <div className="source-grid">
              {evidence.map((item, index) => (
                <div className="source-row" key={index}>
                  <input
                    value={item.title}
                    onChange={(event) => {
                      const copy = [...evidence];
                      copy[index] = { ...item, title: event.target.value };
                      setEvidence(copy);
                    }}
                    placeholder="Title"
                  />
                  <input
                    value={item.url}
                    onChange={(event) => {
                      const copy = [...evidence];
                      copy[index] = { ...item, url: event.target.value };
                      setEvidence(copy);
                    }}
                    placeholder="URL"
                  />
                  <button onClick={() => setEvidence(evidence.filter((_, i) => i !== index))}>
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <button className="primary" disabled={busy || isActive} onClick={() => void performAction(approveEvidenceStep)}>
              2. Approve sources and generate outline
            </button>
          </section>
        )}

        {canReviewOutline && (
          <section className="panel">
            <header>
              <h2>Human Outline Review</h2>
            </header>
            <OutlineEditor value={planJson} onChange={setPlanJson} />
            <button className="primary" disabled={busy || isActive} onClick={() => void performAction(approveOutlineStep)}>
              3. Write section drafts
            </button>
          </section>
        )}

        {canReviewSections && (
          <section className="panel">
            <header>
              <h2>Human Section Review</h2>
            </header>
            {sections.map((section, index) => (
              <div className="section-editor" key={section.task_id}>
                <div className="section-title">
                  <strong>{tasksById.get(section.task_id) ?? `Section ${section.task_id}`}</strong>
                  <button disabled={busy || isActive} onClick={() => void performAction(() => regenerateSectionStep(section.task_id))}>
                    Regenerate
                  </button>
                </div>
                <textarea
                  value={section.markdown}
                  rows={10}
                  onChange={(event) => {
                    const copy = [...sections];
                    copy[index] = { ...section, markdown: event.target.value };
                    setSections(copy);
                  }}
                />
              </div>
            ))}
            <button className="primary" disabled={busy || isActive} onClick={() => void performAction(approveSectionsStep)}>
              4. Approve sections and build final article
            </button>
          </section>
        )}

        {run && <section className="panel"><h2>Usage and performance</h2><div className="metrics-grid">
          {[ ["Input tokens", Number(run.metrics.input_tokens ?? 0).toLocaleString()], ["Output tokens", Number(run.metrics.output_tokens ?? 0).toLocaleString()], ["LLM calls", String(run.metrics.llm_calls ?? 0)], ["Elapsed", `${run.elapsed_seconds.toFixed(1)}s`], ["Est. Groq cost", `$${Number(run.metrics.estimated_cost_usd ?? 0).toFixed(5)}`] ].map(([label, value]) => <div key={label}><span className="label">{label}</span><strong>{value}</strong></div>)}
        </div><p className="caption">Metrics for this phase. Text cost estimate excludes research and image generation.</p></section>}

        {finalMarkdown && (
          <section className="panel">
            <header>
              <h2>Generated blog</h2>
              <div className="result-actions"><button onClick={() => {
                const url = URL.createObjectURL(new Blob([finalMarkdown], { type: "text/markdown;charset=utf-8" }));
                const link = document.createElement("a"); link.href = url; link.download = "article.md"; link.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
              }}>Download Markdown</button>
              <a className="button-link" href={`/api/runs/${encodeURIComponent(finalRunId)}/bundle`} download>Download ZIP</a></div>
            </header>
            <div className="tabs" role="tablist" aria-label="Blog results">
              {["Preview", "Markdown", "Plan", "Evidence"].map(tab => <button key={tab} role="tab" aria-selected={resultTab === tab} onClick={() => setResultTab(tab)}>{tab}</button>)}
            </div>
            {resultTab === "Preview" && <ArticlePreview markdown={finalMarkdown} runId={finalRunId} />}
            {resultTab === "Markdown" && <pre className="markdown-preview">{finalMarkdown}</pre>}
            {resultTab === "Plan" && <pre>{JSON.stringify(plan, null, 2)}</pre>}
            {resultTab === "Evidence" && <ul>{(run?.current_state.evidence ?? []).map((item, index) => <li key={index}><a href={/^https?:\/\//i.test(item.url) ? item.url : undefined} target="_blank" rel="noreferrer">{item.title}</a></li>)}</ul>}
          </section>
        )}

        {run?.logs?.length ? (
          <details className="panel log-panel">
            <summary>Execution logs</summary>
            <pre>{run.logs.slice(-20).join("\n\n")}</pre>
          </details>
        ) : null}
      </section>
    </main>
  );
}
