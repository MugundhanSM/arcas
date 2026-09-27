"""Benchmark dataset adapters."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.core.logging import get_logger

logger = get_logger("arcas.evaluation.datasets")


class Provenance(str, Enum):
    EXTERNAL = "external"
    LOCAL_SUBSET = "local_subset"


@dataclass
class BenchmarkSample:
    """One labelled benchmark item, normalised across both datasets."""

    sample_id: str
    language: str
    code: str
    # CWE identifiers expected to be present, e.g. {"CWE-89"}.
    expected_cwes: Set[str] = field(default_factory=set)
    # ARCAS security categories expected, e.g. {"sql_injection"}.
    expected_categories: Set[str] = field(default_factory=set)
    is_safe: bool = False
    dataset: str = "unknown"
    provenance: Provenance = Provenance.LOCAL_SUBSET
    # For CodeReviewer: the human reviewer's comment on this diff.
    reference_comment: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.sample_id,
            "dataset": self.dataset,
            "provenance": self.provenance.value,
            "language": self.language,
            "expected_cwes": sorted(self.expected_cwes),
            "expected_categories": sorted(self.expected_categories),
            "is_safe": self.is_safe,
        }


CWE_TO_CATEGORY: Dict[str, str] = {
    "CWE-78": "command_injection",
    "CWE-77": "command_injection",
    "CWE-88": "command_injection",
    "CWE-89": "sql_injection",
    "CWE-79": "xss",
    "CWE-502": "deserialization",
    "CWE-327": "weak_crypto",
    "CWE-328": "weak_crypto",
    "CWE-326": "weak_crypto",
    "CWE-798": "hardcoded_secret",
    "CWE-259": "hardcoded_secret",
    "CWE-321": "hardcoded_secret",
    "CWE-94": "code_injection",
    "CWE-95": "code_injection",
    "CWE-22": "path_traversal",
    "CWE-23": "path_traversal",
    "CWE-36": "path_traversal",
    "CWE-918": "ssrf",
    "CWE-330": "insecure_random",
    "CWE-338": "insecure_random",
    "CWE-611": "xxe",
    "CWE-352": "csrf",
    "CWE-295": "cert_validation",
    "CWE-732": "permissions",
    "CWE-120": "buffer_overflow",
    "CWE-119": "buffer_overflow",
    "CWE-787": "buffer_overflow",
    "CWE-125": "buffer_overflow",
    "CWE-476": "null_dereference",
    "CWE-190": "integer_overflow",
    "CWE-401": "resource_leak",
    "CWE-772": "resource_leak",
}


def categories_for(cwes: Set[str]) -> Set[str]:
    return {CWE_TO_CATEGORY[c] for c in cwes if c in CWE_TO_CATEGORY}


# SATE IV / Juliet adapter

# Juliet encodes the CWE in the filename: CWE89_SQL_Injection__...java.
_JULIET_CWE_RE = re.compile(r"CWE(\d+)_", re.IGNORECASE)
_JULIET_SUFFIX_TO_LANGUAGE = {
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".py": "python",
}


def load_sate_iv(root: Optional[str] = None, limit: int = 500) -> List[BenchmarkSample]:
    """Load SATE IV / Juliet test cases from a local extraction."""
    root = root or os.environ.get("ARCAS_SATE_PATH", "")
    if not root:
        return []

    base = Path(root).expanduser()
    if not base.exists():
        logger.warning("SATE IV path %s does not exist; skipping.", base)
        return []

    samples: List[BenchmarkSample] = []
    for path in sorted(base.rglob("*")):
        if len(samples) >= limit:
            break
        if not path.is_file():
            continue
        language = _JULIET_SUFFIX_TO_LANGUAGE.get(path.suffix.lower())
        if language is None:
            continue
        match = _JULIET_CWE_RE.search(path.name)
        if not match:
            continue

        try:
            code = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        cwe = f"CWE-{int(match.group(1))}"
        samples.append(
            BenchmarkSample(
                sample_id=path.name,
                language=language,
                code=code,
                expected_cwes={cwe},
                expected_categories=categories_for({cwe}),
                is_safe=False,
                dataset="SATE IV (Juliet)",
                provenance=Provenance.EXTERNAL,
            )
        )

    logger.info("Loaded %d SATE IV samples from %s.", len(samples), base)
    return samples


# CodeReviewer adapter


def load_codereviewer(
    path: Optional[str] = None, limit: int = 500
) -> List[BenchmarkSample]:
    """Load CodeReviewer records from a local JSONL export."""
    path = path or os.environ.get("ARCAS_CODEREVIEWER_PATH", "")
    if not path:
        return []

    file_path = Path(path).expanduser()
    if not file_path.exists():
        logger.warning("CodeReviewer path %s does not exist; skipping.", file_path)
        return []

    code_keys = ("patch", "code", "oldf", "old_file", "diff", "source")
    comment_keys = ("comment", "msg", "review", "target")

    samples: List[BenchmarkSample] = []
    with file_path.open(encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle):
            if len(samples) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            code = next(
                (record[k] for k in code_keys if record.get(k)), ""
            )
            if not code:
                continue
            comment = next(
                (record[k] for k in comment_keys if record.get(k)), ""
            )

            samples.append(
                BenchmarkSample(
                    sample_id=str(record.get("id", f"cr-{line_no}")),
                    language=str(record.get("lang", "python")).lower(),
                    code=code,
                    # CodeReviewer labels review-worthiness, not CWEs.
                    expected_categories=set(),
                    is_safe=not bool(comment),
                    dataset="CodeReviewer",
                    provenance=Provenance.EXTERNAL,
                    reference_comment=str(comment),
                )
            )

    logger.info("Loaded %d CodeReviewer samples from %s.", len(samples), file_path)
    return samples


# Bundled local subsets (offline fallback)

# Mirrors the CWE coverage of the Juliet suite in miniature.
_SATE_LOCAL: List[BenchmarkSample] = [
    BenchmarkSample(
        sample_id="local-cwe89-java",
        language="java",
        expected_cwes={"CWE-89"},
        dataset="SATE IV (local subset)",
        code=(
            "public class Dao {\n"
            "  public User find(Connection c, String name) throws Exception {\n"
            "    Statement s = c.createStatement();\n"
            '    ResultSet r = s.executeQuery("SELECT * FROM users WHERE n=\'" '
            '+ name + "\'");\n'
            "    return map(r);\n"
            "  }\n"
            "}\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cwe78-c",
        language="c",
        expected_cwes={"CWE-78", "CWE-120"},
        dataset="SATE IV (local subset)",
        code=(
            "#include <stdlib.h>\n"
            "void run(char *userInput) {\n"
            "    char cmd[256];\n"
            '    sprintf(cmd, "ls %s", userInput);\n'
            "    system(cmd);\n"
            "}\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cwe120-c",
        language="c",
        expected_cwes={"CWE-120"},
        dataset="SATE IV (local subset)",
        code=(
            "#include <string.h>\n"
            "void copy(char *src) {\n"
            "    char buf[16];\n"
            "    strcpy(buf, src);\n"
            "}\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cwe22-python",
        language="python",
        expected_cwes={"CWE-22"},
        dataset="SATE IV (local subset)",
        code=(
            "def read(name):\n"
            '    with open("/var/data/" + name) as fh:\n'
            "        return fh.read()\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cwe798-python",
        language="python",
        expected_cwes={"CWE-798"},
        dataset="SATE IV (local subset)",
        code=(
            'DB_PASSWORD = "P@ssw0rd123!"\n'
            "def connect():\n"
            "    return db.connect(password=DB_PASSWORD)\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cwe327-java",
        language="java",
        expected_cwes={"CWE-327"},
        dataset="SATE IV (local subset)",
        code=(
            "public class Hash {\n"
            "  public byte[] digest(byte[] in) throws Exception {\n"
            '    return MessageDigest.getInstance("MD5").digest(in);\n'
            "  }\n"
            "}\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cwe502-python",
        language="python",
        expected_cwes={"CWE-502"},
        dataset="SATE IV (local subset)",
        code="import pickle\ndef load(b):\n    return pickle.loads(b)\n",
    ),
    BenchmarkSample(
        sample_id="local-cwe330-python",
        language="python",
        expected_cwes={"CWE-330"},
        dataset="SATE IV (local subset)",
        code=(
            "import random\n"
            "def token():\n"
            '    return "".join(random.choice("abcdef0123456789") '
            "for _ in range(32))\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-safe-java",
        language="java",
        is_safe=True,
        dataset="SATE IV (local subset)",
        code=(
            "public class Dao {\n"
            "  public User find(Connection c, String name) throws Exception {\n"
            '    PreparedStatement p = c.prepareStatement("SELECT * FROM users '
            'WHERE n=?");\n'
            "    p.setString(1, name);\n"
            "    return map(p.executeQuery());\n"
            "  }\n"
            "}\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-safe-python",
        language="python",
        is_safe=True,
        dataset="SATE IV (local subset)",
        code=(
            "import secrets\n"
            "def token() -> str:\n"
            "    return secrets.token_hex(16)\n"
        ),
    ),
]

for _sample in _SATE_LOCAL:
    _sample.expected_categories = categories_for(_sample.expected_cwes)


# Mirrors CodeReviewer's task shape: a diff plus whether a human reviewer raised a comment on it.
_CODEREVIEWER_LOCAL: List[BenchmarkSample] = [
    BenchmarkSample(
        sample_id="local-cr-1",
        language="python",
        dataset="CodeReviewer (local subset)",
        reference_comment="Use a parameterised query rather than f-string interpolation.",
        code=(
            "def get(cur, uid):\n"
            '    cur.execute(f"SELECT * FROM users WHERE id = {uid}")\n'
            "    return cur.fetchone()\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cr-2",
        language="python",
        dataset="CodeReviewer (local subset)",
        reference_comment="This swallows every exception; narrow the except clause.",
        code=(
            "def load(path):\n"
            "    try:\n"
            "        return open(path).read()\n"
            "    except Exception:\n"
            "        pass\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cr-3",
        language="python",
        dataset="CodeReviewer (local subset)",
        reference_comment="Mutable default argument is shared across calls.",
        code="def add(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n",
    ),
    BenchmarkSample(
        sample_id="local-cr-4",
        language="javascript",
        dataset="CodeReviewer (local subset)",
        reference_comment="Missing await; the promise is never resolved.",
        code=(
            "async function main() {\n"
            "  const data = fetchData();\n"
            "  return data.items;\n"
            "}\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cr-5",
        language="python",
        dataset="CodeReviewer (local subset)",
        is_safe=True,
        code=(
            "def normalise(name: str) -> str:\n"
            '    """Trim and lowercase a user-supplied name."""\n'
            "    return name.strip().lower()\n"
        ),
    ),
    BenchmarkSample(
        sample_id="local-cr-6",
        language="python",
        dataset="CodeReviewer (local subset)",
        is_safe=True,
        code=(
            "from typing import Iterable\n"
            "def total(values: Iterable[float]) -> float:\n"
            "    return sum(values)\n"
        ),
    ),
]


# Public loader


@dataclass
class LoadedDataset:
    name: str
    samples: List[BenchmarkSample]
    provenance: Provenance
    note: str

    def as_dict(self) -> dict:
        return {
            "dataset": self.name,
            "provenance": self.provenance.value,
            "sample_count": len(self.samples),
            "note": self.note,
        }


def load_dataset(name: str, limit: int = 500) -> LoadedDataset:
    """Load a benchmark, preferring external data and falling back locally."""
    key = name.strip().lower().replace(" ", "_")

    if key in ("sate", "sate_iv", "juliet"):
        external = load_sate_iv(limit=limit)
        if external:
            return LoadedDataset(
                name="SATE IV",
                samples=external,
                provenance=Provenance.EXTERNAL,
                note="Loaded from the local SATE IV / Juliet extraction.",
            )
        return LoadedDataset(
            name="SATE IV",
            samples=list(_SATE_LOCAL),
            provenance=Provenance.LOCAL_SUBSET,
            note=(
                "NIST SATE IV was not found; ran a bundled hand-labelled "
                "subset mirroring its CWE coverage. Report these as "
                "'local subset' results, NOT as SATE IV results. Set "
                "ARCAS_SATE_PATH to evaluate on the real suite."
            ),
        )

    if key in ("codereviewer", "code_reviewer"):
        external = load_codereviewer(limit=limit)
        if external:
            return LoadedDataset(
                name="CodeReviewer",
                samples=external,
                provenance=Provenance.EXTERNAL,
                note="Loaded from the local CodeReviewer JSONL export.",
            )
        return LoadedDataset(
            name="CodeReviewer",
            samples=list(_CODEREVIEWER_LOCAL),
            provenance=Provenance.LOCAL_SUBSET,
            note=(
                "CodeReviewer was not found; ran a bundled hand-labelled "
                "subset mirroring its task shape. Report these as "
                "'local subset' results, NOT as CodeReviewer results. Set "
                "ARCAS_CODEREVIEWER_PATH to evaluate on the real dataset."
            ),
        )

    raise ValueError(f"Unknown dataset '{name}'. Use 'sate_iv' or 'codereviewer'.")


def available_datasets() -> List[dict]:
    """Report which benchmarks are externally available in this environment."""
    return [
        {
            "name": "SATE IV",
            "env_var": "ARCAS_SATE_PATH",
            "external_available": bool(load_sate_iv(limit=1)),
        },
        {
            "name": "CodeReviewer",
            "env_var": "ARCAS_CODEREVIEWER_PATH",
            "external_available": bool(load_codereviewer(limit=1)),
        },
    ]
