"""Result tabs for plans, evidence, markdown preview, images, and logs."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from blog_writer.graph import section_regeneration_app
from blog_writer.paths import (
    IMAGES_ROOT,
    PROJECT_DIR,
    blog_images_dir,
    is_within,
    safe_slug,
)
from ui.job_monitor import start_job
from ui.outline_editor import plan_as_dict, task_rows
from ui.persistence_panel import extract_title_from_md


def _validated_image_files(images_dir: Path) -> list[Path]:
    """List image files only when the directory is inside the image root."""
    resolved_directory = images_dir.resolve()
    if not is_within(resolved_directory, IMAGES_ROOT) or not resolved_directory.is_dir():
        return []
    return sorted(
        resolved
        for path in resolved_directory.rglob("*")
        if path.is_file()
        and is_within((resolved := path.resolve()), IMAGES_ROOT)
    )


def bundle_zip(md_text: str, md_filename: str, images_dir: Path) -> bytes:
    """Create an in-memory ZIP containing markdown and any generated images."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(md_filename, md_text.encode("utf-8"))
        for path in _validated_image_files(images_dir):
            archive.write(path, arcname=path.relative_to(PROJECT_DIR).as_posix())
    return buffer.getvalue()


def images_zip(images_dir: Path) -> bytes | None:
    """Create an in-memory ZIP for generated images, if any exist."""
    image_files = _validated_image_files(images_dir)
    if not image_files:
        return None
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in image_files:
            archive.write(path, arcname=path.relative_to(PROJECT_DIR).as_posix())
    return buffer.getvalue()


_MD_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)")
_CAPTION_LINE_RE = re.compile(r"^\*(?P<cap>.+)\*$")


def blog_images_directory(title: str, blog_id: str, markdown: str) -> Path:
    """Resolve the expected image directory for current or loaded markdown."""
    if blog_id:
        try:
            return blog_images_dir(title, blog_id)
        except ValueError:
            pass
    for match in _MD_IMG_RE.finditer(markdown):
        source = (match.group("src") or "").strip()
        if source and not source.startswith(("http://", "https://")):
            image_path = _resolve_image_path(source)
            if image_path is not None:
                return image_path.parent
    return IMAGES_ROOT / safe_slug(title)


def _resolve_image_path(source: str) -> Path | None:
    """Resolve a markdown image source while blocking paths outside images root."""
    source_path = Path(source.strip())
    candidate = source_path if source_path.is_absolute() else PROJECT_DIR / source_path
    resolved = candidate.resolve()
    return resolved if is_within(resolved, IMAGES_ROOT) else None


def render_markdown_with_local_images(markdown: str) -> None:
    """Render markdown while displaying safe local image paths via Streamlit."""
    matches = list(_MD_IMG_RE.finditer(markdown))
    if not matches:
        st.markdown(markdown, unsafe_allow_html=False)
        return

    parts: list[tuple[str, str]] = []
    last = 0
    for match in matches:
        before = markdown[last : match.start()]
        if before:
            parts.append(("md", before))
        alt = (match.group("alt") or "").strip()
        source = (match.group("src") or "").strip()
        parts.append(("img", f"{alt}|||{source}"))
        last = match.end()
    if markdown[last:]:
        parts.append(("md", markdown[last:]))

    index = 0
    while index < len(parts):
        kind, payload = parts[index]
        if kind == "md":
            st.markdown(payload, unsafe_allow_html=False)
            index += 1
            continue

        alt, source = payload.split("|||", 1)
        caption = None
        if index + 1 < len(parts) and parts[index + 1][0] == "md":
            next_markdown = parts[index + 1][1].lstrip()
            if next_markdown.strip():
                first_line = next_markdown.splitlines()[0].strip()
                caption_match = _CAPTION_LINE_RE.match(first_line)
                if caption_match:
                    caption = caption_match.group("cap").strip()
                    parts[index + 1] = (
                        "md",
                        "\n".join(next_markdown.splitlines()[1:]),
                    )

        if source.startswith(("http://", "https://")):
            st.image(source, caption=caption or alt or None, width="stretch")
        else:
            image_path = _resolve_image_path(source)
            if image_path is None:
                st.warning(f"Blocked image path outside the project image directory: `{source}`")
            elif image_path.is_file():
                st.image(
                    str(image_path), caption=caption or alt or None, width="stretch"
                )
            else:
                st.warning(
                    f"Image not found: `{source}` (looked for `{image_path}`)"
                )
        index += 1


def render_results(out: dict[str, Any] | None, job_is_running: bool) -> None:
    """Render all result tabs for the current draft, final article, or saved file."""
    tab_plan, tab_evidence, tab_preview, tab_images, tab_logs = st.tabs(
        ["Plan", "Evidence", "Markdown Preview", "Images", "Logs"]
    )

    if not out:
        with tab_preview:
            st.info("Enter a topic and generate an outline to begin.")
        return

    final_markdown = out.get("final") or ""
    plan_object = out.get("plan")
    if hasattr(plan_object, "blog_title"):
        blog_title = plan_object.blog_title
    elif isinstance(plan_object, dict):
        blog_title = plan_object.get("blog_title", "blog")
    else:
        blog_title = extract_title_from_md(final_markdown, "blog")
    blog_id = str(out.get("blog_id") or "")
    images_dir = blog_images_directory(blog_title, blog_id, final_markdown)

    with tab_plan:
        st.subheader("Plan")
        if not plan_object:
            st.info("No plan is available for this saved Markdown file.")
        else:
            plan_dict = plan_as_dict(plan_object)
            st.write("**Title:**", plan_dict.get("blog_title"))
            summary_columns = st.columns(3)
            summary_columns[0].write(
                "**Audience:** " + str(plan_dict.get("audience"))
            )
            summary_columns[1].write("**Tone:** " + str(plan_dict.get("tone")))
            summary_columns[2].write(
                "**Blog kind:** " + str(plan_dict.get("blog_kind", ""))
            )
            display_tasks = task_rows(plan_object).drop(
                columns=["goal", "bullets"], errors="ignore"
            )
            st.dataframe(display_tasks, hide_index=True, width="stretch")
            with st.expander("Task details"):
                st.json(plan_dict.get("tasks", []))

            if final_markdown and out.get("sections"):
                # Regeneration starts a new run ID so previous artifacts remain intact.
                task_options = {
                    f"{task['id']}: {task['title']}": int(task["id"])
                    for task in plan_dict.get("tasks", [])
                }
                selected_task = st.selectbox(
                    "Section to regenerate",
                    options=list(task_options),
                    disabled=job_is_running,
                )
                if st.button(
                    "Regenerate selected section",
                    disabled=job_is_running,
                    width="stretch",
                ):
                    regeneration_state = dict(out)
                    regeneration_state.update(
                        {
                            "blog_id": uuid4().hex[:12],
                            "target_task_id": task_options[selected_task],
                            "merged_md": "",
                            "md_with_placeholders": "",
                            "image_specs": [],
                            "artifact_path": "",
                            "final": "",
                        }
                    )
                    start_job(
                        section_regeneration_app,
                        regeneration_state,
                        "regeneration",
                    )
                    st.rerun()

    with tab_evidence:
        st.subheader("Evidence")
        research_errors = out.get("research_errors") or []
        if research_errors:
            with st.expander(
                f"Research warnings ({len(research_errors)})",
                expanded=True,
            ):
                for error in research_errors:
                    st.warning(error)
        evidence = out.get("evidence") or []
        if not evidence:
            st.info(
                "No evidence returned; the router may have selected closed-book mode."
            )
        else:
            rows = []
            for item in evidence:
                item_dict = item.model_dump() if hasattr(item, "model_dump") else item
                rows.append(
                    {
                        "title": item_dict.get("title"),
                        "published_at": item_dict.get("published_at"),
                        "source": item_dict.get("source"),
                        "url": item_dict.get("url"),
                    }
                )
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with tab_preview:
        st.subheader("Markdown Preview")
        if not final_markdown:
            if out.get("sections"):
                st.info("Review and approve the generated sections to build the article.")
            else:
                st.info("Approve the outline to generate section drafts.")
        else:
            render_markdown_with_local_images(final_markdown)
            markdown_filename = f"{safe_slug(blog_title)}.md"
            st.download_button(
                "Download Markdown",
                data=final_markdown.encode("utf-8"),
                file_name=markdown_filename,
                mime="text/markdown",
            )
            st.download_button(
                "Download bundle (Markdown + images)",
                data=bundle_zip(final_markdown, markdown_filename, images_dir),
                file_name=f"{safe_slug(blog_title)}_bundle.zip",
                mime="application/zip",
            )

    with tab_images:
        st.subheader("Images")
        specs = out.get("image_specs") or []
        if specs:
            st.write("**Image plan:**")
            st.json(specs)
        if images_dir.is_dir() and is_within(images_dir, IMAGES_ROOT):
            image_files = _validated_image_files(images_dir)
            if not image_files:
                st.warning("The image directory exists but is empty.")
            for path in sorted(image_files):
                st.image(str(path), caption=path.name, width="stretch")
            archive = images_zip(images_dir)
            if archive:
                st.download_button(
                    "Download images",
                    data=archive,
                    file_name=f"{safe_slug(blog_title)}_images.zip",
                    mime="application/zip",
                )
        elif final_markdown:
            st.info("No images were generated for this blog.")

    with tab_logs:
        st.subheader("Logs")
        logs = st.session_state.get("last_run_logs", [])
        st.text_area("Event log", value="\n\n".join(logs[-100:]), height=520)
