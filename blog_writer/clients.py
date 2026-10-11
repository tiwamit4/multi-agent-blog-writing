"""Shared LLM client configuration and startup API-key validation."""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

REQUIRED_API_KEYS = ("GROQ_API_KEY", "TAVILY_API_KEY", "GOOGLE_API_KEY")


def validate_api_keys() -> None:
    """Fail early when any external service key required by the app is missing."""
    missing = [key for key in REQUIRED_API_KEYS if not os.getenv(key)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing required API keys: {names}. "
            "Add them to the project .env file before starting the application."
        )


validate_api_keys()

GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "60"))
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "3"))

llm = ChatGroq(
    model=GROQ_MODEL,
    temperature=0.6,
    reasoning_effort="default",
    model_kwargs={"top_p": 0.95},
    timeout=GROQ_TIMEOUT_SECONDS,
    max_retries=GROQ_MAX_RETRIES,
)

__all__ = [
    "GROQ_MAX_RETRIES",
    "GROQ_MODEL",
    "GROQ_TIMEOUT_SECONDS",
    "REQUIRED_API_KEYS",
    "llm",
    "validate_api_keys",
]
