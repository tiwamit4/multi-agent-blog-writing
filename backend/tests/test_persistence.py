from __future__ import annotations

from blog_writer.persistence import RunStore


def test_run_store_round_trips_typed_state(tmp_path, sample_state) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    store.create_run(
        run_id="run-1",
        checkpoint_thread_id="thread-1",
        phase="planning",
        state=sample_state,
    )

    restored = store.get_run("run-1")

    assert restored is not None
    assert restored["state"]["plan"] == sample_state["plan"]
    assert restored["state"]["sections"] == []
    assert restored["state"]["research_errors"] == []
    assert restored["state"]["artifact_path"] == ""
