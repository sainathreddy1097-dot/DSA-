"""Unicode-aware inverted-index search without search libraries.

Handwritten inverted index with:
- NFKC normalization and case folding
- deterministic tokenisation
- term-frequency postings: term -> {document_id: term_frequency}
- document-frequency metadata for explainability
- deduplicated query terms
- AND / OR retrieval
- matched-term reporting
- deterministic ordering

Complexity (documents D, total tokens T, query terms Q):
- build: O(T) time, O(T) space for postings
- search_with_terms: O(Q + R * Q) time where R is the number of matches,
  O(Q + R) space. No clause is rescanned; only postings lists are intersected.
"""

from collections import Counter, defaultdict
import re
import unicodedata


TOKEN_PATTERN = re.compile(r"[^\W_]+(?:['\u2019][^\W_]+)?", re.UNICODE)


def normalize_text(value: str) -> str:
    """NFKC normalise and case-fold so case/width variants share one key."""
    return unicodedata.normalize("NFKC", value).casefold()


def tokenize(value: str) -> list[str]:
    """Split normalised text into deterministic, punctuation-stripped tokens."""
    return TOKEN_PATTERN.findall(normalize_text(value))


class InvertedIndex:
    """term -> {document_id: term_frequency}, plus document_frequency metadata.

    Postings store term frequencies so retrieval can report not only which
    clauses matched but how often each query term occurred in each document.
    """

    def __init__(self, documents: dict[str, str]):
        self.documents = dict(sorted(documents.items()))
        self.postings: dict[str, dict[str, int]] = defaultdict(dict)
        self.document_frequency: dict[str, int] = defaultdict(int)
        for document_id in sorted(documents):
            frequencies = Counter(tokenize(documents[document_id]))
            for term, count in frequencies.items():
                self.postings[term][document_id] = count
                self.document_frequency[term] += 1
        self.postings = dict(self.postings)
        self.document_frequency = dict(self.document_frequency)

    def document_count(self) -> int:
        return len(self.documents)

    def term_count(self) -> int:
        return len(self.postings)

    def postings_for(self, term: str) -> dict[str, int]:
        """Return the {document_id: term_frequency} mapping for one term."""
        return dict(self.postings.get(term, {}))

    def search(self, query: str, mode: str = "AND") -> list[str]:
        """Return sorted matching document IDs (no term metadata)."""
        return [item["id"] for item in self.search_with_terms(query, mode)]

    def search_with_terms(self, query: str, mode: str = "AND") -> list[dict]:
        """Return matches with matched-term and frequency metadata.

        Each result is a dict with keys: id, matched_terms, term_frequency, score.
        Ordering is deterministic: ascending document id.
        """
        terms = list(dict.fromkeys(tokenize(query)))
        normalized_mode = mode.upper()
        if normalized_mode not in {"AND", "OR"}:
            raise ValueError("mode must be AND or OR")
        if not terms:
            return []
        candidate_sets = [set(self.postings.get(term, {})) for term in terms]
        if normalized_mode == "AND":
            matched_ids = set.intersection(*candidate_sets) if candidate_sets else set()
        else:
            matched_ids = set().union(*candidate_sets) if candidate_sets else set()
        results: list[dict] = []
        for document_id in sorted(matched_ids):
            matched_terms: list[str] = []
            term_frequency: dict[str, int] = {}
            total = 0
            for term in terms:
                postings = self.postings.get(term, {})
                if document_id in postings:
                    matched_terms.append(term)
                    count = postings[document_id]
                    term_frequency[term] = count
                    total += count
            results.append({
                "id": document_id,
                "matched_terms": matched_terms,
                "term_frequency": term_frequency,
                "score": total,
            })
        return results
