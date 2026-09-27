"""Signature introspection and dummy-input synthesis."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("arcas.agents.introspect")


# Data model
@dataclass
class Param:
    name: str
    annotation: Optional[str] = None
    has_default: bool = False
    kind: str = "positional"  # positional | keyword_only | var_positional | var_keyword


@dataclass
class FunctionSig:
    name: str
    params: list[Param] = field(default_factory=list)
    class_name: Optional[str] = None  # None => module-level function
    is_static: bool = False
    is_classmethod: bool = False
    returns: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        return f"{self.class_name}.{self.name}" if self.class_name else self.name

    def required_params(self) -> list[Param]:
        """Params a caller must supply (drops self/cls, defaults and *varargs)."""
        out = []
        for p in self.params:
            if p.kind in ("var_positional", "var_keyword"):
                continue
            if p.has_default:
                continue
            out.append(p)
        return out


# AST extraction
def _annotation_to_str(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - very old ast without unparse
        return getattr(node, "id", None)


def _params_from_args(args: ast.arguments) -> list[Param]:
    params: list[Param] = []

    posonly = getattr(args, "posonlyargs", [])
    positional = list(posonly) + list(args.args)
    # defaults align to the tail of `positional`
    n_defaults = len(args.defaults)
    default_offset = len(positional) - n_defaults

    for i, a in enumerate(positional):
        params.append(
            Param(
                name=a.arg,
                annotation=_annotation_to_str(a.annotation),
                has_default=i >= default_offset,
                kind="positional",
            )
        )

    if args.vararg:
        params.append(Param(name=args.vararg.arg, kind="var_positional"))

    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        params.append(
            Param(
                name=a.arg,
                annotation=_annotation_to_str(a.annotation),
                has_default=d is not None,
                kind="keyword_only",
            )
        )

    if args.kwarg:
        params.append(Param(name=args.kwarg.arg, kind="var_keyword"))

    return params


def _decorator_names(node) -> set[str]:
    names = set()
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Name):
            names.add(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.add(dec.attr)
    return names


def extract_signatures(source_code: str) -> list[FunctionSig]:
    """Return signatures for top-level functions and public methods."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        logger.info("Signature extraction skipped - source did not parse: %s", exc)
        return []

    sigs: list[FunctionSig] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            sigs.append(
                FunctionSig(
                    name=node.name,
                    params=_params_from_args(node.args),
                    returns=_annotation_to_str(node.returns),
                )
            )
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if sub.name.startswith("_") and sub.name != "__init__":
                    continue
                decos = _decorator_names(sub)
                params = _params_from_args(sub.args)
                is_static = "staticmethod" in decos
                is_cls = "classmethod" in decos
                # Drop the implicit self / cls receiver for instance & class methods
                if not is_static and params and params[0].name in ("self", "cls"):
                    params = params[1:]
                sigs.append(
                    FunctionSig(
                        name=sub.name,
                        params=params,
                        class_name=node.name,
                        is_static=is_static,
                        is_classmethod=is_cls,
                        returns=_annotation_to_str(sub.returns),
                    )
                )

    return sigs


# Dummy value synthesis Tier 1 - annotation driven.
_ANNOTATION_DUMMIES: dict[str, str] = {
    "int": "1",
    "float": "1.5",
    "complex": "1j",
    "str": "'sample'",
    "bytes": "b'sample'",
    "bytearray": "bytearray(b'sample')",
    "bool": "True",
    "list": "[1, 2, 3]",
    "List": "[1, 2, 3]",
    "tuple": "(1, 2)",
    "Tuple": "(1, 2)",
    "dict": "{'key': 'value'}",
    "Dict": "{'key': 'value'}",
    "set": "{1, 2, 3}",
    "Set": "{1, 2, 3}",
    "frozenset": "frozenset({1, 2})",
    "None": "None",
    "Any": "'sample'",
    "object": "object()",
}

# Tier 2 - name-driven heuristics for un-annotated params.
_NAME_HEURISTICS: list[tuple[tuple[str, ...], str]] = [
    (("email", "e_mail"), "'user@example.com'"),
    (("url", "uri", "endpoint", "href"), "'https://example.com'"),
    (("path", "file", "filename", "filepath", "dir"), "'sample.txt'"),
    (("password", "passwd", "secret", "token", "apikey", "api_key"), "'s3cr3t-dummy'"),
    (("username", "user", "login"), "'testuser'"),
    (("name", "label", "title", "key"), "'sample'"),
    (("query", "sql", "search", "term"), "'sample'"),
    (("html", "markup", "template"), "'<p>sample</p>'"),
    (("json", "payload", "body"), "'{\"k\": \"v\"}'"),
    (("date", "time", "timestamp", "datetime"), "'2024-01-01'"),
    (("count", "num", "n_", "size", "length", "limit", "offset", "index", "idx", "age", "qty"), "3"),
    (("amount", "price", "rate", "ratio", "score", "pct", "percent"), "1.5"),
    (("id",), "1"),
    (("is_", "has_", "enable", "flag", "active", "valid", "verbose", "debug"), "True"),
    (("items", "values", "list", "array", "rows", "records", "elements", "nums", "numbers", "data"), "[1, 2, 3]"),
    (("options", "config", "params", "kwargs", "mapping", "headers", "meta"), "{'key': 'value'}"),
    (("text", "message", "msg", "content", "input", "value", "string", "s", "comment", "description"), "'sample'"),
]

_TRUTHY_PREFIXES = ("is_", "has_", "should_", "can_", "enable", "allow")

_NUMERIC_SHORT_NAMES = set("abcdefghijklmnpqrstuvwz") | {
    "aa", "bb", "xx", "yy", "nn",
}


def synthesize_value(param: Param, counter: Optional[list[int]] = None) -> str:
    """Return a source-code literal that structurally satisfies param."""
    def _next_int() -> str:
        if counter is None:
            return "2"
        counter[0] += 1
        return str(counter[0])

    ann = (param.annotation or "").strip()
    if ann:
        # Optional[X] / X | None -> synthesize X
        root = ann
        if root.startswith("Optional[") and root.endswith("]"):
            root = root[len("Optional["):-1]
        root = root.split("[", 1)[0].split("|", 1)[0].split(".")[-1].strip()
        if root in ("int",):
            return _next_int()
        if root in _ANNOTATION_DUMMIES:
            return _ANNOTATION_DUMMIES[root]
        # Unknown / user-defined class annotation - fall through to name rules, then to a permissive default.

    lname = param.name.lower()

    # Short numeric-looking identifiers take priority over the string fallback.
    if not ann and lname in _NUMERIC_SHORT_NAMES:
        return _next_int()

    for keys, value in _NAME_HEURISTICS:
        if any(k in lname for k in keys):
            if value == "3":  # numeric heuristic bucket -> keep values distinct
                return _next_int()
            return value

    if any(lname.startswith(p) for p in _TRUTHY_PREFIXES):
        return "True"

    # Last resort: a string is accepted by the widest range of Python code.
    return "'sample'"


def build_call_arguments(sig: FunctionSig) -> tuple[str, dict[str, str]]:
    """Build the argument source for calling sig with dummy values."""
    parts: list[str] = []
    chosen: dict[str, str] = {}
    counter = [1]  # mutable seed so numeric params get 2, 3, 4, ...
    for p in sig.required_params():
        value = synthesize_value(p, counter)
        chosen[p.name] = value
        if p.kind == "keyword_only":
            parts.append(f"{p.name}={value}")
        else:
            parts.append(value)
    return ", ".join(parts), chosen


# Smoke-test code generation
_SMOKE_HEADER = '''"""Auto-generated structural smoke tests (ARCAS).

These tests are synthesised deterministically from the function signatures in
the module under test. Each one calls a function with dummy arguments shaped to
match its declared parameters and asserts it is *structurally* callable. A
domain exception (ValueError, ZeroDivisionError, KeyError, ...) counts as a
PASS - it proves the function executed and validated the input itself. Only a
signature/att​ribute mismatch (TypeError, NameError, AttributeError, ImportError)
is treated as a FAILURE.
"""
import pytest
import module_under_test as _mut

# Unambiguous structural failures - the callable could not even be reached
# with the supplied shape.
_STRUCTURAL_ERRORS = (NameError, AttributeError, ImportError, IndentationError)

# TypeError is ambiguous: it can mean a call-arity/keyword mismatch (structural,
# should FAIL) or an operation inside the function that rejected the dummy value
# (domain, should PASS). We treat it as structural only when the message clearly
# points at the call boundary.
_ARITY_MARKERS = (
    "positional argument",
    "keyword argument",
    "required argument",
    "takes no arguments",
    "got an unexpected",
    "missing",
)


def _is_arity_error(exc):
    if not isinstance(exc, TypeError):
        return False
    msg = str(exc).lower()
    return any(marker in msg for marker in _ARITY_MARKERS)
'''


def _smoke_test_for(sig: FunctionSig) -> str:
    call_args, _ = build_call_arguments(sig)
    safe = sig.qualified_name.replace(".", "_")

    if sig.class_name and not sig.is_static and not sig.is_classmethod:
        return f'''

def test_smoke_{safe}():
    try:
        _instance = _mut.{sig.class_name}()
    except _STRUCTURAL_ERRORS:
        pytest.skip("{sig.class_name} requires constructor arguments; skipping smoke test")
        return
    except Exception:
        pytest.skip("{sig.class_name}() could not be instantiated for smoke testing")
        return
    try:
        _instance.{sig.name}({call_args})
    except _STRUCTURAL_ERRORS as exc:
        pytest.fail("Signature mismatch calling {sig.qualified_name}: " + repr(exc))
    except TypeError as exc:
        if _is_arity_error(exc):
            pytest.fail("Arity mismatch calling {sig.qualified_name}: " + repr(exc))
        # else: the method ran; the operands just did not support the operation.
    except Exception:
        # Domain exception -> the method ran and rejected the dummy input itself.
        pass
'''

    target = (
        f"_mut.{sig.class_name}.{sig.name}"
        if sig.class_name
        else f"_mut.{sig.name}"
    )
    return f'''

def test_smoke_{safe}():
    try:
        {target}({call_args})
    except _STRUCTURAL_ERRORS as exc:
        pytest.fail("Signature mismatch calling {sig.qualified_name}: " + repr(exc))
    except TypeError as exc:
        if _is_arity_error(exc):
            pytest.fail("Arity mismatch calling {sig.qualified_name}: " + repr(exc))
        # else: the callable ran; the operands just did not support the operation.
    except Exception:
        # Domain exception -> the callable ran and rejected the dummy input itself.
        pass
'''


def generate_smoke_tests(source_code: str) -> tuple[str, list[FunctionSig]]:
    """Return (smoke_test_source, signatures) for source_code."""
    sigs = extract_signatures(source_code)
    if not sigs:
        return "", []

    body = _SMOKE_HEADER + "".join(_smoke_test_for(s) for s in sigs)
    return body, sigs


def describe_signatures(sigs: list[FunctionSig]) -> str:
    """Human-readable one-liner per signature, for prompts and narration."""
    lines = []
    for s in sigs:
        rendered = []
        for p in s.params:
            prefix = {"var_positional": "*", "var_keyword": "**"}.get(p.kind, "")
            piece = f"{prefix}{p.name}"
            if p.annotation:
                piece += f": {p.annotation}"
            if p.has_default:
                piece += "=…"
            rendered.append(piece)
        sig_str = f"{s.qualified_name}({', '.join(rendered)})"
        if s.returns:
            sig_str += f" -> {s.returns}"
        lines.append(sig_str)
    return "\n".join(lines)
