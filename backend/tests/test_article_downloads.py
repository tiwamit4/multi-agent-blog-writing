"""The browser preview and bundle can only read a completed blog's images."""

from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from api import main
from blog_writer.persistence import RunStore


def test_article_image_and_bundle_are_scoped_to_the_saved_blog(tmp_path, monkeypatch, sample_state):
    store = RunStore(tmp_path / "runs.sqlite3")
    state = dict(sample_state)
    state.update(
        blog_id="blog123",
        final="# Reliable Agents\n\n![Diagram](output/images/reliable_agents/blog123/diagram.png)",
    )
    store.create_run(
        run_id="final-run", checkpoint_thread_id="thread-final", phase="finalizing", state=state,
    )
    store.update_run(
        run_id="final-run", status="completed", state=state, metrics={},
        node_counts={}, logs=[], elapsed_seconds=1, error=None,
    )
    images_root = tmp_path / "output" / "images"
    image = images_root / "reliable_agents" / "blog123" / "diagram.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image bytes")
    other = images_root / "reliable_agents" / "other456" / "secret.png"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"secret")
    monkeypatch.setattr(main, "run_store", store)
    monkeypatch.setattr(main, "IMAGES_ROOT", images_root)
    client = TestClient(main.app)

    url = "/runs/final-run/image"
    allowed = client.get(url, params={"path": "output/images/reliable_agents/blog123/diagram.png"})
    assert allowed.status_code == 200
    assert allowed.content == b"image bytes"
    assert allowed.headers["content-type"] == "image/png"
    assert client.get(url, params={"path": "output/images/reliable_agents/other456/secret.png"}).status_code == 404
    assert client.get(url, params={"path": "output/images/reliable_agents/blog123/../other456/secret.png"}).status_code == 404
    assert client.get("/runs/missing/bundle").status_code == 404

    bundle = client.get("/runs/final-run/bundle")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(bundle.content)) as archive:
        assert sorted(archive.namelist()) == [
            "output/images/reliable_agents/blog123/diagram.png",
            "reliable_agents.md",
        ]
        assert archive.read("reliable_agents.md").decode() == state["final"]
        assert archive.read("output/images/reliable_agents/blog123/diagram.png") == b"image bytes"
