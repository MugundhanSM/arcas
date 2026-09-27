"""Structural code analysis via Tree-sitter."""

from __future__ import annotations

import re
from typing import Dict, List

from app.core.logging import get_logger
from app.tools import treesitter_registry as registry

logger = get_logger("arcas.tools.treesitter")


_IDENTIFIER_FIELDS = ("name", "declarator", "path")
_IDENTIFIER_TYPES = (
    "identifier",
    "type_identifier",
    "field_identifier",
    "constant",
    "property_identifier",
    "scoped_identifier",
    "word",
)


class TreeSitterTool:
    """Multi-language structural analysis with an honest capability report."""

    @staticmethod
    def analyze(code: str, language_name: str = "python") -> Dict:
        from app.core.telemetry import start_span

        with start_span(
            "tool.treesitter", layer=6, language=language_name or "python"
        ) as span:
            result = TreeSitterTool._analyze(code, language_name)
            span.set_attribute("parser", result.get("parser", "unknown"))
            return result

    @staticmethod
    def _analyze(code: str, language_name: str = "python") -> Dict:
        language_name = registry.normalize_language(language_name or "python")

        loaded = registry.get_parser(language_name)
        if loaded is not None:
            parser, spec = loaded
            try:
                result = TreeSitterTool._analyze_with_grammar(code, parser, spec)
                result["parser"] = "tree-sitter"
                result["language"] = spec.language
                return result
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Tree-sitter parse failed for '%s' (%s); using regex "
                    "fallback.",
                    language_name,
                    exc,
                )

        result = TreeSitterTool._analyze_generic(code, language_name)
        result["parser"] = "regex"
        result["language"] = language_name
        return result

    # Tree-sitter path

    @staticmethod
    def _analyze_with_grammar(code: str, parser, spec) -> Dict:
        """Walk the syntax tree, driven entirely by the grammar spec."""
        source = bytes(code, "utf-8")
        tree = parser.parse(source)

        result: Dict[str, List[str]] = {
            "imports": [],
            "classes": [],
            "functions": [],
        }

        def text(node) -> str:
            return source[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace"
            )

        def identifier_of(node) -> str:
            """Best-effort name extraction that works across grammars."""
            for field_name in _IDENTIFIER_FIELDS:
                try:
                    child = node.child_by_field_name(field_name)
                except Exception:  # noqa: BLE001 - grammar lacks the field
                    child = None
                if child is not None:
                    if child.type in _IDENTIFIER_TYPES:
                        return text(child)
                    # e.g. C's `function_declarator` wraps the identifier.
                    nested = identifier_of(child)
                    if nested:
                        return nested
            for child in node.children:
                if child.type in _IDENTIFIER_TYPES:
                    return text(child)
            return ""

        # Byte ranges of imports already captured.
        captured_import_spans: List[tuple] = []

        def already_captured(node) -> bool:
            return any(
                start <= node.start_byte and node.end_byte <= end
                for start, end in captured_import_spans
            )

        def walk(node) -> None:
            node_type = node.type

            if node_type in spec.import_nodes:
                if already_captured(node):
                    for child in node.children:
                        walk(child)
                    return
                statement = text(node).strip()
                # A grouped block - Go's `import ( "fmt"\n "os" )`, Rust's nested `use` - spans several lines.
                if "\n" in statement and len(spec.import_nodes) > 1:
                    for child in node.children:
                        walk(child)
                    return
                captured_import_spans.append((node.start_byte, node.end_byte))
                # Ruby/bash model imports as generic calls; keep only the ones that actually import something.
                if spec.language in ("ruby", "bash"):
                    if not re.match(
                        r"^(require|require_relative|load|source|\.)\b", statement
                    ):
                        statement = ""
                if statement:
                    result["imports"].append(statement.splitlines()[0][:200])

            elif node_type in spec.class_nodes:
                name = identifier_of(node)
                if name:
                    result["classes"].append(name)

            elif node_type in spec.function_nodes:
                name = identifier_of(node)
                if name:
                    result["functions"].append(name)

            elif node_type in spec.value_function_nodes:
                # `const handler = () => {}` - a function bound to a name.
                try:
                    value = node.child_by_field_name("value")
                except Exception:  # noqa: BLE001
                    value = None
                if value is not None and value.type in spec.value_function_types:
                    name = identifier_of(node)
                    if name:
                        result["functions"].append(name)

            for child in node.children:
                walk(child)

        walk(tree.root_node)

        for key in ("imports", "classes", "functions"):
            result[key] = list(dict.fromkeys(result[key]))

        result["syntax_errors"] = TreeSitterTool._count_errors(tree.root_node)
        return result

    @staticmethod
    def _count_errors(root) -> int:
        """Number of error/missing nodes - a grammar-level syntax signal."""
        count = 0
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == "ERROR" or getattr(node, "is_missing", False):
                count += 1
            stack.extend(node.children)
        return count

    # Regex fallback

    @staticmethod
    def _analyze_generic(code: str, language_name: str) -> Dict:
        logger.info(
            "Using regex structural analysis for '%s' (no grammar loaded).",
            language_name,
        )

        import_patterns = [
            r"^\s*import\s+[\w.*]+",  # java / go / python
            r"^\s*from\s+[\w.]+\s+import",  # python
            r"^\s*#include\s+[<\"][\w./]+[>\"]",  # c / c++
            r"^\s*(?:const|let|var)?\s*\w+\s*=\s*require\(",  # node
            r"^\s*using\s+[\w.]+;",  # c#
            r"^\s*use\s+[\w:]+;",  # rust
            r"^\s*require(?:_relative)?\s+['\"]",  # ruby
        ]
        class_pattern = (
            r"\b(?:class|interface|struct|enum|trait|impl)\s+([A-Za-z_]\w*)"
        )
        function_pattern = (
            r"\b(?:func|function|def|fn|sub|void|public|private|protected|"
            r"static|[A-Za-z_][\w<>]*)\s+([A-Za-z_]\w*)\s*\("
        )

        imports = []
        for line in code.splitlines():
            for pattern in import_patterns:
                if re.match(pattern, line):
                    imports.append(line.strip())
                    break

        classes = re.findall(class_pattern, code)
        functions = [
            name
            for name in re.findall(function_pattern, code)
            if name.lower()
            not in {"if", "for", "while", "switch", "catch", "return", "else"}
        ]

        return {
            "imports": list(dict.fromkeys(imports)),
            "classes": list(dict.fromkeys(classes)),
            "functions": list(dict.fromkeys(functions)),
            "syntax_errors": 0,
        }

    # Capability reporting

    @staticmethod
    def capabilities() -> dict:
        """Report which languages get a real AST parse in this environment."""
        return registry.capabilities().as_dict()
