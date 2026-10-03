from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database
from app import database, models
from app.main import create_app
from app.seed import database_counts, reset_and_seed


@pytest.fixture()
def client(tmp_path: Path):
    configure_database(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    reset_and_seed()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Actor-Id": "USR-001"})
        yield test_client


def test_seed_counts_are_deterministic(client):
    counts = database_counts()
    assert counts["contracts"] == 12
    assert counts["versions"] == 36
    assert counts["clauses"] == 276
    assert counts["obligations"] == 10
    assert counts["reviewers"] == 6
    reset_and_seed()
    assert database_counts() == counts


def test_health_dashboard_and_paginated_contract_filters(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    response = client.get("/contracts", params={"page": 1, "pageSize": 3, "department": "Legal"})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"items", "page", "pageSize", "total", "totalPages"}
    assert all(item["department"] == "Legal" for item in payload["items"])
    assert client.get("/dashboard/summary").json()["portfolio"]["totalContracts"] == 12


def test_contract_detail_clauses_and_not_found_error_shape(client):
    detail = client.get("/contracts/CTR-001")
    assert detail.status_code == 200
    assert detail.json()["currentVersion"] == "v3.2"
    assert len(detail.json()["versions"]) == 2
    clauses = client.get("/contracts/CTR-001/clauses").json()
    assert clauses["total"] == 8
    missing = client.get("/contracts/NOPE")
    assert missing.status_code == 404
    assert missing.json() == {"error": {"code": "not_found", "message": "Contract NOPE was not found"}}


def test_search_compare_similarity_and_coverage_validation(client):
    search = client.get("/clauses/search", params={"q": "retention notice", "mode": "OR", "pageSize": 5})
    assert search.status_code == 200
    assert search.json()["total"] > 0
    versions = client.get("/contracts/CTR-002").json()["versions"]
    compared = client.get(
        "/contracts/CTR-002/compare",
        params={"baseVersionId": versions[-1]["id"], "targetVersionId": versions[0]["id"]},
    )
    assert compared.status_code == 200
    assert compared.json()["contractId"] == "CTR-002"
    change_kinds = {change["kind"] for change in compared.json()["changes"]}
    assert {"Added", "Removed", "Modified"} <= change_kinds
    graph = client.get("/similarity-graph", params={"threshold": 0.75})
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) == 12
    assert len(graph.json()["components"]) > 1
    assert any(edge["score"] < 1 for edge in graph.json()["edges"])
    invalid = client.get("/similarity-graph", params={"threshold": 2})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    coverage = client.get("/compliance/coverage", params={"contractId": "CTR-001"})
    assert coverage.status_code == 200
    assert coverage.json()["total"] == 10


def test_approved_post_analysis_routes_and_review_aliases(client):
    versions = client.get("/contracts/CTR-002/versions", params={"pageSize": 2})
    assert versions.status_code == 200
    assert versions.json()["total"] == 3
    version_items = versions.json()["items"]
    search = client.post("/clause-search", json={"query": "retention", "mode": "AND", "pageSize": 5})
    assert search.status_code == 200
    assert search.json()["total"] > 0
    comparison = client.post("/version-comparisons", json={
        "contractId": "CTR-002", "baseVersionId": version_items[-1]["id"], "targetVersionId": version_items[0]["id"],
    })
    assert comparison.status_code == 200
    assert client.post("/similarity/graph", json={"threshold": 0.4}).status_code == 200
    assert client.post("/compliance/coverage", json={"contractId": "CTR-001"}).status_code == 200
    reviews = client.get("/reviews")
    assert reviews.status_code == 200
    review_id = reviews.json()["items"][1]["id"]
    assert client.patch(f"/reviews/{review_id}", json={"status": "In Review"}).status_code == 200


def test_assignment_confirmation_conflicts_capacity_and_writes_audit(client):
    reviewers = client.get("/reviewers", params={"expertise": "Privacy", "pageSize": 1})
    assert reviewers.status_code == 200
    assert reviewers.json()["total"] == 2
    assert len(reviewers.json()["items"]) == 1
    assert "Privacy" in reviewers.json()["items"][0]["expertise"]
    proposal = client.post("/reviewer-assignments/propose", json={"contractIds": ["CTR-001", "CTR-002"]})
    assert proposal.status_code == 200
    assignments = proposal.json()["assignments"]
    assert assignments
    confirmed = client.post("/reviewer-assignments/confirm", json={"assignments": assignments})
    assert confirmed.status_code == 201
    conflict = client.post("/reviewer-assignments/confirm", json={"assignments": assignments})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "assignment_conflict"
    events = client.get("/audit-events", params={"query": "Review Assigned"}).json()
    assert events["total"] == len(assignments)


def test_confirmation_rejects_reviewer_capacity_overflow(client):
    payload = {"assignments": [
        {"contractId": contract_id, "reviewerId": "REV-C", "cost": 0, "confidence": "Strong fit"}
        for contract_id in ["CTR-001", "CTR-002", "CTR-003"]
    ]}
    response = client.post("/reviewer-assignments/confirm", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "capacity_exceeded"


def test_confirmation_rejects_incompatible_reviewer(client):
    response = client.post("/reviewer-assignments/confirm", json={"assignments": [{
        "contractId": "CTR-002", "reviewerId": "REV-B", "cost": 0, "confidence": "Good fit",
    }]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "incompatible_assignment"


def test_review_status_decision_settings_persist_and_create_audit_events(client):
    queue = client.get("/review-queue").json()
    review_id = queue["items"][0]["id"]
    update = client.patch(f"/review-queue/{review_id}", json={"status": "In Review"})
    assert update.status_code == 200
    decision = client.post(
        f"/reviews/{review_id}/decision",
        json={"decision": "Approved", "notes": "Evidence verified", "decidedBy": "Compliance Reviewer"},
    )
    assert decision.status_code == 201
    decisions = client.get(f"/reviews/{review_id}/decisions")
    assert decisions.status_code == 200
    assert decisions.json()["total"] == 1
    assert decisions.json()["items"][0]["decision"] == "Approved"
    second = client.post(
        f"/reviews/{review_id}/decisions",
        json={"decision": "Rejected", "notes": "Duplicate", "decidedBy": "Compliance Reviewer"},
    )
    assert second.status_code == 409
    settings = client.put("/settings", json={"displayName": "A. Reviewer", "weeklySummary": False})
    assert settings.status_code == 200
    assert client.get("/settings").json()["displayName"] == "A. Reviewer"
    assert client.get("/audit-events", params={"query": "Review Decision"}).json()["total"] == 1


def test_invalid_payloads_use_structured_422(client):
    response = client.patch("/review-queue/RVW-001", json={"status": "Nonsense"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"]


def test_audit_events_are_append_only(client):
    with database.SessionLocal() as session:
        event = session.get(models.AuditEvent, "AUD-000001")
        event.action = "Tampered"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()


def test_clause_search_exposes_inverted_index_matched_terms(client):
    response = client.post("/clause-search", json={"query": "retention notice", "mode": "OR", "pageSize": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    for item in payload["items"]:
        assert item["matchedTerms"]
        assert set(item["matchedTerms"]) <= {"retention", "notice"}
        assert set(item["termFrequency"]) == set(item["matchedTerms"])
        assert all(count >= 1 for count in item["termFrequency"].values())
    assert payload["items"][0]["match"] == "retention notice"

    conjunction = client.post("/clause-search", json={"query": "retention notice", "mode": "AND", "pageSize": 5})
    assert conjunction.status_code == 200
    assert conjunction.json()["total"] <= payload["total"]
    assert client.post("/clause-search", json={"query": "zzzznotpresent", "pageSize": 5}).json()["total"] == 0
    assert client.post("/clause-search", json={"query": "   ", "pageSize": 5}).status_code == 422
    assert client.get("/clauses/search", params={"q": "   "}).status_code == 422


def test_version_comparison_returns_summary_counts_and_word_level_spans(client):
    versions = client.get("/contracts/CTR-002").json()["versions"]
    response = client.post("/version-comparisons", json={
        "contractId": "CTR-002", "baseVersionId": versions[-1]["id"], "targetVersionId": versions[0]["id"],
    })
    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert set(summary) == {"added", "removed", "modified", "unchanged", "total"}
    assert summary["total"] == sum(summary[key] for key in ("added", "removed", "modified", "unchanged"))
    assert summary["total"] == len(payload["changes"])

    kinds = [change["kind"] for change in payload["changes"]]
    assert {"Added", "Removed", "Modified"} <= set(kinds)
    modified = [change for change in payload["changes"] if change["kind"] == "Modified"][0]
    assert modified["commonWords"]
    assert modified["spans"]
    assert {span["op"] for span in modified["spans"]} <= {"equal", "insert", "delete"}
    assert any(span["op"] in {"insert", "delete"} for span in modified["spans"])

    identical = client.post("/version-comparisons", json={
        "contractId": "CTR-002", "baseVersionId": versions[0]["id"], "targetVersionId": versions[0]["id"],
    })
    assert identical.status_code == 200
    identical_summary = identical.json()["summary"]
    assert identical_summary["added"] == identical_summary["removed"] == identical_summary["modified"] == 0
    assert identical_summary["unchanged"] == identical_summary["total"] > 0
    assert {change["kind"] for change in identical.json()["changes"]} == {"Unchanged"}


def test_coverage_endpoint_returns_greedy_selection_steps(client):
    response = client.post("/compliance/coverage", json={"contractId": "CTR-001"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["method"] == "Greedy Set Cover approximation (not guaranteed optimal)"
    assert payload["total"] == 10
    assert set(payload["selectedClauses"]) <= set(payload["clauseCoverage"])
    assert payload["steps"]
    assert [step["step"] for step in payload["steps"]] == list(range(1, len(payload["steps"]) + 1))
    covered_so_far: list[str] = []
    for index, step in enumerate(payload["steps"]):
        assert step["clauseId"] in payload["selectedClauses"]
        assert step["newlyCovered"]
        assert step["coveredCount"] == len(step["newlyCovered"])
        covered_so_far.extend(step["newlyCovered"])
        assert step["uncoveredCount"] + len(covered_so_far) == payload["total"]
        if index < len(payload["steps"]) - 1:
            assert step["uncoveredCount"] > 0
    # Greedy never re-selects an obligation, so the step log explains full coverage exactly.
    assert len(set(covered_so_far)) == len(covered_so_far) == payload["covered"]
    assert payload["status"] == ("Complete Coverage" if not payload["uncoveredObligationIds"] else "Partial Coverage")


def test_similarity_graph_reports_threshold_dependent_edges_and_isolates(client):
    high = client.post("/similarity/graph", json={"threshold": 0.9}).json()
    low = client.post("/similarity/graph", json={"threshold": 0.05}).json()
    assert high["threshold"] == 0.9
    assert high["comparedPairs"] == 12 * 11 // 2 == low["comparedPairs"]
    assert len(low["edges"]) >= len(high["edges"])
    assert len(low["isolatedContractIds"]) <= len(high["isolatedContractIds"])
    assert all(edge["score"] >= 0.9 for edge in high["edges"])
    assert all(edge["score"] >= 0.05 for edge in low["edges"])
    assert {node["id"] for node in low["nodes"]} == {f"CTR-{index:03d}" for index in range(1, 13)}
    assert low["isolatedContractIds"] == sorted(low["isolatedContractIds"])


def test_assignment_proposal_returns_explanations_loads_and_unassigned_reasons(client):
    response = client.post("/reviewer-assignments/propose", json={"contractIds": ["CTR-001", "CTR-002"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["objective"] == "maximize valid assignments first, then minimize workload/expertise cost"
    assert set(payload["reviewerLoads"][0]) == {"reviewerId", "capacity", "existingWorkload", "proposedCount",
                                               "projectedLoad", "remainingCapacity"}
    for assignment in payload["assignments"]:
        assert "Matched expertise" in assignment["explanation"]
        assert "cost" in assignment["explanation"]
        assert assignment["confidence"] in {"Strong fit", "Good fit"}
    assert len(payload["reviewerLoads"]) == 6
    assert payload["eligiblePairs"] >= payload["assignedCount"]
    assert payload["assignedCount"] == len(payload["assignments"])
    assert sorted(item["contractId"] for item in payload["unassigned"]) == sorted(payload["unassignedContractIds"])
    for item in payload["unassigned"]:
        assert item["reason"].startswith(("No active reviewer", "All "))
    assert client.post("/reviewer-assignments/propose", json={"contractIds": ["CTR-999"]}).status_code == 404
