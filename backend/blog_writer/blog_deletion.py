"""Shared deletion of saved blogs from the API and Streamlit sidebar."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .paths import IMAGES_ROOT, RUNS_ROOT, is_within
from .persistence import RunStore, run_store


class BlogNotFoundError(Exception):
    """The requested saved blog does not exist."""


class BlogDeleteConflictError(Exception):
    """The requested blog is not safe to delete right now."""


def delete_blog_artifacts(
    blog_id: str,
    *,
    runs_root: Path = RUNS_ROOT,
    images_root: Path = IMAGES_ROOT,
) -> None:
    """Remove only the article and image directories owned by a blog ID."""
    if not blog_id or not blog_id.isascii() or not blog_id.isalnum():
        raise BlogDeleteConflictError("Saved blog has an invalid ID.")
    article_dir = runs_root / blog_id
    image_dirs = list(images_root.glob(f"*/{blog_id}"))
    for directory, root in [(article_dir, runs_root), *[(path, images_root) for path in image_dirs]]:
        if not is_within(directory, root):
            raise BlogDeleteConflictError("Saved blog has an invalid output path.")
        if directory.exists():
            shutil.rmtree(directory)


def delete_saved_blog(
    run_id: str,
    *,
    store: RunStore = run_store,
    active_jobs: Mapping[str, Any] | None = None,
    runs_root: Path = RUNS_ROOT,
    images_root: Path = IMAGES_ROOT,
) -> int:
    """Delete every inactive phase, checkpoint, and artifact of a blog."""
    record = store.get_run(run_id)
    if record is None:
        raise BlogNotFoundError("Saved blog not found.")
    state = record["state"]
    blog_id = str(record.get("blog_id") or state.get("blog_id") or "")
    if not blog_id or not blog_id.isascii() or not blog_id.isalnum():
        raise BlogDeleteConflictError("This run is not a blog run.")
    phases = store.get_blog_runs(blog_id)
    if not phases:
        raise BlogNotFoundError("Saved blog not found.")
    if any(phase["status"] in {"created", "running", "cancelling"} for phase in phases):
        raise BlogDeleteConflictError("Wait for all blog phases to finish before deleting.")
    if active_jobs and any(
        (snapshot := job.snapshot())["status"] not in {"completed", "cancelled", "failed", "interrupted"}
        and snapshot["current_state"].get("blog_id") == blog_id
        for job in active_jobs.values()
    ):
        raise BlogDeleteConflictError("Wait for all blog phases to finish before deleting.")

    delete_blog_artifacts(blog_id, runs_root=runs_root, images_root=images_root)
    try:
        deleted_runs = store.delete_blog(blog_id)
    except ValueError as error:
        raise BlogDeleteConflictError(str(error)) from error
    if isinstance(active_jobs, dict):
        for phase in phases:
            active_jobs.pop(phase["run_id"], None)
    return deleted_runs
