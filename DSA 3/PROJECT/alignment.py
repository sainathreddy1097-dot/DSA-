"""Dynamic-programming clause alignment and word-level LCS.

Problem
    Given the ordered clause sequences of two contract versions, identify which
    clauses were Added, Removed, Modified or left Unchanged.

Identity across versions
    Every clause carries a stable ``clause_key`` preserved between versions of
    the same contract, so correspondence never depends on position or on fuzzy
    text matching.

Data structures
    - ``table``: an (n+1) x (m+1) integer DP table holding the length of the
      longest common subsequence of clause keys. It drives the Added/Removed
      decisions during the alignment walk.
    - A word-level (p+1) x (q+1) DP table for each modified clause pair.

Algorithms
    - Clause alignment: LCS over clause keys, then a backtrack that walks both
      sequences in order.
    - Word comparison: LCS over tokens, backtracked into ordered diff spans of
      ``equal`` / ``insert`` / ``delete`` operations.

Complexity
    - ``align_clause_sequences``: O(n * m) time and O(n * m) space for the DP
      table, plus O(p * q) time and space per modified clause pair.
    - ``word_lcs`` / ``word_diff``: O(p * q) time and O(p * q) space where p and
      q are the token counts of the two clause texts.

Determinism
    Output order follows the walk over both sequences, and every tie in the
    backtrack prefers the same branch, so identical inputs always produce
    byte-equivalent serialised output.
"""

from .search import tokenize


def word_lcs(before: str, after: str) -> list[str]:
    """Return the longest common subsequence of the two texts' tokens."""
    left, right = tokenize(before), tokenize(after)
    table = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i in range(1, len(left) + 1):
        for j in range(1, len(right) + 1):
            if left[i - 1] == right[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
            else:
                table[i][j] = max(table[i - 1][j], table[i][j - 1])
    result: list[str] = []
    i, j = len(left), len(right)
    while i and j:
        if left[i - 1] == right[j - 1]:
            result.append(left[i - 1])
            i -= 1
            j -= 1
        elif table[i - 1][j] >= table[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return list(reversed(result))


def word_diff(before: str, after: str) -> list[dict]:
    """Return ordered word-level diff spans derived from the LCS table.

    Each span is ``{"op": "equal"|"insert"|"delete", "words": [...]}`` where
    ``insert`` words exist only in ``after`` and ``delete`` words only in
    ``before``. Consecutive spans with the same operation are merged, giving a
    stable representation of the change.
    """
    left, right = tokenize(before), tokenize(after)
    table = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i in range(1, len(left) + 1):
        for j in range(1, len(right) + 1):
            if left[i - 1] == right[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
            else:
                table[i][j] = max(table[i - 1][j], table[i][j - 1])

    operations: list[tuple[str, str]] = []
    i, j = len(left), len(right)
    while i and j:
        if left[i - 1] == right[j - 1]:
            operations.append(("equal", left[i - 1]))
            i -= 1
            j -= 1
        elif table[i - 1][j] >= table[i][j - 1]:
            operations.append(("delete", left[i - 1]))
            i -= 1
        else:
            operations.append(("insert", right[j - 1]))
            j -= 1
    while i:
        operations.append(("delete", left[i - 1]))
        i -= 1
    while j:
        operations.append(("insert", right[j - 1]))
        j -= 1

    spans: list[dict] = []
    for op, word in reversed(operations):
        if spans and spans[-1]["op"] == op:
            spans[-1]["words"].append(word)
        else:
            spans.append({"op": op, "words": [word]})
    return spans


def summarize_changes(changes: list[dict]) -> dict:
    """Count clause changes per kind in a fixed, deterministic key order."""
    summary = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    for change in changes:
        key = str(change["kind"]).lower()
        if key in summary:
            summary[key] += 1
    summary["total"] = len(changes)
    return summary


def align_clause_sequences(before: list[dict], after: list[dict], include_unchanged: bool = False) -> list[dict]:
    """Align stable clause keys using an LCS dynamic-programming table.

    Set ``include_unchanged=True`` to also emit ``Unchanged`` entries, which the
    version-analysis API needs for its summary counts.
    """
    n, m = len(before), len(after)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if before[i]["key"] == after[j]["key"]:
                table[i][j] = 1 + table[i + 1][j + 1]
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])

    changes: list[dict] = []
    i = j = 0
    while i < n or j < m:
        if i < n and j < m and before[i]["key"] == after[j]["key"]:
            if before[i]["text"] != after[j]["text"]:
                changes.append({
                    "clauseKey": before[i]["key"],
                    "kind": "Modified",
                    "before": before[i]["text"],
                    "after": after[j]["text"],
                    "commonWords": word_lcs(before[i]["text"], after[j]["text"]),
                    "spans": word_diff(before[i]["text"], after[j]["text"]),
                })
            elif include_unchanged:
                changes.append({
                    "clauseKey": before[i]["key"],
                    "kind": "Unchanged",
                    "before": before[i]["text"],
                    "after": after[j]["text"],
                })
            i += 1
            j += 1
        elif i < n and (j == m or table[i + 1][j] >= table[i][j + 1]):
            changes.append({"clauseKey": before[i]["key"], "kind": "Removed", "before": before[i]["text"]})
            i += 1
        else:
            changes.append({"clauseKey": after[j]["key"], "kind": "Added", "after": after[j]["text"]})
            j += 1
    return changes


def analyze_version_diff(before: list[dict], after: list[dict]) -> dict:
    """Return the complete version-analysis result for two clause sequences."""
    changes = align_clause_sequences(before, after, include_unchanged=True)
    return {"changes": changes, "summary": summarize_changes(changes)}
