"""Analyzes code to extract semantic information and patterns."""

import re
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """Analyzes code to extract semantic meaning and patterns."""

    @staticmethod
    def extract_purpose(content: str, language: str) -> Optional[str]:
        """Extract the purpose of a file from its content."""
        # Look for docstrings, comments, or module-level descriptions
        if language == "python":
            # Try to find module docstring
            docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if docstring_match:
                return docstring_match.group(1).strip()[:200]

            # Look for comments at the top
            lines = content.split("\n")[:10]
            comments = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    comments.append(stripped[1:].strip())
            if comments:
                return " ".join(comments)[:200]

        return None

    @staticmethod
    def extract_api_endpoints(content: str, language: str) -> List[Dict[str, Any]]:
        """Extract API endpoints from code."""
        endpoints = []

        if language == "python":
            # FastAPI/Flask patterns
            patterns = [
                (r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']', r'\1'),
                (r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']', r'\1'),
                (r'@.*?\.route\(["\']([^"\']+)["\']', "route"),
            ]

            for pattern, method in patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    endpoints.append({
                        "path": match.group(2) if len(match.groups()) > 1 else match.group(1),
                        "method": method.upper() if method != "route" else "GET",
                        "line": content[:match.start()].count("\n") + 1,
                    })

        return endpoints

    @staticmethod
    def extract_data_structures(content: str, language: str) -> List[Dict[str, Any]]:
        """Extract data structures (models, schemas, types)."""
        structures = []

        if language == "python":
            # Pydantic models
            model_pattern = r'class\s+(\w+)\s*\(.*?BaseModel.*?\):'
            for match in re.finditer(model_pattern, content, re.DOTALL):
                structures.append({
                    "name": match.group(1),
                    "type": "pydantic_model",
                    "line": content[:match.start()].count("\n") + 1,
                })

            # Dataclasses
            dataclass_pattern = r'@dataclass\s+class\s+(\w+)'
            for match in re.finditer(dataclass_pattern, content):
                structures.append({
                    "name": match.group(1),
                    "type": "dataclass",
                    "line": content[:match.start()].count("\n") + 1,
                })

        return structures

    @staticmethod
    def extract_dependencies(content: str, language: str) -> List[str]:
        """Extract dependencies/imports."""
        dependencies = []

        if language == "python":
            # Import statements
            import_pattern = r'(?:from\s+(\S+)\s+)?import\s+([^\n]+)'
            for match in re.finditer(import_pattern, content):
                if match.group(1):  # from X import Y
                    dependencies.append(match.group(1))
                else:  # import X
                    deps = [d.strip().split(" as ")[0] for d in match.group(2).split(",")]
                    dependencies.extend(deps)

        return list(set(dependencies))

    @staticmethod
    def extract_decorators(content: str, language: str) -> List[str]:
        """Extract decorators from code (Python, TypeScript)."""
        decorators = []

        if language == "python":
            # Python decorators: @decorator_name
            decorator_pattern = r'@(\w+(?:\.\w+)*)'
            decorators = list(set(re.findall(decorator_pattern, content)))

        return decorators

    @staticmethod
    def extract_semantic_tags(content: str, file_path: str, language: str) -> List[str]:
        """
        Extract semantic tags that describe the code's purpose and tech stack.

        Returns:
            List of tags like 'api', 'database', 'authentication', 'fastapi', etc.
        """
        tags = []
        content_lower = content.lower()

        # Framework detection
        if "fastapi" in content_lower or "@app.get" in content_lower:
            tags.append("fastapi")
        if "flask" in content_lower or "from flask import" in content_lower:
            tags.append("flask")
        if "sqlalchemy" in content_lower:
            tags.append("sqlalchemy")
        if "pydantic" in content_lower or "basemodel" in content_lower:
            tags.append("pydantic")
        if "pytest" in content_lower or "def test_" in content_lower:
            tags.append("testing")
        if "asyncio" in content_lower or "async def" in content_lower:
            tags.append("async")

        # Purpose detection
        if any(word in content_lower for word in ["@app.get", "@app.post", "router.", "endpoint"]):
            tags.append("api")
        if any(word in content_lower for word in ["database", "db", "session", "query", "select"]):
            tags.append("database")
        if any(word in content_lower for word in ["auth", "login", "token", "jwt", "password"]):
            tags.append("authentication")
        if any(word in content_lower for word in ["model", "schema", "basemodel"]):
            tags.append("models")
        if "test" in file_path.lower() or "def test_" in content_lower:
            tags.append("test")

        # Pattern detection
        if "factory" in content_lower and "class" in content_lower:
            tags.append("factory-pattern")
        if "singleton" in content_lower:
            tags.append("singleton-pattern")
        if "repository" in content_lower:
            tags.append("repository-pattern")

        return list(set(tags))

    @staticmethod
    def extract_quality_signals(content: str, language: str) -> Dict[str, Any]:
        """
        Extract code quality signals.

        Returns:
            Dict with keys: has_docstrings, has_type_hints, has_tests, complexity_estimate
        """
        signals = {
            "has_docstrings": False,
            "has_type_hints": False,
            "has_tests": False,
            "line_count": len(content.split("\n")),
        }

        if language == "python":
            # Check for docstrings
            if '"""' in content or "'''" in content:
                signals["has_docstrings"] = True

            # Check for type hints
            if "->" in content or ": " in content:
                # Simple heuristic: presence of type annotations
                type_hint_pattern = r'def \w+\([^)]*:\s*\w+[^)]*\)|def \w+\([^)]*\)\s*->'
                if re.search(type_hint_pattern, content):
                    signals["has_type_hints"] = True

            # Check for tests
            if "def test_" in content or "class Test" in content:
                signals["has_tests"] = True

        return signals

    @staticmethod
    def extract_function_signatures(content: str, language: str) -> List[Dict[str, Any]]:
        """
        Extract function signatures with type information.

        Returns:
            List of dicts with keys: name, params, return_type, decorators
        """
        signatures = []

        if language == "python":
            # Match function definitions with optional type hints
            func_pattern = r'(?:(@\w+(?:\.\w+)*)\s+)*def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?:'
            for match in re.finditer(func_pattern, content):
                decorator = match.group(1) if match.group(1) else None
                name = match.group(2)
                params = match.group(3).strip() if match.group(3) else ""
                return_type = match.group(4).strip() if match.group(4) else None

                signatures.append({
                    "name": name,
                    "params": params,
                    "return_type": return_type,
                    "decorator": decorator,
                })

        return signatures

    @staticmethod
    def generate_file_summary(file_info: Dict[str, Any]) -> str:
        """Generate a human-readable summary of a file."""
        parts = []

        if file_info.get("classes"):
            class_names = [c["name"] for c in file_info["classes"]]
            parts.append(f"Classes: {', '.join(class_names)}")

        if file_info.get("functions"):
            func_names = [f["name"] for f in file_info["functions"]]
            parts.append(f"Functions: {', '.join(func_names[:5])}")  # Limit to 5

        if file_info.get("purpose"):
            parts.append(f"Purpose: {file_info['purpose']}")

        return ". ".join(parts) if parts else f"File: {file_info.get('path', 'unknown')}"
