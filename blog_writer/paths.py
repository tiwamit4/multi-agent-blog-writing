"""Filesystem helpers for safe output paths and atomic artifact writes."""

from __future__ import annotations

import os
import re
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_DIR / "output"
IMAGES_ROOT = OUTPUT_ROOT / "images"
RUNS_ROOT = OUTPUT_ROOT / "runs"


def safe_slug(value: str) -> str:
    """Convert a blog title into a stable directory-friendly slug."""
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9 _-]+", "", slug)
    slug = re.sub(r"\s+", "_", slug).strip("_")
    return slug or "blog"


def safe_blog_id(value: str) -> str:
    """Validate the per-run ID before using it in an output path."""
    blog_id = re.sub(r"[^a-zA-Z0-9_-]+", "", value.strip())
    if not blog_id:
        raise ValueError("A valid blog_id is required for artifact storage.")
    return blog_id


def blog_images_dir(title: str, blog_id: str) -> Path:
    """Return the image directory for a specific blog title and run."""
    return IMAGES_ROOT / safe_slug(title) / safe_blog_id(blog_id)


def blog_run_dir(blog_id: str) -> Path:
    """Return the article directory for a specific run."""
    return RUNS_ROOT / safe_blog_id(blog_id)


def is_within(path: Path, root: Path) -> bool:
    """Check that a resolved path stays inside an expected root directory."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def project_relative(path: Path) -> str:
    """Return a project-relative path after preventing path traversal."""
    resolved = path.resolve()
    if not is_within(resolved, PROJECT_DIR):
        raise ValueError(f"Artifact path escapes the project directory: {path}")
    return resolved.relative_to(PROJECT_DIR).as_posix()


def atomic_write_text(path: Path, content: str) -> None:
    """Write text through a temporary file so partial writes are not exposed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Write bytes through a temporary file so partial writes are not exposed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
