from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app.main import create_app
from app.seed import reset_and_seed


@pytest.fixture()
def client(tmp_path: Path):
    configure_database(f"sqlite:///{(tmp_path / 'lifecycle.db').as_posix()}")
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def contract_payload(name: str) -> dict:
    return {
        "name": name,
        "type": "Services",
        "owner": "Legal Operations",
        "department": "Legal",
        "compliance": "Needs Review",
        "reviewStatus": "Pending",
        "effectiveDate": "2026-10-01",
        "expiryDate": "2027-10-01",
        "risk": "Medium",
        "counterparty": "Example Supplier",
        "jurisdiction": "Karnataka, India",
        "description": "Lifecycle API test contract.",
    }


def test_create_and_update_contract(client):
    created_response = client.post("/contracts", json=contract_payload("Lifecycle Test"))
    assert created_response.status_code == 201
    created = created_response.json()

    response = client.patch(
        f"/contracts/{created['id']}",
        json={"owner": "Updated Owner", "updatedAt": created["updatedAt"]},
    )

    assert response.status_code == 200
    assert response.json()["owner"] == "Updated Owner"
    assert response.json()["updatedAt"] != created["updatedAt"]


def test_stale_contract_update_returns_conflict(client):
    created = client.post("/contracts", json=contract_payload("Concurrency Test")).json()
    first = client.patch(
        f"/contracts/{created['id']}",
        json={"owner": "First", "updatedAt": created["updatedAt"]},
    )
    assert first.status_code == 200

    stale = client.patch(
        f"/contracts/{created['id']}",
        json={"owner": "Second", "updatedAt": created["updatedAt"]},
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_record"


def test_archive_and_restore_preserve_contract(client):
    created = client.post("/contracts", json=contract_payload("Archivable Test")).json()

    archived = client.post(f"/contracts/{created['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["archivedAt"] is not None
    assert client.get(f"/contracts/{created['id']}").status_code == 404

    restored = client.post(f"/contracts/{created['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archivedAt"] is None
    assert client.get(f"/contracts/{created['id']}").status_code == 200


def test_bulk_action_rolls_back_when_any_contract_is_missing(client):
    before = client.get("/contracts/CTR-001").json()["compliance"]

    response = client.post(
        "/contracts/bulk-actions",
        json={
            "contractIds": ["CTR-001", "MISSING"],
            "action": "set_compliance",
            "value": "Exception",
        },
    )

    assert response.status_code == 404
    assert client.get("/contracts/CTR-001").json()["compliance"] == before


def test_bulk_archive_is_atomic_and_audited(client):
    response = client.post(
        "/contracts/bulk-actions",
        json={"contractIds": ["CTR-001", "CTR-002"], "action": "archive"},
    )

    assert response.status_code == 200
    assert response.json()["affected"] == 2
    assert client.get("/contracts/CTR-001").status_code == 404
    events = client.get("/audit-events", params={"query": "Bulk Contract Archive"}).json()
    assert events["total"] == 2
