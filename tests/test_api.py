import time
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import COST_RISK_Q, make_services
from researcher.api import create_app
from researcher.models import Job
from researcher.storage import Store


def _client(tmp_path: Path) -> TestClient:
    services = make_services(tmp_path)
    return TestClient(create_app(services=services))


def _wait(client: TestClient, job_id: str) -> dict:
    for _ in range(200):
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_full_api_flow(tmp_path):
    with _client(tmp_path) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/config").json()["mode"] == "offline"
        resp = client.post("/api/jobs", json={"question": COST_RISK_Q})
        assert resp.status_code == 202
        job_id = resp.json()["id"]
        data = _wait(client, job_id)
        assert data["status"] == "completed"
        assert client.get(f"/api/jobs/{job_id}/sources").json()
        assert client.get(f"/api/jobs/{job_id}/claims").json()
        logs = client.get(f"/api/jobs/{job_id}/logs").json()
        assert (
            logs
            and client.get(f"/api/jobs/{job_id}/logs", params={"after": logs[-1]["seq"]}).json()
            == []
        )
        report = client.get(f"/api/jobs/{job_id}/report").json()
        assert {s["kind"] for sec in report["sections"] for s in sec["statements"]} >= {
            "conflicting"
        }
        md = client.get(f"/api/jobs/{job_id}/report.md")
        assert (
            md.headers["content-type"].startswith("text/plain") and "# Research report" in md.text
        )
        assert [j["id"] for j in client.get("/api/jobs").json()] == [job_id]
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_validation_and_not_found(tmp_path):
    with _client(tmp_path) as client:
        assert client.post("/api/jobs", json={"question": "short"}).status_code == 422
        assert client.post("/api/jobs", json={"question": "x" * 2000}).status_code == 422
        assert (
            client.post(
                "/api/jobs", json={"question": COST_RISK_Q, "options": {"max_subquestions": 99}}
            ).status_code
            == 422
        )
        assert client.get("/api/jobs/nope").status_code == 404
        assert client.get("/api/jobs/nope/report").status_code == 404


def test_history_survives_restart_and_interrupted_jobs_are_marked(tmp_path):
    services = make_services(tmp_path)
    with TestClient(create_app(services=services)) as client:
        job_id = client.post("/api/jobs", json={"question": COST_RISK_Q}).json()["id"]
        _wait(client, job_id)
    store = Store(services.settings.db_path)
    stuck = Job.model_validate(
        store.get(job_id).model_dump() | {"id": "stuck", "status": "running"}
    )
    store.save(stuck)
    store.close()
    with TestClient(create_app(services=services)) as client:
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
        assert client.get("/api/jobs/stuck").json()["status"] == "failed"
        assert "interrupted" in client.get("/api/jobs/stuck").json()["error"]
