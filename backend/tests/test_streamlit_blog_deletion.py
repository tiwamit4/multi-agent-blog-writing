from streamlit.testing.v1 import AppTest
import pytest

from blog_writer.persistence import RunStore
from ui import persistence_panel


def test_streamlit_delete_selected_blog_requires_confirmation_and_removes_artifacts(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs.sqlite3")
    state = {"blog_id": "saved123", "topic": "Safe blogs", "final": "# Safe blogs"}
    store.create_run(
        run_id="saved-run", checkpoint_thread_id="saved-thread",
        phase="finalizing", state=state,
    )
    store.update_run(
        run_id="saved-run", status="completed", state=state,
        metrics={}, node_counts={}, logs=[], elapsed_seconds=1, error=None,
    )
    article = tmp_path / "output" / "runs" / "saved123" / "article.md"
    image = tmp_path / "output" / "images" / "safe_blogs" / "saved123" / "diagram.png"
    for path in (article, image):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Safe blogs", encoding="utf-8")
    monkeypatch.setattr(persistence_panel, "run_store", store)
    monkeypatch.setattr(persistence_panel, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(persistence_panel, "RUNS_ROOT", tmp_path / "output" / "runs")
    monkeypatch.setattr(persistence_panel, "IMAGES_ROOT", tmp_path / "output" / "images")

    app = AppTest.from_file("bwa_frontend.py", default_timeout=30).run()
    assert not app.exception, app.exception
    button = next(button for button in app.button if button.label == "Delete selected blog")
    assert button.disabled
    checkbox = next(box for box in app.checkbox if box.label.startswith("Confirm permanent deletion"))
    checkbox.set_value(True).run()
    button = next(button for button in app.button if button.label == "Delete selected blog")
    assert not button.disabled
    button.click().run()
    assert not app.exception, app.exception
    assert store.get_run("saved-run") is None
    assert not article.exists() and not image.exists()
    assert app.session_state["last_notice"] == "Selected blog deleted."


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_streamlit_can_delete_old_run_without_final_article(tmp_path, monkeypatch, status):
    store = RunStore(tmp_path / "runs.sqlite3")
    state = {"blog_id": "oldblog123", "topic": "Old blog", "final": ""}
    store.create_run(
        run_id="old-run", checkpoint_thread_id="old-thread",
        phase="writing", state=state,
    )
    store.update_run(
        run_id="old-run", status=status, state=state,
        metrics={}, node_counts={}, logs=[], elapsed_seconds=1, error=None,
    )
    monkeypatch.setattr(persistence_panel, "run_store", store)
    monkeypatch.setattr(persistence_panel, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(persistence_panel, "RUNS_ROOT", tmp_path / "output" / "runs")
    monkeypatch.setattr(persistence_panel, "IMAGES_ROOT", tmp_path / "output" / "images")

    app = AppTest.from_file("bwa_frontend.py", default_timeout=30).run()
    assert not app.exception, app.exception
    button = next(button for button in app.button if button.label == "Delete selected run and blog")
    assert button.disabled
    box = next(box for box in app.checkbox if box.label.startswith("Confirm permanent deletion of this blog"))
    box.set_value(True).run()
    button = next(button for button in app.button if button.label == "Delete selected run and blog")
    button.click().run()
    assert not app.exception, app.exception
    assert store.get_run("old-run") is None
    assert app.session_state["last_notice"] == "Selected blog and its saved runs deleted."
