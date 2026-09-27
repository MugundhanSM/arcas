"""Curated knowledge corpus."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, List

LANGUAGES = [
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "ruby",
    "php",
    "c",
    "cpp",
    "csharp",
]


# OWASP Top 10 (2021) - one base entry, expanded per language.
OWASP_TOP_10 = [
    (
        "A01:2021",
        "Broken Access Control",
        "Restrict access server-side; deny by default; enforce record "
        "ownership; never rely on hiding UI elements. Verify authorization on "
        "every request.",
        ["access-control", "authorization"],
    ),
    (
        "A02:2021",
        "Cryptographic Failures",
        "Encrypt sensitive data in transit and at rest; use strong, current "
        "algorithms (AES-GCM, SHA-256+, argon2/bcrypt); never roll your own "
        "crypto; disable weak protocols.",
        ["crypto", "encryption", "tls"],
    ),
    (
        "A03:2021",
        "Injection",
        "Use parameterized queries, ORMs, and safe APIs; validate and escape "
        "all untrusted input; never concatenate input into SQL, shell, or "
        "HTML.",
        ["injection", "sql", "xss", "command"],
    ),
    (
        "A04:2021",
        "Insecure Design",
        "Apply threat modeling, secure design patterns, and reference "
        "architectures; establish security requirements up front; use defense "
        "in depth.",
        ["design", "threat-model"],
    ),
    (
        "A05:2021",
        "Security Misconfiguration",
        "Harden defaults; remove unused features; patch promptly; disable "
        "verbose errors in production; review cloud and framework "
        "configuration.",
        ["configuration", "hardening"],
    ),
    (
        "A06:2021",
        "Vulnerable and Outdated Components",
        "Inventory dependencies; track CVEs; update regularly; remove unused "
        "libraries; obtain components from trusted sources.",
        ["dependencies", "cve", "supply-chain"],
    ),
    (
        "A07:2021",
        "Identification and Authentication Failures",
        "Enforce MFA; rate-limit and lock accounts; use secure session "
        "management; never hard-code credentials; store passwords with "
        "argon2/bcrypt.",
        ["authentication", "session", "credentials"],
    ),
    (
        "A08:2021",
        "Software and Data Integrity Failures",
        "Verify integrity with signatures; avoid insecure deserialization; "
        "secure CI/CD; use trusted repositories and lockfiles.",
        ["integrity", "deserialization", "ci-cd"],
    ),
    (
        "A09:2021",
        "Security Logging and Monitoring Failures",
        "Log security events with context; protect logs; monitor and alert; "
        "ensure auditability and incident response readiness.",
        ["logging", "monitoring", "audit"],
    ),
    (
        "A10:2021",
        "Server-Side Request Forgery (SSRF)",
        "Validate and allow-list outbound URLs; block internal address "
        "ranges; disable unused URL schemes; segment networks.",
        ["ssrf", "network"],
    ),
]


# CWE Top 25 (representative subset of the most dangerous weaknesses).
CWE_TOP_25 = [
    ("CWE-79", "Cross-site Scripting", "Escape output; use templating "
     "auto-escaping; apply CSP."),
    ("CWE-787", "Out-of-bounds Write", "Validate buffer sizes; use safe "
     "memory functions and bounds checks."),
    ("CWE-89", "SQL Injection", "Use parameterized queries / prepared "
     "statements."),
    ("CWE-416", "Use After Free", "Null out freed pointers; use RAII / smart "
     "pointers."),
    ("CWE-78", "OS Command Injection", "Avoid shells; pass argument lists; "
     "validate input."),
    ("CWE-20", "Improper Input Validation", "Validate type, length, format, "
     "and range of all input."),
    ("CWE-125", "Out-of-bounds Read", "Check indices and lengths before "
     "reading memory."),
    ("CWE-22", "Path Traversal", "Canonicalize and allow-list paths; reject "
     "'..' sequences."),
    ("CWE-352", "Cross-Site Request Forgery", "Use anti-CSRF tokens and "
     "SameSite cookies."),
    ("CWE-434", "Unrestricted Upload of Dangerous File Type", "Validate file "
     "type and content; store outside webroot."),
    ("CWE-862", "Missing Authorization", "Enforce authorization checks on "
     "every protected resource."),
    ("CWE-476", "NULL Pointer Dereference", "Check for null before "
     "dereferencing."),
    ("CWE-287", "Improper Authentication", "Use vetted auth frameworks and "
     "MFA."),
    ("CWE-190", "Integer Overflow or Wraparound", "Use checked arithmetic and "
     "wider types."),
    ("CWE-502", "Deserialization of Untrusted Data", "Use safe loaders; never "
     "deserialize untrusted bytes."),
    ("CWE-77", "Command Injection", "Use safe APIs; never build commands from "
     "untrusted input."),
    ("CWE-119", "Improper Restriction of Memory Buffer", "Validate bounds; "
     "use memory-safe constructs."),
    ("CWE-798", "Use of Hard-coded Credentials", "Load secrets from a vault "
     "or environment, never source."),
    ("CWE-918", "Server-Side Request Forgery", "Allow-list outbound hosts; "
     "block internal ranges."),
    ("CWE-306", "Missing Authentication for Critical Function", "Require auth "
     "for all sensitive operations."),
    ("CWE-362", "Race Condition", "Use locks / atomic operations on shared "
     "state."),
    ("CWE-269", "Improper Privilege Management", "Apply least privilege; drop "
     "privileges early."),
    ("CWE-94", "Code Injection", "Never eval untrusted input; use safe "
     "evaluators."),
    ("CWE-863", "Incorrect Authorization", "Verify authorization logic "
     "against the access model."),
    ("CWE-276", "Incorrect Default Permissions", "Set restrictive default "
     "permissions on files and resources."),
]


# PEP 8 major rules.
PEP8_RULES = [
    ("Indentation", "Use 4 spaces per indentation level; never tabs."),
    ("Maximum Line Length", "Limit lines to 79 characters (72 for "
     "docstrings)."),
    ("Blank Lines", "Two blank lines around top-level defs; one around "
     "methods."),
    ("Imports", "One import per line; group stdlib, third-party, local."),
    ("Module Imports Position", "Place imports at the top of the file."),
    ("Whitespace in Expressions", "Avoid extraneous whitespace inside "
     "brackets and before commas."),
    ("Trailing Commas", "Use trailing commas in multi-line collections."),
    ("Comments", "Keep comments current; write complete sentences."),
    ("Block Comments", "Indent block comments to the code they describe."),
    ("Inline Comments", "Use sparingly; separate with two spaces."),
    ("Documentation Strings", "Write docstrings for public modules, classes "
     "and functions."),
    ("Naming: Functions", "Use lowercase_with_underscores."),
    ("Naming: Classes", "Use CapWords / CamelCase."),
    ("Naming: Constants", "Use UPPER_CASE_WITH_UNDERSCORES."),
    ("Naming: Variables", "Use descriptive lowercase names."),
    ("Naming: Protected", "Prefix non-public attributes with a single "
     "underscore."),
    ("Naming: Private", "Use a leading double underscore to invoke name "
     "mangling."),
    ("Comparisons to None", "Use 'is' / 'is not', never equality."),
    ("Boolean Comparisons", "Don't compare booleans to True/False with =="),
    ("Exception Handling", "Catch specific exceptions, not bare except."),
    ("Return Consistency", "Be consistent: always return a value or never."),
    ("String Quotes", "Pick one quote style and stay consistent."),
    ("Whitespace Around Operators", "Surround binary operators with a single "
     "space."),
    ("Default Argument Values", "Don't use mutable defaults like [] or {}."),
    ("Type Hints", "Annotate public function signatures where useful."),
    ("Function Length", "Keep functions short and single-purpose."),
    ("Nested Functions", "Avoid deep nesting; extract helpers."),
    ("List Comprehensions", "Prefer comprehensions over map/filter when "
     "clearer."),
    ("Context Managers", "Use 'with' for files and locks."),
    ("f-strings", "Prefer f-strings for readable interpolation."),
]


# Clean Code principles (Robert C. Martin).
CLEAN_CODE = [
    ("Meaningful Names", "Names should reveal intent and avoid disinformation."),
    ("Pronounceable Names", "Use names you can say and search for."),
    ("Functions Should Be Small", "A function should be small and do one "
     "thing."),
    ("Single Responsibility", "A function/class should have one reason to "
     "change."),
    ("One Level of Abstraction", "Keep a function at a single abstraction "
     "level."),
    ("Few Arguments", "Prefer zero to three arguments; avoid flag args."),
    ("No Side Effects", "Functions should not have hidden side effects."),
    ("Command Query Separation", "A function either does something or answers "
     "something."),
    ("DRY", "Don't Repeat Yourself; remove duplication."),
    ("Prefer Exceptions", "Use exceptions over error codes."),
    ("Don't Return Null", "Avoid returning or passing null."),
    ("Comments Explain Why", "Good code is self-documenting; comment intent."),
    ("Avoid Noise Comments", "Remove redundant or misleading comments."),
    ("Consistent Formatting", "Apply consistent vertical and horizontal "
     "formatting."),
    ("Encapsulate Conditionals", "Extract complex booleans into named "
     "functions."),
    ("Avoid Negative Conditionals", "Prefer positive conditionals for "
     "clarity."),
    ("Class Cohesion", "Keep classes focused with high cohesion."),
    ("Law of Demeter", "Talk to friends, not strangers; avoid train wrecks."),
    ("Error Handling Is One Thing", "Separate error handling from logic."),
    ("Boundaries", "Wrap third-party APIs behind your own interfaces."),
    ("Unit Tests Are First-Class", "Keep tests clean, fast, and "
     "independent."),
    ("One Assert Per Concept", "Test a single concept per test."),
    ("Fail Fast", "Validate preconditions early and clearly."),
    ("Avoid Premature Optimization", "Optimize only with measurements."),
    ("Leave It Cleaner", "Follow the Boy Scout Rule: improve as you go."),
]


# Per-language secure-coding patterns (15 patterns expanded across languages).
SECURE_PATTERNS = [
    ("Input Validation", "Validate all external input for type, length, "
     "format, and range before use."),
    ("Output Encoding", "Encode output for its context (HTML, URL, SQL, "
     "shell)."),
    ("Parameterized Queries", "Use prepared statements for all database "
     "access."),
    ("Avoid Shell Execution", "Avoid invoking a shell; pass argument arrays "
     "to process APIs."),
    ("Secrets Management", "Load secrets from environment or a vault; never "
     "hard-code."),
    ("Strong Cryptography", "Use vetted algorithms; avoid MD5/SHA1/DES/ECB."),
    ("Secure Random", "Use a cryptographically secure RNG for tokens and "
     "keys."),
    ("Least Privilege", "Run with the minimum permissions required."),
    ("Safe Deserialization", "Never deserialize untrusted data with unsafe "
     "loaders."),
    ("TLS Verification", "Always verify certificates; never disable TLS "
     "checks."),
    ("Error Handling", "Catch specific errors; never leak stack traces to "
     "users."),
    ("Authentication", "Use established auth libraries; enforce MFA and "
     "lockouts."),
    ("Authorization", "Check authorization server-side on every request."),
    ("Logging Hygiene", "Log security events but never secrets or PII."),
    ("Dependency Hygiene", "Pin and update dependencies; scan for CVEs."),
]


def _build_entries() -> list[dict]:
    entries: list[dict] = []

    # OWASP × language
    for code, title, content, tags in OWASP_TOP_10:
        for lang in LANGUAGES:
            entries.append(
                {
                    "id": f"owasp-{code.lower().replace(':', '-')}-{lang}",
                    "category": "security",
                    "language": lang,
                    "source": "OWASP Top 10 2021",
                    "title": f"{code} {title}",
                    "content": (
                        f"[{lang}] {code} {title}. {content}"
                    ),
                    "tags": tags + ["owasp", lang],
                }
            )

    # CWE Top 25
    for cwe_id, title, content in CWE_TOP_25:
        entries.append(
            {
                "id": f"{cwe_id.lower()}",
                "category": "security",
                "language": "all",
                "source": "CWE Top 25",
                "title": f"{cwe_id}: {title}",
                "content": f"{cwe_id} {title}. {content}",
                "tags": ["cwe", "weakness"],
            }
        )

    # PEP 8
    for rule, content in PEP8_RULES:
        entries.append(
            {
                "id": f"pep8-{rule.lower().replace(' ', '-').replace(':', '')}",
                "category": "style",
                "language": "python",
                "source": "PEP 8",
                "title": f"PEP 8 - {rule}",
                "content": f"PEP 8 {rule}: {content}",
                "tags": ["pep8", "style", "python"],
            }
        )

    # Clean code
    for principle, content in CLEAN_CODE:
        entries.append(
            {
                "id": f"clean-{principle.lower().replace(' ', '-')}",
                "category": "quality",
                "language": "all",
                "source": "Clean Code (R. C. Martin)",
                "title": f"Clean Code - {principle}",
                "content": f"{principle}: {content}",
                "tags": ["clean-code", "quality"],
            }
        )

    # Secure patterns × language
    for pattern, content in SECURE_PATTERNS:
        for lang in LANGUAGES:
            entries.append(
                {
                    "id": (
                        f"pattern-{pattern.lower().replace(' ', '-')}-{lang}"
                    ),
                    "category": "security",
                    "language": lang,
                    "source": "Secure Coding Patterns",
                    "title": f"{pattern} ({lang})",
                    "content": f"[{lang}] {pattern}: {content}",
                    "tags": ["secure-pattern", lang],
                }
            )

    return entries

@lru_cache(maxsize=1)
def build_corpus() -> List[Dict]:
    """Return the full corpus, built once per process."""
    return _build_entries()


def corpus_stats() -> Dict:
    """Breakdown by category/source, used by /health and the evaluation."""
    entries = build_corpus()
    by_category: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    by_language: Dict[str, int] = {}
    for entry in entries:
        by_category[entry["category"]] = by_category.get(entry["category"], 0) + 1
        by_source[entry["source"]] = by_source.get(entry["source"], 0) + 1
        by_language[entry["language"]] = by_language.get(entry["language"], 0) + 1
    return {
        "total_entries": len(entries),
        "by_category": dict(sorted(by_category.items())),
        "by_source": dict(sorted(by_source.items())),
        "by_language": dict(sorted(by_language.items())),
    }
