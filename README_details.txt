Additional README Details

Features

- Routes topics between closed-book, hybrid, and open-book workflows.
- Discovers trending technical subjects and under-served article angles.
- Ranks discovery ideas by freshness, grounded evidence, and content-gap strength.
- Performs optional web research with Tavily.
- Runs bounded Tavily searches concurrently with retries, timeouts, and visible partial-failure warnings.
- Rejects research URLs that were not present in the original search results.
- Adds a human-in-the-loop evidence review step to approve, remove, edit, or add sources.
- Produces an editable outline before any section writers run.
- Runs section writers in parallel after outline approval.
- Adds a human-in-the-loop section review step before final Markdown is built.
- Allows each generated section to be edited or regenerated before final approval.
- Supports cooperative cancellation with live per-agent progress.
- Persists graph checkpoints, run state, metrics, logs, and status in SQLite.
- Resumes interrupted, cancelled, or failed runs from their latest successful graph step.
- Regenerates one selected section without rewriting the others.
- Displays token usage, latency, LLM calls, and estimated Groq text cost.
- Merges sections into a complete Markdown article.
- Plans and generates up to three technical images with Gemini.
- Displays the plan, evidence, Markdown preview, images, and execution logs.
- Saves generated blogs locally and allows previous Markdown files to be loaded.
- Downloads Markdown, images, or a combined ZIP bundle.

Project Structure

multi-agent-blog-writing/
|-- blog_writer/
|   |-- __init__.py       # Package entrypoint
|   |-- clients.py        # Shared Groq client configuration
|   |-- config.py         # Token, search, outline, and generation-size limits
|   |-- discovery.py      # Trend scouting, gap analysis, and idea ranking
|   |-- graph.py          # LangGraph assembly and compilation
|   |-- images.py         # Image planning, generation, and placement
|   |-- jobs.py           # Background execution and cancellation
|   |-- metrics.py        # Token, cost, and latency accounting
|   |-- models.py         # Pydantic schemas and graph state
|   |-- paths.py          # Safe per-run artifact and image paths
|   |-- persistence.py    # SQLite checkpointer and durable run registry
|   |-- research.py       # Tavily search and evidence processing
|   |-- router.py         # Research-routing decision
|   `-- writing.py        # Planning, worker fan-out, and section merging
|-- ui/
|   |-- __init__.py
|   |-- sidebar.py
|   |-- topic_discovery.py
|   |-- evidence_review.py
|   |-- outline_editor.py
|   |-- section_review.py
|   |-- job_monitor.py
|   |-- results.py
|   |-- persistence_panel.py
|   `-- metrics_panel.py
|-- tests/
|-- output/              # Generated articles and images
|-- bwa_backend.py
|-- bwa_frontend.py
|-- requirements.txt
`-- README.md

Usage

Use the Workspace selector in the sidebar to switch between blog writing and topic discovery.

Token and Cost Tuning

Edit blog_writer/config.py to reduce or increase token usage. The most useful knobs are query count, search results per query, prompt snippet length, evidence count per section, section count, and target words per section.

Discover topics:

1. Open Topic Discovery.
2. Enter a technology or domain such as AI agents or platform engineering.
3. Choose a freshness window and the number of ideas to return.
4. Click Discover and rank topics.
5. Compare overall, freshness, evidence, and content-gap scores.
6. Inspect the grounded source links for each idea.
7. Click Write this topic to transfer the title, angle, and gap into the blog writer.

Discovery uses two recent-news searches and three broader technical searches. The gap analyst can only attach URLs returned by those searches. Final ranking is deterministic:

overall score = 45% freshness + 40% evidence strength + 15% content-gap strength

Discovery runs use the same SQLite checkpoints, cancellation, metrics, and resume controls as blog-generation runs.

Write a blog:

1. Enter a technical blog topic in the sidebar.
2. Select the date used for recency-sensitive research.
3. Click Gather evidence.
4. Review researched sources, remove weak sources, edit metadata, or add manual sources.
5. Click Approve sources and generate outline.
6. Edit the title, metadata, sections, bullets, word targets, and task flags.
7. Click Write section drafts.
8. Follow live agent progress or cancel the active generation.
9. Review each generated section, edit Markdown directly, or regenerate only the section that needs work.
10. Click Approve sections and build final article.
11. Regenerate individual sections from the Plan tab later when needed.
12. Review and download the Markdown, images, or combined bundle.

Generated Markdown files are saved under output/runs/<run-id>/article.md, so blogs with the same title cannot overwrite one another. Each run stores its images separately under output/images/<blog-slug>/<run-id>/.

The Persistent runs panel lists recent SQLite-backed operations. Completed runs can be reopened. Interrupted, cancelled, and failed runs can be resumed from the latest successful LangGraph checkpoint. The database stores the plan, evidence, completed sections, metrics, logs, elapsed time, errors, and run status.

Cancellation is cooperative: it takes effect after the currently active external API request returns. Completed sections are not published as a final result for a cancelled job.

The cost shown in the interface estimates Groq text inference only. It uses the current documented pricing for llama-3.3-70b-versatile: $0.59 per million input tokens and $0.79 per million output tokens. Tavily and Gemini costs are excluded.

Running the Backend Directly

The compiled LangGraph application is available as:

from bwa_backend import app

config = {"configurable": {"thread_id": "unique-run-id"}}
result = app.invoke(inputs, config)

The input must contain the complete graph state defined in blog_writer/models.py. A unique thread_id is required because the graph is compiled with SQLite checkpointing. Reusing a thread ID continues that thread's saved state.

The interface uses focused graph entrypoints from blog_writer.graph:

- evidence_app for routing, optional Tavily research, and the source-review checkpoint
- planning_app for creating an outline from human-approved evidence
- writing_app for approved-outline fan-out and section draft generation
- section_draft_regeneration_app for replacing one draft section before finalization
- finalizing_app for merging approved section drafts, planning images, and saving artifacts
- section_regeneration_app for replacing one section after finalization and rebuilding the article

Persistence

The default database is data/blog_writer.sqlite3. Its write-ahead log files are created beside it while the application is running. These files are excluded by .gitignore.

LangGraph writes a state checkpoint after each graph step. A separate blog_runs table in the same database stores UI-oriented metadata and metrics. If the process stops while a job is marked as running, the next application process marks it as interrupted and enables Resume run.

SQLite is appropriate for this local application and lightweight synchronous workloads. For a multi-server production deployment, migrate the checkpointer and run registry to PostgreSQL.

Tests

python -m pytest -q
python -m pip check

Troubleshooting

streamlit: command not found

Activate the virtual environment before starting the application:

streamlit run bwa_frontend.py

Missing LangGraph or LangChain modules

Confirm that packages were installed into the same interpreter used to run Streamlit:

python -m pip install -r requirements.txt
python -c "import langgraph, langchain_core, langchain_groq"

No research evidence

Research is skipped for evergreen topics. For research-enabled topics, Tavily failures are reported with the query that failed instead of being silently ignored. If useful sources are missing, add manual sources in the evidence review table before generating the outline.

Images are not generated

Confirm that GOOGLE_API_KEY is configured. The application keeps the blog usable and inserts an image-generation failure block when image generation fails.
