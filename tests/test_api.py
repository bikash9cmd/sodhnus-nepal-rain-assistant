from fastapi.testclient import TestClient


def test_local_api(monkeypatch, tmp_path):
    from sodhnus import api

    monkeypatch.setattr(api.log_store, "path", tmp_path / "asks.jsonl")
    client = TestClient(api.app)
    r = client.post("/ask", json={"question": "Kathmandu monsoon total 2023"})
    assert r.status_code == 200 and "1235.1" in r.json()["answer"] and r.json()["sources"] == ["Kathmandu Airport"]
    assert client.post("/feedback", json={"id": r.json()["id"], "helpful": True}).json() == {"ok": True}
    assert client.get("/health").json()["data_through"] == "2025-08-24"
    assert client.post("/ask", json={"question": "Will it rain tomorrow?"}).json()["refused"] == "forecast"
