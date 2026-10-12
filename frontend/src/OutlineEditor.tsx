import type { Plan, Task } from "./types";

export default function OutlineEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  if (!value) return null;
  const plan = JSON.parse(value) as Plan;
  function update(patch: Partial<Plan>) { onChange(JSON.stringify({ ...plan, ...patch }, null, 2)); }
  function updateTask(index: number, patch: Partial<Task>) {
    update({ tasks: plan.tasks.map((task, i) => i === index ? { ...task, ...patch } : task) });
  }
  return <div className="outline-form">
    <label>Blog title<input value={plan.blog_title} onChange={event => update({ blog_title: event.target.value })} /></label>
    <div className="form-columns">
      <label>Audience<input value={plan.audience} onChange={event => update({ audience: event.target.value })} /></label>
      <label>Tone<input value={plan.tone} onChange={event => update({ tone: event.target.value })} /></label>
      <label>Blog kind<select value={plan.blog_kind} onChange={event => update({ blog_kind: event.target.value as Plan["blog_kind"] })}>
        {["explainer", "tutorial", "news_roundup", "comparison", "system_design"].map(kind => <option key={kind}>{kind}</option>)}
      </select></label>
    </div>
    <label>Constraints (one per line)<textarea value={plan.constraints.join("\n")} onChange={event => update({ constraints: event.target.value.split("\n") })} /></label>
    <h3>Sections</h3>
    {plan.tasks.map((task, index) => <details key={task.id} open className="task-editor">
      <summary>Section {index + 1}: {task.title}</summary>
      <label>Title<input value={task.title} onChange={event => updateTask(index, { title: event.target.value })} /></label>
      <label>Goal<input value={task.goal} onChange={event => updateTask(index, { goal: event.target.value })} /></label>
      <label>Key points (one per line)<textarea value={task.bullets.join("\n")} onChange={event => updateTask(index, { bullets: event.target.value.split("\n") })} /></label>
      <div className="form-columns">
        <label>Target words<input type="number" min={1} value={task.target_words} onChange={event => updateTask(index, { target_words: Number(event.target.value) })} /></label>
        <label>Tags (comma separated)<input value={task.tags.join(",")} onChange={event => updateTask(index, { tags: event.target.value.split(",") })} /></label>
      </div>
      <div className="check-row">
        <label><input type="checkbox" checked={task.requires_research} onChange={event => updateTask(index, { requires_research: event.target.checked })} /> Research</label>
        <label><input type="checkbox" checked={task.requires_citations} onChange={event => updateTask(index, { requires_citations: event.target.checked })} /> Citations</label>
        <label><input type="checkbox" checked={task.requires_code} onChange={event => updateTask(index, { requires_code: event.target.checked })} /> Code</label>
      </div>
    </details>)}
  </div>;
}
