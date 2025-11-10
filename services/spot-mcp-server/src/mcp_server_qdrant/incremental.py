"""Incremental indexing with hash-based change detection."""

import hashlib
import logging
import time
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


class FileHashTracker:
    """Track file hashes to detect changes for incremental indexing."""

    def __init__(self):
        self.file_hashes: Dict[str, str] = {}  # {file_path: hash}
        self.last_check: Dict[str, float] = {}  # {file_path: timestamp}
        self.indexable_extensions: Set[str] = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".scala",
            ".clj",
            ".sh",
            ".bash",
            ".zsh",
            ".lua",
            ".r",
            ".m",
            ".mm",
            ".sql",
            ".yaml",
            ".yml",
            ".json",
            ".toml",
        }

    def compute_hash(self, content: str) -> str:
        """Compute MD5 hash of file content."""
        try:
            return hashlib.md5(content.encode("utf-8")).hexdigest()
        except (UnicodeEncodeError, AttributeError):
            # Fallback for binary or non-UTF8 content
            if isinstance(content, bytes):
                return hashlib.md5(content).hexdigest()
            # For strings that can't be UTF-8 encoded, use latin-1
            return hashlib.md5(content.encode("latin-1", errors="ignore")).hexdigest()

    def is_indexable(self, file_path: str) -> bool:
        """Check if file type should be indexed."""
        import os

        _, ext = os.path.splitext(file_path)
        return ext.lower() in self.indexable_extensions

    def has_changed(self, file_path: str, content: str) -> bool:
        """
        Check if file has changed since last index.

        Returns True if:
        - File is new (not in cache)
        - File content hash has changed
        """
        if not self.is_indexable(file_path):
            logger.info(f"   🔍 Hash check: {file_path} (not indexable, skipping)")
            return False

        new_hash = self.compute_hash(content)
        old_hash = self.file_hashes.get(file_path)

        if old_hash != new_hash:
            status = "NEW" if old_hash is None else "CHANGED"
            logger.info(
                f"   🔍 Hash check: {file_path} → {status} (old: {old_hash[:8] if old_hash else 'none'}... → new: {new_hash[:8]}...)"
            )
            self.file_hashes[file_path] = new_hash
            self.last_check[file_path] = time.time()
            return True

        # Update last check time even if not changed
        logger.info(
            f"   🔍 Hash check: {file_path} → UNCHANGED (hash: {new_hash[:8]}...)"
        )
        self.last_check[file_path] = time.time()
        return False

    def get_changed_files(self, files: Dict[str, str]) -> List[str]:
        """
        Return list of changed file paths.

        Args:
            files: Dict of file_path: content

        Returns:
            List of file paths that have changed
        """
        logger.info(f"🔍 Checking {len(files)} files for changes...")
        changed = []
        for path, content in files.items():
            if self.has_changed(path, content):
                changed.append(path)
        logger.info(
            f"   ✓ Hash check complete: {len(changed)} changed, {len(files) - len(changed)} unchanged"
        )
        return changed

    def mark_indexed(self, file_path: str, content: str):
        """Mark a file as indexed with its current hash."""
        if self.is_indexable(file_path):
            hash_value = self.compute_hash(content)
            self.file_hashes[file_path] = hash_value
            self.last_check[file_path] = time.time()
            logger.info(
                f"   📌 Marked as indexed: {file_path} (hash: {hash_value[:8]}...)"
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked files."""
        return {
            "total_files": len(self.file_hashes),
            "oldest_check": min(self.last_check.values()) if self.last_check else None,
            "newest_check": max(self.last_check.values()) if self.last_check else None,
        }

    def remove_file(self, file_path: str):
        """Remove a file from tracking (e.g., when deleted)."""
        self.file_hashes.pop(file_path, None)
        self.last_check.pop(file_path, None)

    def clear(self):
        """Clear all tracked files."""
        self.file_hashes.clear()
        self.last_check.clear()
