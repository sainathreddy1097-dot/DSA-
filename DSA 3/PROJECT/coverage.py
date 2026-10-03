"""Deterministic handwritten Greedy Set Cover.

Problem
    Choose a small set of candidate clauses whose obligation mappings cover
    every required regulatory obligation.

Universe
    The ids of all required regulatory obligations.

Candidate sets
    ``clause_key -> set of obligation ids that clause covers``.

Data structures
    - ``uncovered``: a Python ``set`` of obligation ids, giving O(1) membership
      tests and O(|gain|) removal through set difference.
    - ``candidates``: a dict read once and pre-sorted by clause id so that
      iteration order (and therefore tie-breaking) is reproducible.
    - ``steps``: an append-only list recording every greedy decision so the
      result can be explained during a viva.

Algorithm
    1. Score every candidate clause by ``|coverage(clause) & uncovered|``.
    2. Select the clause with the largest positive score.
    3. Ties are broken by the smallest clause id (deterministic).
    4. Record the step, then subtract the newly covered obligations.
    5. Repeat until the universe is covered or no clause adds new coverage.

Complexity
    Let C be the number of candidate clauses, U the number of obligations and
    K = min(C, U) the maximum number of greedy iterations.

    - time:  O(C log C) to sort candidates, then O(C * K) for the selection
      scans, i.e. O(C log C + C * K). Because U bounds the iterations, the
      practical worst case is O(C * U).
    - space: O(C + U) for the candidate map, the uncovered set and the steps.

Limitation
    This is a GREEDY APPROXIMATION. It is not guaranteed to return the globally
    minimum set cover, and no optimality claim is made anywhere in the project.
"""


def greedy_set_cover(universe: set[str], candidates: dict[str, set[str]]) -> dict:
    """Greedily cover ``universe`` using the clause sets in ``candidates``.

    Returns a deterministic dict with the keys ``selected``, ``covered``,
    ``uncovered``, ``steps``, ``clause_coverage`` and ``coverage_status``.
    """
    uncovered = set(universe)
    ordered_ids = sorted(candidates)
    selected: list[str] = []
    steps: list[dict] = []
    while uncovered:
        best_id: str | None = None
        best_gain = 0
        best_new: set[str] = set()
        for clause_id in ordered_ids:
            gain_set = set(candidates[clause_id]) & uncovered
            gain = len(gain_set)
            if gain > best_gain:
                best_id = clause_id
                best_gain = gain
                best_new = gain_set
        if best_id is None:
            break
        selected.append(best_id)
        uncovered -= best_new
        steps.append({
            "step": len(steps) + 1,
            "clause_id": best_id,
            "newly_covered": sorted(best_new),
            "covered_count": len(best_new),
            "uncovered_count": len(uncovered),
            "uncovered_after": sorted(uncovered),
        })
    return {
        "selected": selected,
        "covered": sorted(set(universe) - uncovered),
        "uncovered": sorted(uncovered),
        "steps": steps,
        "clause_coverage": {clause_id: sorted(values) for clause_id, values in sorted(candidates.items())},
        "coverage_status": "Complete Coverage" if not uncovered else "Partial Coverage",
    }
