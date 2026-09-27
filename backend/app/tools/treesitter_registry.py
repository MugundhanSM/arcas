"""Tree-sitter grammar registry."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger("arcas.tools.treesitter.registry")


try:  # Core runtime is optional - see module docstring.
    from tree_sitter import Language, Parser  # type: ignore

    _TS_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import failure means "no tree-sitter"
    Language = None  # type: ignore[assignment]
    Parser = None  # type: ignore[assignment]
    _TS_AVAILABLE = False


@dataclass(frozen=True)
class GrammarSpec:
    """Declarative description of how to read one language's syntax tree."""

    language: str
    module: str
    import_nodes: Tuple[str, ...] = ()
    class_nodes: Tuple[str, ...] = ()
    function_nodes: Tuple[str, ...] = ()
    aliases: Tuple[str, ...] = ()
    value_function_nodes: Tuple[str, ...] = ()
    value_function_types: Tuple[str, ...] = ()


_SPECS: Tuple[GrammarSpec, ...] = (
    GrammarSpec(
        language="python",
        module="tree_sitter_python",
        import_nodes=("import_statement", "import_from_statement"),
        class_nodes=("class_definition",),
        function_nodes=("function_definition",),
        aliases=("py", "python3"),
    ),
    GrammarSpec(
        language="javascript",
        module="tree_sitter_javascript",
        import_nodes=("import_statement",),
        class_nodes=("class_declaration", "class"),
        function_nodes=(
            "function_declaration",
            "function_expression",
            "generator_function_declaration",
            "method_definition",
        ),
        aliases=("js", "jsx", "node"),
        value_function_nodes=("variable_declarator",),
        value_function_types=("arrow_function", "function", "function_expression"),
    ),
    GrammarSpec(
        language="typescript",
        module="tree_sitter_typescript",
        import_nodes=("import_statement",),
        class_nodes=("class_declaration", "interface_declaration"),
        function_nodes=(
            "function_declaration",
            "function_signature",
            "method_definition",
            "method_signature",
        ),
        aliases=("ts", "tsx"),
        value_function_nodes=("variable_declarator",),
        value_function_types=("arrow_function", "function", "function_expression"),
    ),
    GrammarSpec(
        language="java",
        module="tree_sitter_java",
        import_nodes=("import_declaration",),
        class_nodes=(
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
        ),
        function_nodes=("method_declaration", "constructor_declaration"),
    ),
    GrammarSpec(
        language="go",
        module="tree_sitter_go",
        # `import_spec` is the individual entry inside a grouped `import ( ...
        import_nodes=("import_declaration", "import_spec"),
        class_nodes=("type_spec",),
        function_nodes=("function_declaration", "method_declaration"),
        aliases=("golang",),
    ),
    GrammarSpec(
        language="rust",
        module="tree_sitter_rust",
        import_nodes=("use_declaration", "extern_crate_declaration"),
        class_nodes=("struct_item", "enum_item", "trait_item", "impl_item"),
        function_nodes=("function_item",),
        aliases=("rs",),
    ),
    GrammarSpec(
        language="c",
        module="tree_sitter_c",
        import_nodes=("preproc_include",),
        class_nodes=("struct_specifier", "union_specifier", "enum_specifier"),
        function_nodes=("function_definition",),
    ),
    GrammarSpec(
        language="cpp",
        module="tree_sitter_cpp",
        import_nodes=("preproc_include", "using_declaration"),
        class_nodes=(
            "class_specifier",
            "struct_specifier",
            "namespace_definition",
        ),
        function_nodes=("function_definition", "template_declaration"),
        aliases=("c++", "cxx", "cc"),
    ),
    GrammarSpec(
        language="csharp",
        module="tree_sitter_c_sharp",
        import_nodes=("using_directive",),
        class_nodes=(
            "class_declaration",
            "interface_declaration",
            "struct_declaration",
            "record_declaration",
        ),
        function_nodes=("method_declaration", "constructor_declaration"),
        aliases=("c#", "cs"),
    ),
    GrammarSpec(
        language="ruby",
        module="tree_sitter_ruby",
        import_nodes=("call",),  # `require`/`require_relative` are calls
        class_nodes=("class", "module"),
        function_nodes=("method", "singleton_method"),
        aliases=("rb",),
    ),
    GrammarSpec(
        language="php",
        module="tree_sitter_php",
        import_nodes=("namespace_use_declaration", "require_expression"),
        class_nodes=(
            "class_declaration",
            "interface_declaration",
            "trait_declaration",
        ),
        function_nodes=("function_definition", "method_declaration"),
    ),
    GrammarSpec(
        language="kotlin",
        module="tree_sitter_kotlin",
        import_nodes=("import_header",),
        class_nodes=("class_declaration", "object_declaration"),
        function_nodes=("function_declaration",),
        aliases=("kt",),
    ),
    GrammarSpec(
        language="scala",
        module="tree_sitter_scala",
        import_nodes=("import_declaration",),
        class_nodes=("class_definition", "object_definition", "trait_definition"),
        function_nodes=("function_definition",),
    ),
    GrammarSpec(
        language="bash",
        module="tree_sitter_bash",
        import_nodes=("command",),
        class_nodes=(),
        function_nodes=("function_definition",),
        aliases=("sh", "shell", "zsh"),
    ),
)


_SPEC_BY_NAME: Dict[str, GrammarSpec] = {}
for _spec in _SPECS:
    _SPEC_BY_NAME[_spec.language] = _spec
    for _alias in _spec.aliases:
        _SPEC_BY_NAME[_alias] = _spec


def normalize_language(name: str) -> str:
    """Map an alias (py, c++, golang) to its canonical name."""
    key = (name or "").strip().lower()
    spec = _SPEC_BY_NAME.get(key)
    return spec.language if spec else key


def is_available() -> bool:
    """True when the tree_sitter core runtime is importable."""
    return _TS_AVAILABLE


def get_spec(language: str) -> Optional[GrammarSpec]:
    return _SPEC_BY_NAME.get((language or "").strip().lower())


def _build_language(module_name: str):
    module = importlib.import_module(module_name)

    factory = None
    for attr in ("language", "language_typescript", "language_php"):
        candidate = getattr(module, attr, None)
        if callable(candidate):
            factory = candidate
            break
    if factory is None:
        raise AttributeError(f"{module_name} exposes no language() factory")

    pointer = factory()
    try:
        return Language(pointer)  # type: ignore[misc]
    except TypeError:
        # Legacy signature: Language(ptr, name)
        return Language(pointer, module_name)  # type: ignore[misc]


@lru_cache(maxsize=None)
def _load(language: str):
    """Return a cached (Language, GrammarSpec) pair, or None."""
    if not _TS_AVAILABLE:
        return None

    spec = get_spec(language)
    if spec is None:
        return None

    try:
        ts_language = _build_language(spec.module)
    except Exception as exc:  # noqa: BLE001 - wheel simply not installed
        logger.debug(
            "Tree-sitter grammar for '%s' unavailable (%s).", spec.language, exc
        )
        return None

    logger.info("Tree-sitter grammar loaded for '%s'.", spec.language)
    return ts_language, spec


def get_parser(language: str):
    """Return (Parser, GrammarSpec) for language, or None."""
    loaded = _load(normalize_language(language))
    if loaded is None:
        return None

    ts_language, spec = loaded
    try:
        parser = Parser()  # type: ignore[misc]
        # The modern API assigns the property; older builds take it positionally.
        try:
            parser.language = ts_language
        except AttributeError:  # pragma: no cover - very old wheels
            parser = Parser(ts_language)  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not construct parser for '%s': %s", language, exc)
        return None

    return parser, spec


@dataclass
class Capabilities:
    """Which languages actually have a working Tree-sitter grammar loaded."""

    runtime_available: bool
    parsed: List[str] = field(default_factory=list)
    regex_fallback: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "tree_sitter_runtime": self.runtime_available,
            "ast_parsed_languages": sorted(self.parsed),
            "regex_fallback_languages": sorted(self.regex_fallback),
            "ast_language_count": len(self.parsed),
            "declared_language_count": len(self.parsed) + len(self.regex_fallback),
        }


def capabilities() -> Capabilities:
    """Probe every declared grammar and report what is genuinely available."""
    caps = Capabilities(runtime_available=_TS_AVAILABLE)
    for spec in _SPECS:
        if _load(spec.language) is not None:
            caps.parsed.append(spec.language)
        else:
            caps.regex_fallback.append(spec.language)
    return caps


def declared_languages() -> List[str]:
    """All canonical language names the registry knows how to describe."""
    return [spec.language for spec in _SPECS]
