"""
Query enhancement for improved search quality.

Handles query expansion, abbreviation expansion, and code-specific processing
to make search more forgiving and effective.
"""

import logging
import re
from typing import List, Set

logger = logging.getLogger(__name__)


class QueryEnhancer:
    """
    Enhances user queries for better search results.

    Features:
    - Abbreviation expansion (db -> database)
    - Synonym expansion (auth -> authentication, login)
    - Code pattern recognition
    - Term normalization
    """

    # Common abbreviations in code
    ABBREVIATIONS = {
        "db": "database",
        "auth": "authentication",
        "repo": "repository",
        "config": "configuration",
        "util": "utility",
        "impl": "implementation",
        "mgr": "manager",
        "svc": "service",
        "msg": "message",
        "req": "request",
        "res": "response",
        "ctx": "context",
        "env": "environment",
        "init": "initialize",
        "conn": "connection",
        "async": "asynchronous",
    }

    # Common synonyms for technical terms
    SYNONYMS = {
        "auth": ["authentication", "login", "authorize"],
        "database": ["db", "storage", "datastore"],
        "api": ["endpoint", "route", "handler"],
        "error": ["exception", "failure", "issue"],
        "config": ["configuration", "settings", "options"],
        "test": ["testing", "unittest", "spec"],
        "async": ["asynchronous", "concurrent", "parallel"],
        "cache": ["caching", "memoize", "store"],
    }

    @staticmethod
    def detect_code_pattern(query: str) -> bool:
        """
        Detect if query contains code patterns (function names, class names, etc.).

        Args:
            query: Search query

        Returns:
            True if query appears to contain code
        """
        # Check for camelCase, PascalCase, snake_case patterns
        code_patterns = [
            r'[a-z]+[A-Z]',  # camelCase
            r'[A-Z][a-z]+[A-Z]',  # PascalCase
            r'\w+_\w+',  # snake_case
            r'def\s+\w+',  # function definition
            r'class\s+\w+',  # class definition
            r'\w+\(\)',  # function call
        ]

        for pattern in code_patterns:
            if re.search(pattern, query):
                return True

        return False

    @staticmethod
    def expand_abbreviations(query: str) -> str:
        """
        Expand common abbreviations in the query.

        Args:
            query: Original query

        Returns:
            Query with expanded abbreviations
        """
        words = query.lower().split()
        expanded = []

        for word in words:
            # Remove punctuation for matching
            clean_word = re.sub(r'[^\w]', '', word)

            if clean_word in QueryEnhancer.ABBREVIATIONS:
                # Add both original and expanded
                expanded.append(word)
                expanded.append(QueryEnhancer.ABBREVIATIONS[clean_word])
            else:
                expanded.append(word)

        return " ".join(expanded)

    @staticmethod
    def add_synonyms(query: str, max_synonyms: int = 2) -> str:
        """
        Add synonyms to improve recall.

        Args:
            query: Original query
            max_synonyms: Maximum synonyms to add per term

        Returns:
            Query with added synonyms
        """
        words = query.lower().split()
        enhanced = list(words)

        for word in words:
            clean_word = re.sub(r'[^\w]', '', word)

            if clean_word in QueryEnhancer.SYNONYMS:
                synonyms = QueryEnhancer.SYNONYMS[clean_word][:max_synonyms]
                enhanced.extend(synonyms)

        return " ".join(enhanced)

    @staticmethod
    def normalize_code_terms(query: str) -> str:
        """
        Normalize code-specific terms (handle camelCase, snake_case, etc.).

        Args:
            query: Original query

        Returns:
            Query with normalized terms
        """
        # Split camelCase into separate words
        # e.g., "getUserData" -> "get user data"
        words = []

        for word in query.split():
            # Handle camelCase
            if re.search(r'[a-z][A-Z]', word):
                # Insert spaces before capitals
                normalized = re.sub(r'([a-z])([A-Z])', r'\1 \2', word)
                words.append(normalized.lower())
            # Handle snake_case
            elif '_' in word:
                words.append(word.replace('_', ' '))
            else:
                words.append(word)

        return " ".join(words)

    def enhance_query(self, query: str, enable_expansion: bool = True) -> str:
        """
        Enhance query with all improvements.

        Args:
            query: Original search query
            enable_expansion: Whether to add synonyms/abbreviations (increases recall)

        Returns:
            Enhanced query string
        """
        # Start with original query
        enhanced = query

        # Detect if this is a code query
        is_code = self.detect_code_pattern(query)

        if is_code:
            # For code queries, preserve original but add normalized version
            logger.debug(f"Detected code pattern in query: {query}")
            normalized = self.normalize_code_terms(query)
            enhanced = f"{query} {normalized}"
        elif enable_expansion:
            # For natural language queries, expand aggressively
            logger.debug(f"Expanding natural language query: {query}")
            expanded_abbr = self.expand_abbreviations(query)
            with_synonyms = self.add_synonyms(expanded_abbr, max_synonyms=2)
            enhanced = with_synonyms

        logger.debug(f"Query enhanced: '{query}' -> '{enhanced}'")
        return enhanced

    def extract_filters_from_query(self, query: str) -> dict:
        """
        Extract filter hints from natural language query.

        Args:
            query: Search query

        Returns:
            Dict of suggested filters (e.g., {"language": "python", "category": "api"})
        """
        filters = {}
        query_lower = query.lower()

        # Language detection
        languages = ["python", "javascript", "typescript", "java", "rust", "go"]
        for lang in languages:
            if lang in query_lower:
                filters["language"] = lang
                break

        # Category detection
        if any(word in query_lower for word in ["test", "testing", "unittest"]):
            filters["tags"] = "test"
        elif any(word in query_lower for word in ["api", "endpoint", "route"]):
            filters["tags"] = "api"
        elif any(word in query_lower for word in ["database", "db", "query"]):
            filters["tags"] = "database"
        elif any(word in query_lower for word in ["auth", "authentication", "login"]):
            filters["tags"] = "authentication"

        return filters
