import math

import pytest

from app.algorithms.alignment import align_clause_sequences, analyze_version_diff, summarize_changes, word_diff, word_lcs
from app.algorithms.assignment import propose_assignments
from app.algorithms.coverage import greedy_set_cover
from app.algorithms.search import InvertedIndex, tokenize
from app.algorithms.similarity import (
    build_threshold_graph,
    connected_components,
    cosine_similarity,
    similarity_matrix,
    tfidf_vectors,
)


def test_inverted_index_normalizes_unicode_case_and_supports_boolean_queries():
    index = InvertedIndex({"C2": "Café retention notice", "C1": "CAFÉ breach notice", "C3": "retention only"})
    assert tokenize("  CAFÉ—Notice ") == ["café", "notice"]
    assert index.search("café notice", "AND") == ["C1", "C2"]
    assert index.search("breach retention", "OR") == ["C1", "C2", "C3"]
    assert index.search("", "AND") == []
    with pytest.raises(ValueError, match="mode"):
        index.search("notice", "XOR")


def test_dynamic_programming_alignment_and_word_lcs_are_deterministic():
    before = [
        {"key": "A", "text": "retain records for 180 days"},
        {"key": "B", "text": "notify promptly"},
    ]
    after = [
        {"key": "A", "text": "retain records for 90 days"},
        {"key": "C", "text": "permit annual audits"},
    ]
    assert word_lcs(before[0]["text"], after[0]["text"]) == ["retain", "records", "for", "days"]
    changes = align_clause_sequences(before, after)
    assert [(item["clauseKey"], item["kind"]) for item in changes] == [
        ("A", "Modified"),
        ("B", "Removed"),
        ("C", "Added"),
    ]
    assert align_clause_sequences([], []) == []

    analysis = analyze_version_diff(before, after)
    assert analysis["summary"] == {"added": 1, "removed": 1, "modified": 1, "unchanged": 0, "total": 3}
    assert analysis["changes"][0]["spans"] == [
        {"op": "equal", "words": ["retain", "records", "for"]},
        {"op": "insert", "words": ["90"]},
        {"op": "delete", "words": ["180"]},
        {"op": "equal", "words": ["days"]},
    ]
    assert word_diff("alpha beta", "alpha beta") == [{"op": "equal", "words": ["alpha", "beta"]}]
    assert summarize_changes([]) == {"added": 0, "removed": 0, "modified": 0, "unchanged": 0, "total": 0}


def test_version_analysis_reports_unchanged_clauses_and_is_deterministic():
    identical = [{"key": "A", "text": "unchanged clause text"}, {"key": "B", "text": "second clause"}]
    assert align_clause_sequences(identical, identical) == []
    analysis = analyze_version_diff(identical, identical)
    assert [(item["clauseKey"], item["kind"]) for item in analysis["changes"]] == [("A", "Unchanged"), ("B", "Unchanged")]
    assert analysis["summary"] == {"added": 0, "removed": 0, "modified": 0, "unchanged": 2, "total": 2}
    assert analyze_version_diff(identical, identical) == analyze_version_diff(identical, identical)

    added_only = analyze_version_diff([], [{"key": "N", "text": "brand new clause"}])
    assert [(item["clauseKey"], item["kind"]) for item in added_only["changes"]] == [("N", "Added")]
    removed_only = analyze_version_diff([{"key": "O", "text": "retired clause"}], [])
    assert [(item["clauseKey"], item["kind"]) for item in removed_only["changes"]] == [("O", "Removed")]
    assert analyze_version_diff([], [])["summary"]["total"] == 0


def test_tfidf_uses_documented_formula_and_cosine_handles_zero_vectors():
    vectors = tfidf_vectors({"A": "alpha beta", "B": "alpha gamma", "C": ""})
    expected_idf = math.log(4 / 2) + 1
    assert vectors["A"]["beta"] == pytest.approx(0.5 * expected_idf)
    assert cosine_similarity(vectors["A"], vectors["B"]) > 0
    assert cosine_similarity(vectors["A"], vectors["A"]) == pytest.approx(1)
    assert cosine_similarity(vectors["A"], vectors["C"]) == 0
    assert tfidf_vectors({}) == {}


def test_threshold_graph_and_dfs_components_validate_threshold_and_keep_isolates():
    ids = ["C", "A", "B"]
    similarities = [[1, 0.2, 0.8], [0.2, 1, 0.7], [0.8, 0.7, 1]]
    graph, edges = build_threshold_graph(ids, similarities, 0.75)
    assert edges == [{"source": "B", "target": "C", "score": 0.8}]
    assert connected_components(graph) == [["A"], ["B", "C"]]
    with pytest.raises(ValueError, match="threshold"):
        build_threshold_graph(ids, similarities, 1.01)


def test_greedy_set_cover_uses_clause_id_ties_and_reports_uncovered():
    result = greedy_set_cover({"O1", "O2", "O3"}, {"C2": {"O1", "O2"}, "C1": {"O1", "O2"}, "C3": {"O3"}})
    assert result["selected"] == ["C1", "C3"]
    assert result["covered"] == ["O1", "O2", "O3"]
    assert result["uncovered"] == []
    assert result["coverage_status"] == "Complete Coverage"
    assert result["clause_coverage"] == {"C1": ["O1", "O2"], "C2": ["O1", "O2"], "C3": ["O3"]}
    assert greedy_set_cover({"O1", "O2", "O3"}, {"C2": {"O1", "O2"}, "C1": {"O1", "O2"}, "C3": {"O3"}}) == result

    empty = greedy_set_cover(set(), {"C1": {"O1"}})
    assert empty["selected"] == []
    assert empty["steps"] == []
    assert empty["coverage_status"] == "Complete Coverage"
    partial = greedy_set_cover({"O1", "O9"}, {"C1": {"O1"}})
    assert partial["uncovered"] == ["O9"]
    assert partial["coverage_status"] == "Partial Coverage"
    assert partial["steps"] == [{"step": 1, "clause_id": "C1", "newly_covered": ["O1"], "covered_count": 1,
                                 "uncovered_count": 1, "uncovered_after": ["O9"]}]


def test_greedy_set_cover_records_every_selection_step():
    result = greedy_set_cover(
        {"O1", "O2", "O3", "O4"},
        {"C1": {"O1", "O2"}, "C2": {"O2", "O3"}, "C3": {"O1", "O2", "O3", "O4"}, "C4": {"O4"}},
    )
    assert result["selected"] == ["C3"]
    assert result["steps"] == [{"step": 1, "clause_id": "C3", "newly_covered": ["O1", "O2", "O3", "O4"],
                                "covered_count": 4, "uncovered_count": 0, "uncovered_after": []}]

    overlapping = greedy_set_cover({"O1", "O2"}, {"C1": {"O1"}, "C2": {"O2"}})
    assert overlapping["selected"] == ["C1", "C2"]
    assert [step["newly_covered"] for step in overlapping["steps"]] == [["O1"], ["O2"]]
    assert [step["uncovered_count"] for step in overlapping["steps"]] == [1, 0]


def test_min_cost_max_flow_maximizes_count_then_cost_and_respects_capacity():
    tasks = [
        {"id": "T2", "requiredExpertise": ["Privacy"]},
        {"id": "T1", "requiredExpertise": ["Privacy"]},
        {"id": "T3", "requiredExpertise": ["Security"]},
        {"id": "T4", "requiredExpertise": ["Tax"]},
    ]
    reviewers = [
        {"id": "R2", "expertise": ["Privacy", "Security"], "capacity": 1, "workload": 0},
        {"id": "R1", "expertise": ["Privacy"], "capacity": 1, "workload": 0},
    ]
    result = propose_assignments(tasks, reviewers)
    assert result["assignedCount"] == 2
    assert [(item["contractId"], item["reviewerId"], item["cost"], item["confidence"])
            for item in result["assignments"]] == [
        ("T1", "R1", 0, "Strong fit"),
        ("T2", "R2", 0, "Strong fit"),
    ]
    assert result["unassignedContractIds"] == ["T3", "T4"]
    assert result["totalCost"] == 0
    assert propose_assignments(tasks, reviewers) == result
    assert propose_assignments([], reviewers)["assignedCount"] == 0


def test_min_cost_max_flow_explains_assignments_and_unassigned_contracts():
    tasks = [{"id": "T1", "requiredExpertise": ["Privacy"]}, {"id": "T2", "requiredExpertise": ["Tax"]}]
    reviewers = [{"id": "R1", "expertise": ["Privacy"], "capacity": 1, "workload": 0}]
    result = propose_assignments(tasks, reviewers)
    assert result["assignments"][0]["explanation"] == (
        "Matched expertise Privacy; workload 0 of 1; cost 0 = 0 (workload 0 x 10) + 0 (expertise gap 0 x 100)"
    )
    assert result["unassigned"] == [
        {"contractId": "T2", "reason": "No active reviewer covers the required expertise: Tax"},
    ]
    assert result["reviewerLoads"] == [{"reviewerId": "R1", "capacity": 1, "existingWorkload": 0,
                                        "proposedCount": 1, "projectedLoad": 1, "remainingCapacity": 0}]
    assert result["eligiblePairs"] == 1


def test_min_cost_max_flow_respects_capacity_and_prefers_the_cheaper_reviewer():
    tasks = [{"id": "T1", "requiredExpertise": ["Privacy"]}]
    reviewers = [
        {"id": "R1", "expertise": ["Privacy"], "capacity": 1, "workload": 1},
        {"id": "R2", "expertise": ["Privacy", "Security"], "capacity": 3, "workload": 0},
    ]
    result = propose_assignments(tasks, reviewers)
    assert result["assignedCount"] == 1
    # R1 has no remaining capacity (workload == capacity), so the flow must use R2,
    # which is also the cheaper reviewer because cost scales with workload.
    assert result["assignments"][0]["reviewerId"] == "R2"
    assert result["assignments"][0]["confidence"] == "Strong fit"
    assert result["assignments"][0]["cost"] == 0
    assert result["reviewerLoads"][0] == {"reviewerId": "R1", "capacity": 1, "existingWorkload": 1,
                                         "proposedCount": 0, "projectedLoad": 1, "remainingCapacity": 0}

    saturated = propose_assignments(tasks, [{"id": "R1", "expertise": ["Privacy"], "capacity": 0, "workload": 0}])
    assert saturated["assignments"] == []
    assert saturated["assignedCount"] == 0
    assert saturated["unassigned"] == [
        {"contractId": "T1", "reason": "All 1 eligible reviewer(s) are already at capacity"},
    ]

    gap = propose_assignments([{"id": "T1", "requiredExpertise": ["Privacy", "Security"]}],
                              [{"id": "R1", "expertise": ["Privacy"], "capacity": 1, "workload": 0}])
    assert gap["assignments"][0]["confidence"] == "Good fit"
    assert gap["assignments"][0]["cost"] == 100


def test_min_cost_max_flow_assigns_multiple_contracts_to_multiple_reviewers_deterministically():
    tasks = [{"id": f"T{index}", "requiredExpertise": ["Privacy"]} for index in range(1, 5)]
    reviewers = [{"id": f"R{index}", "expertise": ["Privacy"], "capacity": 2, "workload": 0} for index in range(1, 3)]
    result = propose_assignments(tasks, reviewers)
    assert result["assignedCount"] == 4
    # Every pair costs 0, so the solver maximises flow and spreads the work evenly.
    assert result["assignments"] == [
        {"contractId": "T1", "reviewerId": "R1", "cost": 0, "confidence": "Strong fit",
         "explanation": "Matched expertise Privacy; workload 0 of 2; cost 0 = 0 (workload 0 x 10) + 0 (expertise gap 0 x 100)"},
        {"contractId": "T2", "reviewerId": "R1", "cost": 0, "confidence": "Strong fit",
         "explanation": "Matched expertise Privacy; workload 0 of 2; cost 0 = 0 (workload 0 x 10) + 0 (expertise gap 0 x 100)"},
        {"contractId": "T3", "reviewerId": "R2", "cost": 0, "confidence": "Strong fit",
         "explanation": "Matched expertise Privacy; workload 0 of 2; cost 0 = 0 (workload 0 x 10) + 0 (expertise gap 0 x 100)"},
        {"contractId": "T4", "reviewerId": "R2", "cost": 0, "confidence": "Strong fit",
         "explanation": "Matched expertise Privacy; workload 0 of 2; cost 0 = 0 (workload 0 x 10) + 0 (expertise gap 0 x 100)"},
    ]
    assert result["unassignedContractIds"] == []
    assert [load["proposedCount"] for load in result["reviewerLoads"]] == [2, 2]
    assert propose_assignments(tasks, reviewers) == result


def test_inverted_index_stores_term_frequency_postings_and_document_frequency():
    index = InvertedIndex({"B": "alpha beta beta gamma", "A": "beta gamma", "C": "delta"})
    assert index.document_count() == 3
    assert index.term_count() == 4
    assert index.postings["beta"] == {"A": 1, "B": 2}
    assert index.postings_for("gamma") == {"A": 1, "B": 1}
    assert index.postings_for("absent") == {}
    assert index.document_frequency["beta"] == 2
    assert index.document_frequency["delta"] == 1
    assert index.document_frequency.get("absent") is None


def test_inverted_index_returns_matched_terms_and_is_deterministic():
    index = InvertedIndex({"B": "alpha beta beta gamma", "A": "beta gamma", "C": "delta"})
    assert index.search_with_terms("beta gamma", "AND") == [
        {"id": "A", "matched_terms": ["beta", "gamma"], "term_frequency": {"beta": 1, "gamma": 1}, "score": 2},
        {"id": "B", "matched_terms": ["beta", "gamma"], "term_frequency": {"beta": 2, "gamma": 1}, "score": 3},
    ]
    assert index.search_with_terms("alpha delta", "OR") == [
        {"id": "B", "matched_terms": ["alpha"], "term_frequency": {"alpha": 1}, "score": 1},
        {"id": "C", "matched_terms": ["delta"], "term_frequency": {"delta": 1}, "score": 1},
    ]
    assert index.search_with_terms("beta beta", "OR") == [
        {"id": "A", "matched_terms": ["beta"], "term_frequency": {"beta": 1}, "score": 1},
        {"id": "B", "matched_terms": ["beta"], "term_frequency": {"beta": 2}, "score": 2},
    ]
    assert index.search_with_terms("", "OR") == []
    assert index.search_with_terms("beta gamma", "AND") == index.search_with_terms("beta gamma", "AND")


def test_tfidf_similarity_and_clustering_are_deterministic_and_handle_empty_documents():
    documents = {
        "A": "privacy retention breach notice",
        "B": "privacy retention breach notice",
        "C": "payment settlement chargeback merchant",
        "D": "",
    }
    ids, matrix = similarity_matrix(documents)
    assert ids == ["A", "B", "C", "D"]
    assert matrix[0][1] == pytest.approx(1.0)
    assert matrix[0][2] == pytest.approx(0.0)
    assert matrix[3] == [0.0, 0.0, 0.0, 0.0]
    assert similarity_matrix(documents) == (ids, matrix)

    graph, edges = build_threshold_graph(ids, matrix, 0.5)
    assert edges == [{"source": "A", "target": "B", "score": 1.0}]
    assert connected_components(graph) == [["A", "B"], ["C"], ["D"]]

    loose_graph, loose_edges = build_threshold_graph(ids, matrix, 0.0)
    assert [(edge["source"], edge["target"]) for edge in loose_edges] == [
        ("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D"),
    ]
    assert connected_components(loose_graph) == [["A", "B", "C", "D"]]
    assert build_threshold_graph([], [], 0.5) == ({}, [])
    assert connected_components({}) == []


def test_clustering_orders_clusters_and_nodes_deterministically_across_runs():
    ids = ["D", "C", "B", "A"]
    similarities = [
        [1.0, 0.0, 0.9, 0.0],
        [0.0, 1.0, 0.0, 0.85],
        [0.9, 0.0, 1.0, 0.0],
        [0.0, 0.85, 0.0, 1.0],
    ]
    first = connected_components(build_threshold_graph(ids, similarities, 0.8)[0])
    second = connected_components(build_threshold_graph(ids, similarities, 0.8)[0])
    assert first == second == [["A", "C"], ["B", "D"]]
