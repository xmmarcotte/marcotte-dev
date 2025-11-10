"""Maps relationships between code components."""

import re
import logging
from typing import Dict, List, Set, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class RelationshipMapper:
    """Maps relationships and dependencies between code components."""

    def __init__(self):
        self.import_graph: Dict[str, Set[str]] = defaultdict(set)
        self.usage_graph: Dict[str, Set[str]] = defaultdict(set)
        self.file_to_components: Dict[str, Set[str]] = defaultdict(set)

    def add_file(self, file_path: str, imports: List[str], exports: List[str], classes: List[str], functions: List[str]):
        """Add a file and its components to the relationship graph."""
        # Map file to its components
        for cls in classes:
            self.file_to_components[file_path].add(cls)
        for func in functions:
            self.file_to_components[file_path].add(func)

        # Build import graph
        for imp in imports:
            self.import_graph[file_path].add(imp)

        # Build usage graph (simplified - would need AST analysis for full accuracy)
        for export in exports:
            self.usage_graph[export].add(file_path)

    def find_dependencies(self, file_path: str) -> List[str]:
        """Find all files that this file depends on."""
        return list(self.import_graph.get(file_path, set()))

    def find_dependents(self, file_path: str) -> List[str]:
        """Find all files that depend on this file."""
        dependents = []
        file_components = self.file_to_components.get(file_path, set())

        for other_file, components in self.file_to_components.items():
            if other_file != file_path:
                # Check if other_file imports from file_path
                imports = self.import_graph.get(other_file, set())
                if any(comp in imports or file_path in str(imp) for imp in imports for comp in file_components):
                    dependents.append(other_file)

        return dependents

    def find_related_files(self, file_path: str) -> List[Tuple[str, str]]:
        """Find files related to this one (dependencies and dependents)."""
        related = []
        dependencies = self.find_dependencies(file_path)
        dependents = self.find_dependents(file_path)

        for dep in dependencies:
            related.append((dep, "depends_on"))
        for dep in dependents:
            related.append((dep, "depended_by"))

        return related

    def get_component_usage(self, component_name: str) -> List[str]:
        """Find where a component (class/function) is used."""
        return list(self.usage_graph.get(component_name, set()))
