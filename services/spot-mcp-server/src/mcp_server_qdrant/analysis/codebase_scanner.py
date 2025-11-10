"""Scans and indexes codebase structure."""

import ast
import fnmatch
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Information about a code file."""

    path: str
    language: str
    size: int
    line_count: int
    functions: List[Dict[str, Any]]
    classes: List[Dict[str, Any]]
    imports: List[str]
    exports: List[str]
    purpose: Optional[str] = None
    dependencies: List[str] = None


@dataclass
class ProjectStructure:
    """Structure of the entire project."""

    root_path: str
    total_files: int
    languages: Dict[str, int]
    files: List[FileInfo]
    entry_points: List[str]
    main_modules: List[str]


class CodebaseScanner:
    """Scans codebase and extracts structural information."""

    def __init__(
        self,
        root_path: str,
        ignore_patterns: Optional[List[str]] = None,
        respect_gitignore: bool = True,
    ):
        self.root_path = Path(root_path).resolve()

        # Comprehensive default ignores
        default_ignores = [
            # Version control
            ".git",
            ".svn",
            ".hg",
            # Python
            "__pycache__",
            ".venv",
            "venv",
            "env",
            ".pytest_cache",
            ".tox",
            ".coverage",
            "*.egg-info",
            ".mypy_cache",
            ".ruff_cache",
            # Node.js
            "node_modules",
            ".next",
            ".nuxt",
            "out",
            ".cache",
            # Build outputs
            "dist",
            "build",
            "target",  # Rust, Java
            "bin",
            "obj",  # C#
            # IDE
            ".idea",
            ".vscode",
            ".vs",
            # OS
            ".DS_Store",
            "Thumbs.db",
            # Project specific
            ".local-dev",
            "qdrant-data",
            # Large files
            "*.log",
            "*.lock",
            "package-lock.json",
            "yarn.lock",
            "Cargo.lock",
            "poetry.lock",
        ]

        self.ignore_patterns = ignore_patterns or default_ignores
        self.gitignore_patterns = []

        # Parse .gitignore if requested
        if respect_gitignore:
            gitignore_path = self.root_path / ".gitignore"
            if gitignore_path.exists():
                self.gitignore_patterns = self._parse_gitignore(gitignore_path)

    def _parse_gitignore(self, gitignore_path: Path) -> List[str]:
        """Parse .gitignore file and extract patterns."""
        patterns = []
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith("#"):
                        # Remove leading slash for root-relative patterns
                        if line.startswith("/"):
                            line = line[1:]
                        # Remove trailing slash
                        if line.endswith("/"):
                            line = line[:-1]
                        patterns.append(line)
        except Exception as e:
            logger.warning(f"Failed to parse .gitignore: {e}")
        return patterns

    def should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        path_str = str(path.relative_to(self.root_path))
        path_name = path.name

        # Check default patterns
        for pattern in self.ignore_patterns:
            # Wildcard pattern matching
            if "*" in pattern:
                if fnmatch.fnmatch(path_name, pattern) or fnmatch.fnmatch(
                    path_str, pattern
                ):
                    return True
            # Substring matching
            elif pattern in path_str:
                return True

        # Check gitignore patterns
        for pattern in self.gitignore_patterns:
            # Simple glob matching
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(
                path_str, f"**/{pattern}"
            ):
                return True
            # Directory matching
            if pattern in path_str.split(os.sep):
                return True

        return False

    def detect_language(self, file_path: Path) -> Optional[str]:
        """Detect programming language from file extension."""
        ext = file_path.suffix.lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "shell",
            ".ps1": "powershell",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".md": "markdown",
        }
        return language_map.get(ext)

    def analyze_python_file(self, file_path: Path) -> FileInfo:
        """Analyze a Python file and extract structure."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                tree = ast.parse(content, filename=str(file_path))
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return FileInfo(
                path=str(file_path.relative_to(self.root_path)),
                language="python",
                size=len(content),
                line_count=len(content.splitlines()),
                functions=[],
                classes=[],
                imports=[],
                exports=[],
            )

        functions = []
        classes = []
        imports = []
        exports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "args": [arg.arg for arg in node.args.args],
                        "docstring": ast.get_docstring(node),
                    }
                )
            elif isinstance(node, ast.ClassDef):
                methods = [
                    {
                        "name": n.name,
                        "line": n.lineno,
                    }
                    for n in node.body
                    if isinstance(n, ast.FunctionDef)
                ]
                classes.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods,
                        "docstring": ast.get_docstring(node),
                    }
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
                for alias in node.names:
                    imports.append(
                        f"{node.module}.{alias.name}" if node.module else alias.name
                    )

        # Find exports (top-level assignments, functions, classes)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                exports.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        exports.append(target.id)

        return FileInfo(
            path=str(file_path.relative_to(self.root_path)),
            language="python",
            size=len(content),
            line_count=len(content.splitlines()),
            functions=functions,
            classes=classes,
            imports=list(set(imports)),
            exports=list(set(exports)),
        )

    def analyze_file(self, file_path: Path) -> Optional[FileInfo]:
        """Analyze a file and extract information."""
        language = self.detect_language(file_path)
        if not language:
            return None

        if language == "python":
            return self.analyze_python_file(file_path)

        # For non-Python files, extract basic info
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return None

        return FileInfo(
            path=str(file_path.relative_to(self.root_path)),
            language=language,
            size=len(content),
            line_count=len(content.splitlines()),
            functions=[],
            classes=[],
            imports=[],
            exports=[],
        )

    def scan(self) -> ProjectStructure:
        """Scan the entire codebase."""
        files = []
        languages = {}
        entry_points = []
        main_modules = []

        for root, dirs, filenames in os.walk(self.root_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not self.should_ignore(Path(root) / d)]

            for filename in filenames:
                file_path = Path(root) / filename
                if self.should_ignore(file_path):
                    continue

                file_info = self.analyze_file(file_path)
                if file_info:
                    files.append(file_info)
                    languages[file_info.language] = (
                        languages.get(file_info.language, 0) + 1
                    )

                    # Detect entry points
                    if filename in [
                        "main.py",
                        "__main__.py",
                        "index.js",
                        "main.go",
                        "main.rs",
                    ]:
                        entry_points.append(file_info.path)
                    if "main" in filename.lower() or "index" in filename.lower():
                        main_modules.append(file_info.path)

        return ProjectStructure(
            root_path=str(self.root_path),
            total_files=len(files),
            languages=languages,
            files=files,
            entry_points=entry_points,
            main_modules=main_modules,
        )
