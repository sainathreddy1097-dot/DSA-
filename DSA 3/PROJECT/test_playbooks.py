from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app import database, models
from app.main import create_app
from app.seed import reset_and_seed


@pytest.fixture()
def client(tmp_path: Path):
    configure_database(f"sqlite:///{(tmp_path / 'playbooks.db').as_posix()}")
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def test_playbook_analysis_creates_a_single_review_blocks_approval_and_records_override(client):
    contract = client.post("/contracts", json={
        "name": "Playbook Gate Test", "type": "Privacy", "owner": "Legal Operations", "department": "Legal",
        "compliance": "Needs Review", "reviewStatus": "Pending", "effectiveDate": "2026-10-01",
        "expiryDate": "2027-10-01", "risk": "High",
    }).json()
    version = client.post(f"/contracts/{contract['id']}/versions", json={
        "label": "v1.0", "effectiveDate": "2026-10-01", "author": "Legal Operations", "clauses": [{
            "title": "Breach Notification", "text": "The supplier will notify us after an incident.", "sourceSection": "Security",
        }],
    })
    assert version.status_code == 201
    playbook = client.post("/playbooks", json={
        "name": "Test Privacy Baseline", "version": "2026.1", "contractType": "Privacy", "status": "Active",
        "rules": [{"clauseCategory": "Breach Notification", "requiredPhrases": ["within 72 hours"], "risk": "High", "remediation": "Require a 72-hour notification commitment."}],
    })
    assert playbook.status_code == 201
    playbook_id = playbook.json()["id"]
    contract = client.get(f"/contracts/{contract['id']}").json()

    first = client.post(f"/playbooks/{playbook_id}/analyze", json={"contractId": contract["id"]})
    assert first.status_code == 200
    finding = first.json()["findings"][0]
    assert finding["status"] == "Needs Review"
    assert "within 72 hours" in finding["evidence"]
    second = client.post(f"/playbooks/{playbook_id}/analyze", json={"contractId": contract["id"]})
    assert second.status_code == 200
    assert client.get("/reviews", params={"query": "Test Privacy Baseline"}).json()["total"] == 1

    blocked = client.patch(f"/contracts/{contract['id']}", json={"updatedAt": contract["updatedAt"], "reviewStatus": "Approved"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "unresolved_high_risk_deviations"

    overridden = client.post(f"/findings/{finding['id']}/override", json={"notes": "Accepted for a documented business exception."}, headers={"X-Actor-Id": "USR-002"})
    assert overridden.status_code == 200
    refreshed = client.get(f"/contracts/{contract['id']}").json()
    approved = client.patch(f"/contracts/{contract['id']}", json={"updatedAt": refreshed["updatedAt"], "reviewStatus": "Approved"})
    assert approved.status_code == 200
    events = client.get("/audit-events", params={"query": "Playbook Finding Overridden"}).json()
    assert events["items"][0]["actorId"] == "USR-002"


def test_startup_backfills_the_baseline_playbook_for_an_existing_database(client):
    with database.SessionLocal() as session:
        session.delete(session.get(models.Playbook, "PBK-000001"))
        for actor_id in ("USR-001", "USR-002", "USR-003"):
            session.delete(session.get(models.User, actor_id))
        session.commit()
    with TestClient(create_app()):
        pass
    assert client.get("/playbooks").json()["total"] == 1
    with database.SessionLocal() as session:
        assert session.get(models.User, "USR-001").role == "Administrator"