"""
Extract usage examples from code.
Captures how functions and classes are actually used.
"""

import ast
import re
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class UsageExample:
    """An example of how a function/class is used."""

    target_name: str  # Function/class being called
    example_code: str  # The actual usage code
    context: str  # Where it's used (file, function, etc.)
    file_path: str
    line_number: int


class UsageExtractor:
    """Extracts usage examples from code."""

    def extract_python_usage(
        self, content: str, file_path: str
    ) -> List[UsageExample]:
        """
        Extract usage examples from Python code.

        Focuses on tracking usage of IMPORTED names (classes and functions).

        Returns:
            List of UsageExample objects
        """
        examples = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        lines = content.split("\n")

        # Track what's imported (these are the names we care about)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imported_names.add(name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imported_names.add(name)

        logger.info(f"   🔎 Detected {len(imported_names)} imported names in {file_path}")
        logger.info(f"       Names: {sorted(list(imported_names))}")

        # Track what's being defined locally (skip these)
        defined_names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined_names.add(node.name)

        # Find usages of imported names
        # Track which Name nodes are already part of Calls (to avoid duplicates)
        name_nodes_in_calls = set()

        # First pass: find all Call nodes with imported names
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in imported_names:
                    name_nodes_in_calls.add(node.func)
                    target_name = node.func.id
                    line_num = node.lineno

                    # Skip if it's being defined in this file
                    if target_name not in defined_names:
                        # Extract the usage context
                        if 1 <= line_num <= len(lines):
                            start = max(0, line_num - 2)
                            end = min(len(lines), line_num + 1)
                            context_lines = lines[start:end]
                            example_code = "\n".join(context_lines)
                            context = self._get_context(tree, node)

                            examples.append(
                                UsageExample(
                                    target_name=target_name,
                                    example_code=example_code,
                                    context=context,
                                    file_path=file_path,
                                    line_number=line_num,
                                )
                            )

        # Second pass: find other usages (not in calls)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node not in name_nodes_in_calls:
                if isinstance(node.ctx, ast.Load) and node.id in imported_names:
                    if node.id not in defined_names:
                        target_name = node.id
                        line_num = node.lineno

                        if 1 <= line_num <= len(lines):
                            start = max(0, line_num - 2)
                            end = min(len(lines), line_num + 1)
                            context_lines = lines[start:end]
                            example_code = "\n".join(context_lines)
                            context = self._get_context(tree, node)

                            examples.append(
                                UsageExample(
                                    target_name=target_name,
                                    example_code=example_code,
                                    context=context,
                                    file_path=file_path,
                                    line_number=line_num,
                                )
                            )

        return examples

    def _get_call_name(self, call_node: ast.Call) -> Optional[str]:
        """Extract the function/class name from a call node."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            # For method calls, get the base object if it's a simple name
            if isinstance(call_node.func.value, ast.Name):
                return call_node.func.value.id
            return call_node.func.attr
        return None

    def _get_context(self, tree: ast.AST, target_node: ast.AST) -> str:
        """Determine what function/class contains this node."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if target_node in ast.walk(node):
                    return f"function: {node.name}"
            elif isinstance(node, ast.ClassDef):
                if target_node in ast.walk(node):
                    # Check if it's in a method
                    for child in node.body:
                        if isinstance(child, ast.FunctionDef):
                            if target_node in ast.walk(child):
                                return f"method: {node.name}.{child.name}"
                    return f"class: {node.name}"
        return "module"

    def extract_usage(
        self, content: str, file_path: str, language: str
    ) -> List[UsageExample]:
        """
        Extract usage examples based on language.

        Currently only supports Python. Other languages return empty list
        (usage tracking can be added for JavaScript, TypeScript, Go, etc. in the future).

        Args:
            content: File content
            file_path: Path to file
            language: Programming language (e.g., 'python', 'javascript', 'typescript')

        Returns:
            List of UsageExample objects (empty for non-Python languages)
        """
        if language == "python":
            return self.extract_python_usage(content, file_path)
        else:
            # Usage extraction for other languages not yet implemented
            # The codebase will still be indexed and searchable, just without usage tracking
            return []
