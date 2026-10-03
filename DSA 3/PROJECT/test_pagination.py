from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app.main import create_app
from app.seed import reset_and_seed


@pytest.fixture()
def client(tmp_path: Path):
    configure_database(f"sqlite:///{(tmp_path / 'pagination.db').as_posix()}")
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def test_contract_pages_are_stable(client):
    first = client.get("/contracts?page=1&pageSize=5&sort=name&direction=asc").json()
    second = client.get("/contracts?page=2&pageSize=5&sort=name&direction=asc").json()

    assert first["total"] == 12
    assert first["totalPages"] == 3
    assert len(first["items"]) == 5
    assert len(second["items"]) == 5
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )
    assert [item["name"] for item in first["items"]] == sorted(
        item["name"] for item in first["items"]
    )


def test_contract_filters_apply_before_counting(client):
    response = client.get(
        "/contracts",
        params={"query": "agreement", "compliance": "Needs Review", "pageSize": 2},
    ).json()

    assert response["total"] >= len(response["items"])
    assert response["pageSize"] == 2
    assert all(item["compliance"] == "Needs Review" for item in response["items"])
    assert all("agreement" in item["name"].lower() for item in response["items"])


def test_archived_contracts_require_explicit_filter(client):
    client.post("/contracts/CTR-001/archive")

    default_ids = {item["id"] for item in client.get("/contracts?pageSize=100").json()["items"]}
    included_ids = {
        item["id"]
        for item in client.get("/contracts?pageSize=100&includeArchived=true").json()["items"]
    }

    assert "CTR-001" not in default_ids
    assert "CTR-001" in included_ids


@pytest.mark.parametrize(
    "query",
    ["pageSize=101", "page=0", "sort=unknown", "direction=sideways"],
)
def test_invalid_pagination_parameters_return_structured_422(client, query):
    response = client.get(f"/contracts?{query}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
