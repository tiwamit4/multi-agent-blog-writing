"""Image planning, image generation, placeholder replacement, and article output."""

from __future__ import annotations

import os
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from .clients import llm
from .models import GlobalImagePlan, State
from .paths import (
    atomic_write_bytes,
    atomic_write_text,
    blog_images_dir,
    blog_run_dir,
    project_relative,
)
from .prompt import (
    DECIDE_IMAGES_SYSTEM_PROMPT,
    IMAGE_GENERATION_SUFFIX,
    IMAGE_PLANNING_USER_INSTRUCTION,
)

_PLACEHOLDER_RE = re.compile(r"\[\[IMAGE_[123]\]\]")
_ASPECT_RATIO_BY_SIZE = {
    "1024x1024": "1:1",
    "1024x1536": "2:3",
    "1536x1024": "3:2",
}


def _normalized_markdown(markdown: str) -> str:
    """Normalize whitespace before comparing markdown with placeholders removed."""
    return re.sub(r"\s+", " ", markdown).strip()


def validate_image_plan(merged_markdown: str, image_plan: GlobalImagePlan) -> None:
    """Ensure the image planner only inserts declared placeholders."""
    placeholders = [image.placeholder for image in image_plan.images]
    filenames = [image.filename.casefold() for image in image_plan.images]
    if len(placeholders) != len(set(placeholders)):
        raise ValueError("Image plan contains duplicate placeholders.")
    if len(filenames) != len(set(filenames)):
        raise ValueError("Image plan contains duplicate filenames.")

    found_placeholders = _PLACEHOLDER_RE.findall(image_plan.md_with_placeholders)
    if sorted(found_placeholders) != sorted(placeholders):
        raise ValueError(
            "Image placeholders in Markdown must match the declared image specifications."
        )
    if any(image_plan.md_with_placeholders.count(value) != 1 for value in placeholders):
        raise ValueError("Each image placeholder must appear exactly once.")

    without_placeholders = _PLACEHOLDER_RE.sub("", image_plan.md_with_placeholders)
    if _normalized_markdown(without_placeholders) != _normalized_markdown(merged_markdown):
        raise ValueError("Image planning changed article content instead of only adding placeholders.")


def decide_images(state: State) -> dict:
    """Ask whether images are useful and return placeholder-enhanced markdown."""
    planner = llm.with_structured_output(
        GlobalImagePlan, method="json_schema", strict=True
    )
    merged_md = state["merged_md"]
    plan = state["plan"]
    if plan is None:
        raise ValueError("Cannot plan images without an approved blog plan.")

    try:
        image_plan = planner.invoke(
            [
                SystemMessage(content=DECIDE_IMAGES_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Blog kind: {plan.blog_kind}\n"
                        f"Topic: {state['topic']}\n\n"
                        f"{IMAGE_PLANNING_USER_INSTRUCTION}\n\n"
                        f"{merged_md}"
                    )
                ),
            ]
        )
        validate_image_plan(merged_md, image_plan)
    except Exception as error:
        # Image planning should not block the article if the markdown was changed.
        warnings = list(state.get("research_errors") or [])
        warnings.append(f"Image planning skipped: {str(error)[:300]}")
        return {
            "md_with_placeholders": merged_md,
            "image_specs": [],
            "research_errors": warnings,
        }

    return {
        "md_with_placeholders": image_plan.md_with_placeholders,
        "image_specs": [image.model_dump() for image in image_plan.images],
    }


def _gemini_generate_image_bytes(
    prompt: str,
    size: str,
    quality: str,
) -> bytes:
    """Generate one PNG image with Gemini and return its raw bytes."""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    http_options = types.HttpOptions(
        timeout=60_000,
        retry_options=types.HttpRetryOptions(
            attempts=3,
            initial_delay=1.0,
            max_delay=8.0,
            exp_base=2.0,
            jitter=0.2,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        ),
    )
    client = genai.Client(api_key=api_key, http_options=http_options)
    generation_prompt = (
        f"{prompt}\n\nCanvas size: {size}. Output quality: {quality}. "
        f"{IMAGE_GENERATION_SUFFIX}"
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=generation_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=_ASPECT_RATIO_BY_SIZE[size],
                output_mime_type="image/png",
            ),
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_ONLY_HIGH",
                )
            ],
        ),
    )

    parts = getattr(response, "parts", None)
    if not parts and getattr(response, "candidates", None):
        try:
            parts = response.candidates[0].content.parts
        except (AttributeError, IndexError, TypeError):
            parts = None

    if not parts:
        raise RuntimeError("No image content returned (safety, quota, or SDK response).")

    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            return inline.data

    raise RuntimeError("No inline image bytes found in the Gemini response.")


def _write_article(markdown: str, blog_id: str) -> Path:
    """Persist the final article markdown for one run."""
    article_path = blog_run_dir(blog_id) / "article.md"
    atomic_write_text(article_path, markdown)
    return article_path


def generate_and_place_images(state: State) -> dict:
    """Generate planned images, replace placeholders, and save final markdown."""
    plan = state["plan"]
    if plan is None:
        raise ValueError("Cannot generate images without an approved blog plan.")

    blog_id = state.get("blog_id", "")
    markdown = state.get("md_with_placeholders") or state["merged_md"]
    image_specs = state.get("image_specs", []) or []

    if not image_specs:
        article_path = _write_article(markdown, blog_id)
        return {
            "artifact_path": project_relative(article_path),
            "final": markdown,
        }

    images_dir = blog_images_dir(plan.blog_title, blog_id)
    images_dir.mkdir(parents=True, exist_ok=True)

    for spec in image_specs:
        placeholder = spec["placeholder"]
        filename = Path(spec["filename"]).name
        output_path = images_dir / filename

        if not output_path.exists():
            try:
                image_bytes = _gemini_generate_image_bytes(
                    spec["prompt"],
                    spec["size"],
                    spec["quality"],
                )
                atomic_write_bytes(output_path, image_bytes)
            except Exception as error:
                prompt_block = (
                    f"> **[IMAGE GENERATION FAILED]** {spec.get('caption', '')}\n>\n"
                    f"> **Alt:** {spec.get('alt', '')}\n>\n"
                    f"> **Prompt:** {spec.get('prompt', '')}\n>\n"
                    f"> **Error:** {error}\n"
                )
                markdown = markdown.replace(placeholder, prompt_block)
                continue

        image_path = project_relative(output_path)
        image_markdown = f"![{spec['alt']}]({image_path})\n*{spec['caption']}*"
        markdown = markdown.replace(placeholder, image_markdown)

    article_path = _write_article(markdown, blog_id)
    return {
        "artifact_path": project_relative(article_path),
        "final": markdown,
    }
