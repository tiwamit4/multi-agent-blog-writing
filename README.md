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
                            Orchestrator / Planner
                                      |
                              Human Outline Review
                                      |
                               Parallel Workers
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

## Installation

```bash
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

Create a `.env` file in the project directory:

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

## Run the Application

```bash
streamlit run bwa_frontend.py
```

Then open the local URL printed by Streamlit, normally:

```text
http://localhost:8501
```

Generated articles and images are saved under the `output/` folder.
