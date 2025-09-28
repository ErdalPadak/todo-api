from fastapi.testclient import TestClient
from app import app
client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

def test_create_patch_metrics():
    r = client.post("/tasks", json={"title": "pytest"})
    assert r.status_code == 200
    tid = r.json()["id"]
    r = client.patch(f"/tasks/{tid}", json={"done": True})
    assert r.status_code == 200
    m = client.get("/metrics").json()
    assert set(["count","done","open"]).issubset(m.keys())
