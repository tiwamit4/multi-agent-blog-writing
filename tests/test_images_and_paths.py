from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from blog_writer import images as image_module
from blog_writer.images import validate_image_plan
from blog_writer.models import GlobalImagePlan, ImageSpec
from ui import results


def image_spec(**overrides) -> ImageSpec:
    values = {
        "placeholder": "[[IMAGE_1]]",
        "filename": "architecture.png",
        "alt": "Architecture diagram",
        "caption": "Request flow",
        "prompt": "Draw a technical request-flow diagram",
        "size": "1536x1024",
        "quality": "high",
    }
    values.update(overrides)
    return ImageSpec(**values)


def test_image_plan_accepts_only_placeholder_insertions() -> None:
    original = "# Article\n\n## Architecture\n\nExplanation."
    valid = GlobalImagePlan(
        md_with_placeholders=(
            "# Article\n\n## Architecture\n\n[[IMAGE_1]]\n\nExplanation."
        ),
        images=[image_spec()],
    )
    validate_image_plan(original, valid)

    changed = valid.model_copy(
        update={
            "md_with_placeholders": "# Different article\n\n[[IMAGE_1]]",
        }
    )
    with pytest.raises(ValueError, match="changed article content"):
        validate_image_plan(original, changed)


def test_image_plan_rejects_duplicate_filenames() -> None:
    original = "# Article"
    plan = GlobalImagePlan(
        md_with_placeholders="# Article\n\n[[IMAGE_1]]\n\n[[IMAGE_2]]",
        images=[
            image_spec(),
            image_spec(
                placeholder="[[IMAGE_2]]",
                filename="ARCHITECTURE.png",
            ),
        ],
    )
    with pytest.raises(ValueError, match="duplicate filenames"):
        validate_image_plan(original, plan)


def test_local_image_paths_cannot_escape_images_root(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    images = project / "images"
    safe_directory = images / "blog" / "run"
    safe_directory.mkdir(parents=True)
    safe_image = safe_directory / "diagram.png"
    safe_image.write_bytes(b"png")
    secret = project / "secret.txt"
    secret.write_text("secret", encoding="utf-8")

    monkeypatch.setattr(results, "PROJECT_DIR", project)
    monkeypatch.setattr(results, "IMAGES_ROOT", images)

    assert results._resolve_image_path("images/blog/run/diagram.png") == safe_image
    assert results._resolve_image_path("images/../secret.txt") is None

    archive = results.images_zip(safe_directory)
    assert archive is not None
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        assert bundle.namelist() == ["images/blog/run/diagram.png"]


def test_markdown_bundle_ignores_an_outside_directory(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    images = project / "images"
    outside = project / "outside"
    images.mkdir(parents=True)
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(results, "PROJECT_DIR", project)
    monkeypatch.setattr(results, "IMAGES_ROOT", images)

    archive = results.bundle_zip("# Blog", "article.md", outside)
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        assert bundle.namelist() == ["article.md"]


def test_articles_with_the_same_title_are_stored_per_run(
    tmp_path, monkeypatch, sample_state
) -> None:
    monkeypatch.setattr(
        image_module,
        "blog_run_dir",
        lambda blog_id: tmp_path / "runs" / blog_id,
    )
    monkeypatch.setattr(image_module, "project_relative", lambda path: str(path))
    first_state = dict(sample_state, blog_id="run-one", merged_md="# Same title\n")
    second_state = dict(sample_state, blog_id="run-two", merged_md="# Same title\n")

    first = image_module.generate_and_place_images(first_state)
    second = image_module.generate_and_place_images(second_state)

    assert first["artifact_path"] != second["artifact_path"]
    assert (tmp_path / "runs" / "run-one" / "article.md").is_file()
    assert (tmp_path / "runs" / "run-two" / "article.md").is_file()


def test_image_size_and_quality_reach_the_generator(
    tmp_path, monkeypatch, sample_state
) -> None:
    captured = {}

    def fake_generate(prompt: str, size: str, quality: str) -> bytes:
        captured.update(prompt=prompt, size=size, quality=quality)
        return b"png"

    monkeypatch.setattr(image_module, "_gemini_generate_image_bytes", fake_generate)
    monkeypatch.setattr(
        image_module,
        "blog_images_dir",
        lambda title, blog_id: tmp_path / "images" / blog_id,
    )
    monkeypatch.setattr(
        image_module,
        "blog_run_dir",
        lambda blog_id: tmp_path / "runs" / blog_id,
    )
    monkeypatch.setattr(image_module, "project_relative", lambda path: str(path))
    state = dict(
        sample_state,
        md_with_placeholders="# Blog\n\n[[IMAGE_1]]",
        image_specs=[image_spec().model_dump()],
    )

    image_module.generate_and_place_images(state)

    assert captured["size"] == "1536x1024"
    assert captured["quality"] == "high"
