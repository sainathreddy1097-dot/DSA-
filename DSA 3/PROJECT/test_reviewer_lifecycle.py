from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app.main import ASSIGNMENT_OBJECTIVE, create_app
from app.seed import reset_and_seed


@pytest.fixture()
def client(tmp_path: Path):
    configure_database(f"sqlite:///{(tmp_path / 'reviewers.db').as_posix()}")
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def test_create_and_update_reviewer_expertise(client):
    created = client.post(
        "/reviewers",
        json={
            "name": "Asha Menon",
            "role": "Privacy Counsel",
            "capacity": 6,
            "expertise": ["Privacy", "Security"],
        },
    )
    assert created.status_code == 201
    body = created.json()

    updated = client.patch(
        f"/reviewers/{body['id']}",
        json={
            "role": "Senior Privacy Counsel",
            "expertise": ["Privacy", "Legal"],
            "updatedAt": body["updatedAt"],
        },
    )

    assert updated.status_code == 200
    assert updated.json()["role"] == "Senior Privacy Counsel"
    assert updated.json()["expertise"] == ["Legal", "Privacy"]


def test_capacity_cannot_drop_below_active_work(client):
    reviewer = next(item for item in client.get("/reviewers?pageSize=100").json()["items"] if item["id"] == "REV-A")

    response = client.patch(
        "/reviewers/REV-A",
        json={"capacity": 1, "updatedAt": reviewer["updatedAt"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "capacity_conflict"


def test_deactivated_reviewer_is_not_proposed(client):
    deactivated = client.post("/reviewers/REV-A/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    proposal = client.post(
        "/reviewer-assignments/propose",
        json={"contractIds": ["CTR-002"]},
    ).json()

    assert all(item["reviewerId"] != "REV-A" for item in proposal["assignments"])


def test_reviewer_with_confirmed_assignment_cannot_be_deactivated(client):
    proposal = client.post(
        "/reviewer-assignments/propose",
        json={"contractIds": ["CTR-002"]},
    ).json()["assignments"]
    assert proposal
    client.post("/reviewer-assignments/confirm", json={"assignments": proposal})

    response = client.post(f"/reviewers/{proposal[0]['reviewerId']}/deactivate")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "active_assignment_conflict"


def test_assignment_objective_remains_exact(client):
    schema = client.get("/openapi.json").json()
    description = schema["paths"]["/reviewer-assignments/propose"]["post"]["description"]

    assert ASSIGNMENT_OBJECTIVE == "maximize valid assignments first, then minimize workload/expertise cost"
    assert ASSIGNMENT_OBJECTIVE in description
