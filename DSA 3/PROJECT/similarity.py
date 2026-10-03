"""TF-IDF, cosine similarity, threshold graphs, and DFS components.

For ``N`` documents containing ``T`` total tokens and vocabulary size ``V``:

* TF-IDF construction is ``O(T)`` time and ``O(NV)`` worst-case space.
* One sparse cosine comparison is ``O(min(V_left, V_right))`` for the dot
  product plus both vector-size norm scans.
* The full matrix performs ``N²`` comparisons, giving ``O(N²V)`` worst-case
  time and ``O(N²)`` matrix space.
* Threshold-graph construction scans the upper triangle in ``O(N²)`` time;
  iterative DFS is ``O(N + E)`` time and space for ``E`` retained edges.

Sorted document IDs, edges, neighbors, and components keep output stable.
"""

from collections import Counter
import math

from .search import tokenize


def tfidf_vectors(documents: dict[str, str]) -> dict[str, dict[str, float]]:
    if not documents:
        return {}
    tokenized = {doc_id: tokenize(text) for doc_id, text in documents.items()}
    document_frequency: Counter[str] = Counter()
    for terms in tokenized.values():
        document_frequency.update(set(terms))
    count = len(documents)
    vectors: dict[str, dict[str, float]] = {}
    for doc_id in sorted(documents):
        terms = tokenized[doc_id]
        frequencies = Counter(terms)
        vectors[doc_id] = {
            term: (frequency / len(terms)) * (math.log((count + 1) / (document_frequency[term] + 1)) + 1)
            for term, frequency in frequencies.items()
        } if terms else {}
    return vectors


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    return dot / (left_norm * right_norm)


def similarity_matrix(documents: dict[str, str]) -> tuple[list[str], list[list[float]]]:
    ids = sorted(documents)
    vectors = tfidf_vectors(documents)
    matrix = [[cosine_similarity(vectors[left], vectors[right]) for right in ids] for left in ids]
    return ids, matrix


def build_threshold_graph(ids: list[str], similarities: list[list[float]], threshold: float):
    if threshold < 0 or threshold > 1:
        raise ValueError("threshold must be between 0 and 1")
    if len(similarities) != len(ids) or any(len(row) != len(ids) for row in similarities):
        raise ValueError("similarity matrix dimensions must match ids")
    graph = {node_id: set() for node_id in ids}
    edges: list[dict] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            score = similarities[i][j]
            if score >= threshold:
                source, target = sorted((ids[i], ids[j]))
                graph[source].add(target)
                graph[target].add(source)
                edges.append({"source": source, "target": target, "score": round(score, 6)})
    return graph, sorted(edges, key=lambda edge: (edge["source"], edge["target"]))


def connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    visited: set[str] = set()
    components: list[list[str]] = []
    for start in sorted(graph):
        if start in visited:
            continue
        stack, component = [start], []
        visited.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in sorted(graph[node], reverse=True):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return components
