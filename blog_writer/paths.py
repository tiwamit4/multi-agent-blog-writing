from __future__ import annotations

import os
import re
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
IMAGES_ROOT = PROJECT_DIR / "images"
RUNS_ROOT = PROJECT_DIR / "runs"


def safe_slug(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9 _-]+", "", slug)
    slug = re.sub(r"\s+", "_", slug).strip("_")
    return slug or "blog"


def safe_blog_id(value: str) -> str:
    blog_id = re.sub(r"[^a-zA-Z0-9_-]+", "", value.strip())
    if not blog_id:
        raise ValueError("A valid blog_id is required for artifact storage.")
    return blog_id


def blog_images_dir(title: str, blog_id: str) -> Path:
    return IMAGES_ROOT / safe_slug(title) / safe_blog_id(blog_id)


def blog_run_dir(blog_id: str) -> Path:
    return RUNS_ROOT / safe_blog_id(blog_id)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def project_relative(path: Path) -> str:
    resolved = path.resolve()
    if not is_within(resolved, PROJECT_DIR):
        raise ValueError(f"Artifact path escapes the project directory: {path}")
    return resolved.relative_to(PROJECT_DIR).as_posix()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
