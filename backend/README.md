# Python backend

This folder contains the FastAPI service, shared blog-writing agents, tests, and
the existing Streamlit application. Run Python commands from this directory.

Keep `GROQ_API_KEY`, `TAVILY_API_KEY`, and `GOOGLE_API_KEY` in `.env` here.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

The API listens at http://localhost:8000. To run the Streamlit app instead:

```powershell
python -m streamlit run bwa_frontend.py
```

Run tests with `python -m pytest`. Database files live in `data/` and generated
articles and images in `output/`.

To run the API and Bun frontend in containers, run
`docker compose up --build -d` from the repository root.
