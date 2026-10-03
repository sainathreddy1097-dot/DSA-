# Handwritten algorithms

The backend intentionally uses no algorithm libraries. Results are deterministic decision-support output from the seeded local dataset; they are not measured accuracy, legal advice, or compliance certification.

## Inverted-index search

`app/algorithms/search.py` normalizes strings with Unicode NFKC, applies Unicode-aware `casefold`, tokenizes words, and creates term-to-document posting sets. AND queries intersect postings; OR queries unite them. Results are sorted by clause ID. Index construction is `O(T)` for `T` input tokens; a query is proportional to the postings it combines.

## Clause and word alignment

`app/algorithms/alignment.py` builds a dynamic-programming LCS table over stable clause keys, then emits added, removed, or modified records in sequence order. Modified clauses run a second word-token LCS. Space and time are `O(nm)` for sequence lengths `n` and `m` (and separately for the two word sequences).

## TF-IDF and cosine similarity

`app/algorithms/similarity.py` computes term frequency as `term count / document token count` and inverse document frequency exactly as:

```text
log((N + 1) / (df + 1)) + 1
```

Cosine similarity is the sparse dot product divided by both vector norms; a zero vector has similarity zero. Pairwise comparison of `N` documents is `O(N²V)` in the worst case for vocabulary size `V`.

## Threshold graph and DFS components

Each document is a node. An undirected edge is included when its cosine score is at least the validated threshold in `[0, 1]`. Connected components use an explicit depth-first-search stack and sorted traversal. Graph construction is `O(N²)` and traversal is `O(V + E)`.

## Greedy set cover

At each step, `app/algorithms/coverage.py` selects the clause covering the most currently uncovered obligations. Equal coverage gains are resolved by lexicographically smaller clause ID. The response explicitly reports obligations no candidate can cover. With `C` clauses and `O` obligations, the straightforward implementation is `O(CO²)` in the worst case.

## Reviewer assignment

`app/algorithms/assignment.py` builds a residual flow network and runs successive shortest augmenting paths. Source-to-contract and contract-to-reviewer edges have capacity one; reviewer-to-sink capacity is remaining workload capacity. Edges exist only for expertise-valid candidates. Costs penalize workload first and missing expertise second, with sorted node construction for reproducible ties.

The documented objective is exactly: **maximize valid assignments first, then minimize workload/expertise cost**.

The augmenting process continues until no source-to-sink path exists, which maximizes flow before comparing total cost. No third-party graph, optimization, search, or text-analysis package is used.
