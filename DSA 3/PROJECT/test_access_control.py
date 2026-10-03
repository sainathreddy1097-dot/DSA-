from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app.main import create_app
from app.seed import reset_and_seed


@pytest.fixture()
def client(tmp_path: Path):
    configure_database(f"sqlite:///{(tmp_path / 'access.db').as_posix()}")
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def _contract_payload() -> dict:
    return {
        "name": "Access Control Test",
        "type": "Services",
        "owner": "Legal Operations",
        "department": "Legal",
        "compliance": "Needs Review",
        "reviewStatus": "Pending",
        "effectiveDate": "2026-10-01",
        "expiryDate": "2027-10-01",
        "risk": "Medium",
    }


def test_mutations_require_an_authorized_actor_and_audit_the_resolved_identity(client):
    client.headers.pop("X-Actor-Id")
    missing = client.post("/contracts", json=_contract_payload())
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_required"

    forbidden = client.post("/contracts", json=_contract_payload(), headers={"X-Actor-Id": "USR-003"})
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"

    created = client.post("/contracts", json=_contract_payload(), headers={"X-Actor-Id": "USR-001"})
    assert created.status_code == 201

    events = client.get("/audit-events", params={"query": "Contract Created"}).json()
    event = next(item for item in events["items"] if item["entity"] == created.json()["id"])
    assert event["user"] == "Asha Menon"
    assert event["actorId"] == "USR-001"
    assert event["actorRole"] == "Administrator"