from fastapi.testclient import TestClient
import pytest

from api import main
from blog_writer.persistence import RunStore


def _saved_state(blog_id: str, *, finished: bool = True) -> dict:
    return {
        "blog_id": blog_id,
        "topic": "Reliable agents",
        "final": "# Reliable agents" if finished else "",
        "artifact_path": f"output/runs/{blog_id}/article.md",
    }


def test_delete_saved_blog_removes_only_its_runs_checkpoints_and_files(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    store = RunStore(tmp_path / "data" / "runs.sqlite3")
    with store._connect() as connection:
        connection.execute("CREATE TABLE checkpoints (thread_id TEXT, value TEXT)")
        connection.execute("CREATE TABLE writes (thread_id TEXT, value TEXT)")
    for run_id, blog_id in [("old-phase", "target123"), ("final-phase", "target123"), ("other", "other456")]:
        store.create_run(run_id=run_id, checkpoint_thread_id=f"thread-{run_id}", phase="finalizing", state=_saved_state(blog_id))
        store.update_run(run_id=run_id, status="completed", state=_saved_state(blog_id), metrics={}, node_counts={}, logs=[], elapsed_seconds=1, error=None)
        with store._connect() as connection:
            connection.execute("INSERT INTO checkpoints VALUES (?, 'checkpoint')", (f"thread-{run_id}",))
            connection.execute("INSERT INTO writes VALUES (?, 'write')", (f"thread-{run_id}",))

    output = tmp_path / "output"
    article = output / "runs" / "target123" / "article.md"
    image = output / "images" / "reliable_agents" / "target123" / "diagram.png"
    unrelated = output / "runs" / "other456" / "article.md"
    for path in (article, image, unrelated):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("saved", encoding="utf-8")
    monkeypatch.setattr(main, "run_store", store)
    monkeypatch.setattr(main, "RUNS_ROOT", output / "runs")
    monkeypatch.setattr(main, "IMAGES_ROOT", output / "images")
    monkeypatch.setattr(main, "ACTIVE_JOBS", {})

    response = TestClient(main.app).delete("/runs/final-phase/blog")
    assert response.status_code == 200
    assert response.json() == {"deleted_runs": 2}
    assert not article.exists() and not image.exists()
    assert unrelated.exists()
    assert store.get_run("old-phase") is None and store.get_run("final-phase") is None
    assert store.get_run("other") is not None
    with store._connect() as connection:
        assert [row[0] for row in connection.execute("SELECT thread_id FROM checkpoints")] == ["thread-other"]
        assert [row[0] for row in connection.execute("SELECT thread_id FROM writes")] == ["thread-other"]


def test_delete_refuses_active_or_unknown_blogs(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs.sqlite3")
    store.create_run(run_id="active", checkpoint_thread_id="thread-active", phase="evidence", state=_saved_state("active123"))
    store.update_run(run_id="active", status="running", state=_saved_state("active123"), metrics={}, node_counts={}, logs=[], elapsed_seconds=1, error=None)
    monkeypatch.setattr(main, "run_store", store)
    monkeypatch.setattr(main, "ACTIVE_JOBS", {})
    client = TestClient(main.app)
    assert client.delete("/runs/active/blog").status_code == 409
    assert client.delete("/runs/missing/blog").status_code == 404
    assert store.get_run("active") is not None


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_delete_blog_without_final_article(tmp_path, monkeypatch, status):
    store = RunStore(tmp_path / "runs.sqlite3")
    state = _saved_state("unfinished123", finished=False)
    store.create_run(
        run_id="unfinished", checkpoint_thread_id="thread-unfinished",
        phase="writing", state=state,
    )
    store.update_run(
        run_id="unfinished", status=status, state=state,
        metrics={}, node_counts={}, logs=[], elapsed_seconds=1, error=None,
    )
    partial_image = tmp_path / "output" / "images" / "unfinished" / "unfinished123" / "draft.png"
    partial_image.parent.mkdir(parents=True)
    partial_image.write_bytes(b"partial")
    monkeypatch.setattr(main, "run_store", store)
    monkeypatch.setattr(main, "RUNS_ROOT", tmp_path / "output" / "runs")
    monkeypatch.setattr(main, "IMAGES_ROOT", tmp_path / "output" / "images")
    monkeypatch.setattr(main, "ACTIVE_JOBS", {})

    response = TestClient(main.app).delete("/runs/unfinished/blog")
    assert response.status_code == 200
    assert response.json() == {"deleted_runs": 1}
    assert store.get_run("unfinished") is None
    assert not partial_image.exists()
