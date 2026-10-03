import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app.main import create_app
from app.seed import reset_and_seed


@pytest.fixture()
def client(tmp_path: Path):
    configure_database(f"sqlite:///{(tmp_path / 'dataset-import.db').as_posix()}")
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def test_import_dataset_creates_contracts_and_optional_clauses(client):
    dataset = [{
        "name": "CUAD Sample Purchase Agreement", "type": "Purchase Agreement", "filingDate": "2025-03-01",
        "counterparty": "Example Seller", "clauses": [{"title": "Governing Law", "text": "This agreement is governed by Delaware law."}],
    }, {"title": "SEC Exhibit Services Agreement", "contract_type": "Services", "effective_date": "2025-04-01", "expiry_date": "2026-04-01"}]

    response = client.post("/contracts/import-dataset", files={"file": ("contracts.json", json.dumps(dataset), "application/json")})

    assert response.status_code == 201
    payload = response.json()
    assert payload["imported"] == 2
    first = client.get(f"/contracts/{payload['contractIds'][0]}").json()
    assert first["currentVersion"] == "v1.0"
    assert client.get(f"/contracts/{payload['contractIds'][0]}/clauses").json()["total"] == 1


def test_import_dataset_rejects_invalid_rows_without_partial_writes(client):
    response = client.post("/contracts/import-dataset", files={"file": ("contracts.csv", "name,effectiveDate,expiryDate\nValid,2025-01-01,2026-01-01\n,2025-01-01,2026-01-01\n", "text/csv")})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_dataset"
    assert client.get("/contracts", params={"query": "Valid"}).json()["total"] == 0