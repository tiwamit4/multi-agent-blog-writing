from fastapi.testclient import TestClient

from api import main


def test_discovery_api_starts_shared_graph_with_validated_inputs(monkeypatch):
    captured = {}

    def start(graph, state, phase):
        captured.update(graph=graph, state=state, phase=phase)
        return {"run_id": "test-discovery", "phase": phase, "status": "running"}

    monkeypatch.setattr(main, "_start_phase", start)
    client = TestClient(main.app)
    response = client.post("/runs/discovery", json={
        "seed_topic": "  AI agents  ", "as_of": "2026-10-12",
        "lookback_days": 14, "max_ideas": 5,
    })
    assert response.status_code == 200
    assert captured["graph"] is main.discovery_app
    assert captured["phase"] == "discovery"
    assert captured["state"]["seed_topic"] == "AI agents"
    assert captured["state"]["as_of"] == "2026-10-12"
    assert captured["state"]["lookback_days"] == 14
    assert captured["state"]["max_ideas"] == 5
    assert captured["state"]["ranked_ideas"] == []


def test_discovery_api_rejects_invalid_inputs_before_starting(monkeypatch):
    def unexpected(*args):
        raise AssertionError("Invalid input must not start external work")

    monkeypatch.setattr(main, "_start_phase", unexpected)
    client = TestClient(main.app)
    for payload in [
        {"seed_topic": " "}, {"seed_topic": "AI", "lookback_days": 0},
        {"seed_topic": "AI", "max_ideas": 13}, {"seed_topic": "AI", "as_of": "invalid"},
    ]:
        assert client.post("/runs/discovery", json=payload).status_code == 422
