import { useEffect, useState } from "react";
import { cancelRun, getRun, listRuns, startDiscovery } from "./api";
import type { DiscoveryIdea, RunSnapshot } from "./types";

const terminal = new Set(["completed", "failed", "cancelled", "interrupted"]);

export function discoveryPrompt(idea: DiscoveryIdea) {
  return `${idea.title}\n\nRecommended angle: ${idea.angle}\nContent gap to address: ${idea.content_gap}`;
}

export function DiscoveryResults({ run, onWrite }: { run: RunSnapshot; onWrite: (topic: string, date: string) => void }) {
  const [minimum, setMinimum] = useState(0);
  const ideas = run.current_state.ranked_ideas ?? [];
  const visible = ideas.filter(idea => idea.score >= minimum);
  return <>
    {!!run.current_state.discovery_errors?.length && <details className="panel"><summary>Search warnings</summary>
      {run.current_state.discovery_errors.map((error, index) => <p className="notice error" key={index}>{error}</p>)}
    </details>}
    {ideas.length ? <>
      <div className="metrics-grid discovery-metrics">
        {[["Ranked ideas", ideas.length], ["Top score", Math.max(...ideas.map(idea => idea.score)).toFixed(1)],
          ["Evidence links", ideas.reduce((sum, idea) => sum + idea.evidence_count, 0)],
          ["Strongest gap", Math.max(...ideas.map(idea => idea.gap_strength)).toFixed(1)]].map(([label, value]) =>
            <div key={label}><span className="label">{label}</span><strong>{value}</strong></div>)}
      </div>
      <label>Minimum overall score: {minimum}<input type="range" min="0" max="100" value={minimum} onChange={event => setMinimum(Number(event.target.value))} /></label>
      <div className="table-scroll"><table><thead><tr>{["Rank", "Topic", "Overall", "Freshness", "Evidence", "Gap", "Sources"].map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{visible.map(idea => <tr key={idea.rank}><td>{idea.rank}</td><td>{idea.title}</td><td>{idea.score.toFixed(1)}</td><td>{idea.freshness_score.toFixed(1)}</td><td>{idea.evidence_score.toFixed(1)}</td><td>{idea.gap_strength.toFixed(1)}</td><td>{idea.evidence_count}</td></tr>)}</tbody>
      </table></div>
      {!visible.length && <p className="empty-state">No topics meet this minimum score. Lower the filter to see more ideas.</p>}
      <h2>Ranked opportunities</h2>
      {visible.map(idea => <article className="task-editor opportunity" key={idea.rank}>
        <h3>#{idea.rank} — {idea.title}</h3>
        <p><strong>Recommended angle:</strong> {idea.angle}</p>
        <p><strong>Why it is timely:</strong> {idea.why_trending}</p>
        <p><strong>Content gap:</strong> {idea.content_gap}</p>
        <p className="caption">Keywords: {(idea.keywords ?? []).join(", ")}</p>
        <details><summary>Evidence ({idea.evidence_count} sources)</summary><ul>{(idea.evidence ?? []).map((source, index) => <li key={index}>
          <a href={/^https?:\/\//i.test(source.url) ? source.url : undefined} target="_blank" rel="noreferrer">{source.title || source.url}</a> — {source.published_at ?? "date unknown"}
        </li>)}</ul></details>
        <button className="primary" onClick={() => onWrite(discoveryPrompt(idea), run.current_state.as_of ?? new Date().toISOString().slice(0, 10))}>Write this topic</button>
      </article>)}
      <p className="caption">Overall score = 45% freshness + 40% evidence strength + 15% content-gap strength.</p>
    </> : <p className="empty-state">{run.status === "completed" ? "No ranked ideas were found. Try a broader domain or a longer freshness window." : "Ranked ideas will appear when discovery finishes."}</p>}
    <details className="panel"><summary>Discovery queries</summary><ul>{(run.current_state.discovery_queries ?? []).map((query, index) => <li key={index}>{query}</li>)}</ul></details>
  </>;
}

export default function DiscoveryWorkspace({ onWorkspace, onWrite }: {
  onWorkspace: (value: string) => void; onWrite: (topic: string, date: string) => void;
}) {
  const [seed, setSeed] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [lookback, setLookback] = useState(30);
  const [maxIdeas, setMaxIdeas] = useState(8);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [history, setHistory] = useState<RunSnapshot[]>([]);
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [busy, setBusy] = useState(false);
  const active = Boolean(runId && (!run || !terminal.has(run.status)));

  async function refreshHistory() {
    try { setHistory((await listRuns()).filter(item => item.phase === "discovery")); setHistoryError(""); }
    catch { setHistoryError("Could not load discovery history. Check the API connection."); }
  }
  useEffect(() => { void refreshHistory(); }, [run?.status]);
  useEffect(() => {
    if (!runId || (run?.run_id === runId && terminal.has(run.status))) return;
    let stopped = false;
    async function poll() {
      try { const next = await getRun(runId); if (!stopped) { setRun(next); setPollError(""); } }
      catch (error) { if (!stopped) setPollError(error instanceof Error ? error.message : String(error)); }
    }
    void poll();
    const timer = setInterval(poll, 1500);
    return () => { stopped = true; clearInterval(timer); };
  }, [runId, run?.run_id, run?.status]);

  async function act(action: () => Promise<void>) {
    setError(""); setBusy(true);
    try { await action(); }
    catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  async function discover() {
    if (!seed.trim()) { setError("Enter a technology or domain to explore."); return; }
    const result = await startDiscovery(seed.trim(), date, lookback, maxIdeas);
    setRun(null); setPollError(""); setRunId(result.run_id);
  }
  return <main className="app-shell">
    <aside className="sidebar">
      <label>Workspace<select value="Topic Discovery" onChange={event => onWorkspace(event.target.value)}><option>Blog Writer</option><option>Topic Discovery</option></select></label>
      <h2>Discover technical topics</h2>
      <label>Technology or domain<input value={seed} onChange={event => setSeed(event.target.value)} placeholder="e.g. AI agents, vLLM, platform engineering" /></label>
      <label>Discovery date<input type="date" value={date} onChange={event => setDate(event.target.value)} /></label>
      <label>Freshness window<select value={lookback} onChange={event => setLookback(Number(event.target.value))}>{[7, 14, 30, 60, 90].map(days => <option value={days} key={days}>{days} days</option>)}</select></label>
      <label>Ideas to return: {maxIdeas}<input type="range" min="3" max="12" value={maxIdeas} onChange={event => setMaxIdeas(Number(event.target.value))} /></label>
      <button className="primary" disabled={busy || active} onClick={() => void act(discover)}>Discover and rank topics</button>
      <div className="sidebar-group"><h3>Persistent discovery runs</h3>
        <button disabled={busy} onClick={() => void refreshHistory()}>Refresh runs</button>
        {historyError && <p role="alert" className="caption">{historyError}</p>}
        {!history.length && !historyError && <p className="caption">No discovery runs yet.</p>}
        {history.map(item => <button className="history-item" disabled={busy || active} key={item.run_id} onClick={() => {
          setRunId(item.run_id); setRun(item); setSeed(item.current_state.seed_topic ?? ""); setDate(item.current_state.as_of ?? date); setError(""); setPollError("");
        }}>{item.current_state.seed_topic ?? "Topic discovery"}<small>{item.status}</small></button>)}
      </div>
    </aside>
    <section className="workspace">
      <h1>Technical Topic Discovery</h1>
      <p className="caption">Search current technical coverage, identify under-served angles, and rank ideas grounded in source evidence.</p>
      {(error || pollError || run?.error) && <div role="alert" className="notice error">{error || pollError || run?.error}</div>}
      {active && <div className="notice running" role="status"><span className="spinner" /> Discovering and ranking topics…<button disabled={busy} onClick={() => void act(async () => { setRun(await cancelRun(runId)); })}>Cancel run</button></div>}
      {!run && !active && <p className="empty-state">Choose a technology or domain in the sidebar to discover article opportunities.</p>}
      {run && <><p className="caption">Status: {run.status} · Elapsed: {run.elapsed_seconds.toFixed(1)}s · LLM calls: {String(run.metrics.llm_calls ?? 0)}</p>
        <DiscoveryResults key={run.run_id} run={run} onWrite={onWrite} />
        {!!run.logs.length && <details className="panel"><summary>Execution logs</summary><pre>{run.logs.slice(-20).join("\n\n")}</pre></details>}
      </>}
    </section>
  </main>;
}
