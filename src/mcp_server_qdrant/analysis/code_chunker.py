"""
Smart code chunking for semantic search.
Breaks code into meaningful, searchable units.
"""

import ast
import hashlib
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """A chunk of code with context."""

    content: str
    chunk_type: str  # 'function', 'class', 'method', 'import_block', 'file_header'
    name: Optional[str]  # Function/class name
    start_line: int
    end_line: int
    file_path: str
    language: str
    parent_class: Optional[str] = None  # For methods
    docstring: Optional[str] = None
    hash: Optional[str] = None  # Content hash for deduplication

    def __post_init__(self):
        """Generate content hash after initialization."""
        if not self.hash:
            self.hash = hashlib.md5(
                f"{self.file_path}:{self.start_line}:{self.content}".encode()
            ).hexdigest()


class CodeChunker:
    """Intelligently chunks code files into searchable units."""

    def __init__(self, max_chunk_size: int = 500):
        """
        Initialize the code chunker.

        Args:
            max_chunk_size: Maximum number of lines per chunk for large blocks
        """
        self.max_chunk_size = max_chunk_size

    def chunk_python_file(self, content: str, file_path: str) -> List[CodeChunk]:
        """
        Chunk a Python file into semantic units.

        Returns:
            List of CodeChunk objects
        """
        chunks = []

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(f"Syntax error parsing {file_path}: {e}")
            return [self._create_fallback_chunk(content, file_path, "python")]

        lines = content.split("\n")

        # Extract file-level docstring if present
        file_docstring = ast.get_docstring(tree)
        if file_docstring:
            # Find the docstring in the source
            for i, line in enumerate(lines[:20]):  # Check first 20 lines
                if '"""' in line or "'''" in line:
                    # Find end of docstring
                    end = i + 1
                    while end < len(lines) and ('"""' not in lines[end] and "'''" not in lines[end]):
                        end += 1
                    docstring_content = "\n".join(lines[i : end + 1])
                    chunks.append(
                        CodeChunk(
                            content=docstring_content,
                            chunk_type="file_header",
                            name=None,
                            start_line=i + 1,
                            end_line=end + 1,
                            file_path=file_path,
                            language="python",
                            docstring=file_docstring,
                        )
                    )
                    break

        # Extract imports block
        imports = [
            node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        if imports:
            start_line = imports[0].lineno
            end_line = imports[-1].end_lineno or start_line
            import_content = "\n".join(lines[start_line - 1 : end_line])
            chunks.append(
                CodeChunk(
                    content=import_content,
                    chunk_type="import_block",
                    name=None,
                    start_line=start_line,
                    end_line=end_line,
                    file_path=file_path,
                    language="python",
                )
            )

        # Extract functions and classes
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Function definition
                start_line = node.lineno
                end_line = node.end_lineno or start_line
                function_content = "\n".join(lines[start_line - 1 : end_line])
                docstring = ast.get_docstring(node)

                # Determine if it's a method or standalone function
                parent_class = None
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef):
                        if node in parent.body:
                            parent_class = parent.name
                            break

                chunks.append(
                    CodeChunk(
                        content=function_content,
                        chunk_type="method" if parent_class else "function",
                        name=node.name,
                        start_line=start_line,
                        end_line=end_line,
                        file_path=file_path,
                        language="python",
                        parent_class=parent_class,
                        docstring=docstring,
                    )
                )

            elif isinstance(node, ast.ClassDef):
                # Class definition (header + docstring)
                start_line = node.lineno
                # Only include class definition line and docstring, not all methods
                docstring_node = node.body[0] if node.body and isinstance(node.body[0], ast.Expr) else None
                if docstring_node:
                    end_line = docstring_node.end_lineno or start_line
                else:
                    end_line = start_line

                class_header = "\n".join(lines[start_line - 1 : end_line])
                docstring = ast.get_docstring(node)

                chunks.append(
                    CodeChunk(
                        content=class_header,
                        chunk_type="class",
                        name=node.name,
                        start_line=start_line,
                        end_line=end_line,
                        file_path=file_path,
                        language="python",
                        docstring=docstring,
                    )
                )

        return chunks

    def chunk_file(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """
        Chunk a file based on its language.

        Args:
            content: File content
            file_path: Path to the file
            language: Programming language

        Returns:
            List of CodeChunk objects
        """
        if language == "python":
            return self.chunk_python_file(content, file_path)
        else:
            # Fallback for unsupported languages
            return [self._create_fallback_chunk(content, file_path, language)]

    def _create_fallback_chunk(
        self, content: str, file_path: str, language: str
    ) -> CodeChunk:
        """Create a single chunk for the entire file as fallback."""
        lines = content.split("\n")
        # Limit to first N lines for very large files
        if len(lines) > self.max_chunk_size:
            content = "\n".join(lines[: self.max_chunk_size])
            content += f"\n\n... ({len(lines) - self.max_chunk_size} more lines)"

        return CodeChunk(
            content=content,
            chunk_type="file",
            name=None,
            start_line=1,
            end_line=len(lines),
            file_path=file_path,
            language=language,
        )
