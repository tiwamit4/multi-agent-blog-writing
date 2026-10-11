# Multi-Agent Blog Writing

A Streamlit application that uses LangGraph agents to research, plan, write, and illustrate technical blog posts.

## Workflow

```text
Topic
  |
  v
Router ---- closed book -------------------+
  |                                        |
  +---- hybrid/open book ---> Research     |
                               |           |
                               v           v
                             Human Evidence Review
                                      |
                            Orchestrator / Planner
                                      |
                              Human Outline Review
                                      |
                               Parallel Workers
                                      |
                              Human Section Review
                                      |
                              Merge Blog Sections
                                      |
                                Plan Images
                                      |
                         Generate and Place Images
                                      |
                               Final Markdown
```

## Requirements

- Python 3.12 recommended
- A Groq API key
- Tavily and Google API keys for research and image generation
- Optional for React frontend: [Bun](https://bun.com/docs/installation) 1.4.3+

## Project Layout

```text
frontend/           Bun server and React/TypeScript UI
backend/            Python API, agents, tests, and Streamlit app
  api/              FastAPI endpoints
  blog_writer/      Shared workflow and integrations
  ui/               Streamlit UI components
  .env              API keys (local only)
  data/             SQLite database
  output/           Generated articles and images
docker-compose.yml  Starts frontend and backend together
```

## Installation

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Environment Variables

Create `backend/.env` with your API keys:

```dotenv
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
GOOGLE_API_KEY=your_google_api_key

# Optional LangSmith tracing
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=multi-agent-blog-writing
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

# Optional: defaults to data/blog_writer.sqlite3
BLOG_WRITER_DB_PATH=data/blog_writer.sqlite3
```

Do not commit the `.env` file or expose real API keys.

## Run the Streamlit Application

Run from the `backend` directory:

```bash
streamlit run bwa_frontend.py
```

Then open the local URL printed by Streamlit, normally:

```text
http://localhost:8501
```

Generated articles and images are saved under `backend/output/`.

## Run Both Services with Docker

Install and start Docker Desktop with Linux containers enabled. Keep your API
keys in `backend/.env` as described above, then run from the project
root:

```bash
docker compose up --build -d
```

Open `http://localhost:5173` for the Bun/React frontend, or
`http://localhost:8000/docs` for the FastAPI documentation. The frontend forwards
API requests to the backend container and starts after its health check passes.

The database stays in `backend/data/blog_writer.sqlite3`, and generated articles and
images stay in `backend/output/`. These host folders persist when containers stop or are
recreated. Compose sets the database path inside the container automatically.
API keys are loaded into the backend at runtime; `.env` files are excluded from
both image build contexts.

View logs or stop both services:

```bash
docker compose logs -f
docker compose down
```

Stop any locally running API or frontend using ports 8000 or 5173 before starting
Compose. Rebuild with `docker compose up --build -d` after code changes.

## Run the React Frontend

Start the optional API and React app in separate terminals:

```bash
cd backend
python -m uvicorn api.main:app --reload
```

```bash
cd frontend
bun install
bun run dev
```

The React app talks to the API at `http://localhost:8000` by default.

Open `http://localhost:5173` for the React frontend. `frontend/server.ts` uses
Bun's native HTTP server and HTML bundler to serve React, with hot reloading.
Browser requests to `/api/*` are forwarded to the existing Python API.
Set `API_BASE_URL` in `frontend/.env` to change the backend URL.
After installing Bun on Windows, reopen PowerShell so `bun` is available on PATH.

To verify a reproducible frontend build:

```bash
cd frontend
bun install --frozen-lockfile
bun test
bun run build
bun run start
```
