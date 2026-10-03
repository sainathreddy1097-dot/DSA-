from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app.main import create_app
from app.seed import reset_and_seed


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    configure_database(f"sqlite:///{(tmp_path / 'content.db').as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def upload_version(client, label: str, content: bytes):
    return client.post(
        "/contracts/CTR-001/versions/upload",
        data={"label": label, "effectiveDate": "2026-10-01", "author": "Legal Ops"},
        files={"file": ("agreement.txt", content, "text/plain")},
    )


def test_upload_creates_version_and_segmented_clauses(client):
    response = upload_version(
        client,
        "v4.0",
        b"1. Scope\nServices apply.\n2. Fees\nFees apply.",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sourceFilename"] == "agreement.txt"
    assert [clause["title"] for clause in body["clauses"]] == ["Scope", "Fees"]
    assert client.get("/contracts/CTR-001").json()["currentVersion"] == "v4.0"


def test_duplicate_upload_for_contract_returns_conflict(client):
    document = b"1. Scope\nServices.\n2. Fees\nFees apply."
    assert upload_version(client, "v4.0", document).status_code == 201

    duplicate = upload_version(client, "v4.1", document)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_document"


def test_structured_version_creation_is_persisted(client):
    response = client.post(
        "/contracts/CTR-001/versions",
        json={
            "label": "v4.2",
            "effectiveDate": "2026-10-02",
            "author": "Legal Ops",
            "note": "Manual version",
            "clauses": [
                {"title": "Scope", "text": "Services apply.", "status": "Compliant", "tier": "Preferred"}
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["clauses"][0]["clauseKey"] == "CTR-001-C01"


def test_new_contract_without_a_version_has_an_empty_clause_page(client):
    created = client.post(
        "/contracts",
        json={
            "name": "Unversioned Agreement",
            "type": "Services",
            "owner": "Legal Operations",
            "department": "Legal",
            "compliance": "Needs Review",
            "reviewStatus": "Pending",
            "effectiveDate": "2026-10-01",
            "expiryDate": "2027-10-01",
            "risk": "Medium",
        },
    ).json()

    response = client.get(f"/contracts/{created['id']}/clauses")

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "pageSize": 50, "total": 0, "totalPages": 0}


def test_replace_clause_obligations_is_atomic(client):
    clause_id = client.get("/contracts/CTR-001/clauses").json()["items"][0]["id"]

    response = client.put(
        f"/clauses/{clause_id}/obligations",
        json={"obligationIds": ["OBL-01", "OBL-02"]},
    )

    assert response.status_code == 200
    assert response.json()["obligationIds"] == ["OBL-01", "OBL-02"]
    failed = client.put(
        f"/clauses/{clause_id}/obligations",
        json={"obligationIds": ["OBL-01", "MISSING"]},
    )
    assert failed.status_code == 404
    assert client.get(f"/clauses/{clause_id}/obligations").json()["obligationIds"] == ["OBL-01", "OBL-02"]


def test_archived_clause_disappears_from_default_search(client):
    clause = client.get("/contracts/CTR-001/clauses").json()["items"][0]

    archived = client.post(f"/clauses/{clause['id']}/archive")

    assert archived.status_code == 200
    current_ids = {
        item["id"] for item in client.get("/contracts/CTR-001/clauses?pageSize=100").json()["items"]
    }
    assert clause["id"] not in current_ids
    search_ids = {
        item["id"]
        for item in client.post(
            "/clause-search",
            json={"query": "personal information", "mode": "AND", "page": 1, "pageSize": 100},
        ).json()["items"]
    }
    assert clause["id"] not in search_ids


def test_archived_clause_can_be_listed_and_restored(client):
    clause = client.get("/contracts/CTR-001/clauses").json()["items"][0]
    assert client.post(f"/clauses/{clause['id']}/archive").status_code == 200

    archived_items = client.get(
        "/contracts/CTR-001/clauses?pageSize=100&includeArchived=true"
    ).json()["items"]
    assert clause["id"] in {item["id"] for item in archived_items}

    restored = client.post(f"/clauses/{clause['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archivedAt"] is None


def test_obligation_create_update_and_archive(client):
    created = client.post(
        "/obligations",
        json={"name": "Incident escalation", "category": "Security", "description": "Escalate incidents."},
    )
    assert created.status_code == 201
    body = created.json()

    updated = client.patch(
        f"/obligations/{body['id']}",
        json={"description": "Escalate confirmed incidents.", "updatedAt": body["updatedAt"]},
    )
    assert updated.status_code == 200
    archived = client.post(f"/obligations/{body['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["archivedAt"] is not None


def test_archived_obligation_can_be_restored(client):
    created = client.post(
        "/obligations",
        json={"name": "Restorable control", "category": "Security", "description": "Restore this control."},
    ).json()
    assert client.post(f"/obligations/{created['id']}/archive").status_code == 200

    restored = client.post(f"/obligations/{created['id']}/restore")

    assert restored.status_code == 200
    assert restored.json()["archivedAt"] is None
