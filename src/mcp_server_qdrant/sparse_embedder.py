"""
BM25-style sparse embeddings for keyword matching.

Sparse vectors complement dense embeddings by capturing exact term matches
and keyword relevance, which is especially important for technical terms,
function names, and code identifiers.
"""

import logging
import math
import re
from collections import Counter
from typing import Dict, List

from qdrant_client.models import SparseVector

logger = logging.getLogger(__name__)

# Common English stop words (minimal set)
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "will",
    "with",
}


class BM25SparseEmbedder:
    """
    BM25-style sparse embeddings for keyword matching.

    Uses a simplified BM25 algorithm to generate sparse vectors where:
    - Indices represent term hashes
    - Values represent BM25 relevance scores

    This enables hybrid search combining semantic and keyword matching.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 embedder.

        Args:
            k1: Term frequency saturation parameter (default 1.5)
            b: Length normalization parameter (default 0.75)
        """
        self.k1 = k1
        self.b = b
        self.vocab: Dict[str, int] = {}  # term -> index mapping
        self.doc_count = 0
        self.avg_doc_length = 0.0
        self.df: Dict[str, int] = {}  # document frequency for IDF

    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into terms.

        Args:
            text: Input text

        Returns:
            List of lowercase terms (stopwords removed)
        """
        # Split on non-alphanumeric, keep underscores for identifiers
        tokens = re.findall(r"\w+", text.lower())

        # Remove stop words but keep short technical terms (< 3 chars are often meaningful in code)
        filtered = [t for t in tokens if t not in STOP_WORDS or len(t) < 3]

        return filtered

    def get_term_index(self, term: str) -> int:
        """
        Get or create index for a term.

        Args:
            term: The term to index

        Returns:
            Integer index for the term
        """
        if term not in self.vocab:
            self.vocab[term] = len(self.vocab)
        return self.vocab[term]

    def compute_bm25_score(
        self, term_freq: int, doc_length: int, doc_freq: int
    ) -> float:
        """
        Compute BM25 score for a term.

        Args:
            term_freq: Frequency of term in document
            doc_length: Total number of terms in document
            doc_freq: Number of documents containing the term

        Returns:
            BM25 score
        """
        # IDF component
        idf = math.log((self.doc_count - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

        # TF component with saturation and length normalization
        numerator = term_freq * (self.k1 + 1)
        denominator = term_freq + self.k1 * (
            1 - self.b + self.b * (doc_length / self.avg_doc_length)
        )

        return idf * (numerator / denominator)

    def embed_documents(self, texts: List[str]) -> List[SparseVector]:
        """
        Generate sparse embeddings for multiple documents.

        Args:
            texts: List of document texts

        Returns:
            List of SparseVector objects
        """
        # Update statistics
        self.doc_count = len(texts)
        all_tokens = [self.tokenize(text) for text in texts]

        # Calculate average document length
        total_length = sum(len(tokens) for tokens in all_tokens)
        self.avg_doc_length = total_length / max(len(texts), 1)

        # Update document frequencies
        for tokens in all_tokens:
            unique_terms = set(tokens)
            for term in unique_terms:
                self.df[term] = self.df.get(term, 0) + 1

        # Generate sparse vectors
        sparse_vectors = []
        for tokens in all_tokens:
            term_counts = Counter(tokens)
            doc_length = len(tokens)

            indices = []
            values = []

            for term, freq in term_counts.items():
                idx = self.get_term_index(term)
                doc_freq = self.df.get(term, 1)
                score = self.compute_bm25_score(freq, doc_length, doc_freq)

                if score > 0:  # Only include non-zero scores
                    indices.append(idx)
                    values.append(score)

            sparse_vectors.append(SparseVector(indices=indices, values=values))

        return sparse_vectors

    def embed_query(self, text: str) -> SparseVector:
        """
        Generate sparse embedding for a query.

        Args:
            text: Query text

        Returns:
            SparseVector object
        """
        tokens = self.tokenize(text)
        term_counts = Counter(tokens)

        indices = []
        values = []

        for term, freq in term_counts.items():
            # For queries, use simpler term weighting (no length normalization)
            if term in self.vocab:
                idx = self.vocab[term]
                doc_freq = self.df.get(term, 1)

                # Simplified query scoring (IDF * TF)
                idf = math.log(
                    (self.doc_count - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0
                )
                score = idf * freq

                if score > 0:
                    indices.append(idx)
                    values.append(score)

        return SparseVector(indices=indices, values=values)

    def is_available(self) -> bool:
        """Check if sparse embedder is ready to use."""
        return len(self.vocab) > 0
