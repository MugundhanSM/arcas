"""PII detection and redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from app.core.logging import get_logger

logger = get_logger("arcas.guardrails.pii")


@dataclass
class PIIFinding:
    """One detected PII entity, mirroring Presidio's RecognizerResult."""

    entity_type: str
    start: int
    end: int
    score: float
    text: str = ""

    def as_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "start": self.start,
            "end": self.end,
            "score": round(self.score, 2),
        }


@dataclass
class RedactionResult:
    text: str
    findings: List[PIIFinding] = field(default_factory=list)
    engine: str = "pattern"

    @property
    def entity_types(self) -> List[str]:
        return [f.entity_type for f in self.findings]


# Validators - cut the false-positive rate that plain patterns produce


# Issuer Identification Number prefixes and their permitted lengths.
_CARD_SCHEMES: Tuple[Tuple[Tuple[str, ...], Tuple[int, ...]], ...] = (
    (("4",), (13, 16, 19)),  # Visa
    (("51", "52", "53", "54", "55"), (16,)),  # Mastercard
    (tuple(str(n) for n in range(2221, 2721)), (16,)),  # Mastercard 2-series
    (("34", "37"), (15,)),  # Amex
    (("6011", "65"), (16, 19)),  # Discover
    (("644", "645", "646", "647", "648", "649"), (16, 19)),  # Discover
    (("35",), (16, 19)),  # JCB
    (("300", "301", "302", "303", "304", "305", "36", "38"), (14, 16, 19)),  # Diners
    (("50", "56", "57", "58", "6"), (12, 13, 14, 15, 16, 17, 18, 19)),  # Maestro
)


def credit_card_valid(value: str) -> bool:
    """A payment card must pass Luhn and carry a recognised IIN prefix."""
    digits = "".join(c for c in value if c.isdigit())
    if not luhn_valid(digits):
        return False
    for prefixes, lengths in _CARD_SCHEMES:
        if len(digits) in lengths and digits.startswith(prefixes):
            return True
    return False


def luhn_valid(digits: str) -> bool:
    """Standard Luhn checksum used by all major payment card schemes."""
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) < 13:
        return False
    checksum = 0
    parity = len(nums) % 2
    for index, digit in enumerate(nums):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_valid(digits: str) -> bool:
    """Checksum used by the Indian Aadhaar identifier."""
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) != 12:
        return False
    check = 0
    for index, digit in enumerate(reversed(nums)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[index % 8][digit]]
    return check == 0


def _ipv4_is_routable(value: str) -> bool:
    try:
        octets = [int(part) for part in value.split(".")]
    except ValueError:
        return False
    if len(octets) != 4 or any(o > 255 for o in octets):
        return False
    if octets[0] in (0, 127):
        return False
    if octets[0] == 169 and octets[1] == 254:
        return False
    return True


# Deterministic recogniser set

# (entity_type, pattern, base_score, validator)
_RECOGNIZERS: Sequence[Tuple[str, re.Pattern, float, Optional[object]]] = (
    (
        "EMAIL_ADDRESS",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        0.95,
        None,
    ),
    (
        "CREDIT_CARD",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        0.9,
        credit_card_valid,
    ),
    (
        "US_SSN",
        re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
        0.9,
        None,
    ),
    (
        "IN_AADHAAR",
        re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b"),
        0.85,
        verhoeff_valid,
    ),
    (
        "IN_PAN",
        re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        0.8,
        None,
    ),
    (
        "PHONE_NUMBER",
        re.compile(
            r"(?<![\w.])(?:\+\d{1,3}[ -]?)?"
            r"(?:\(\d{3}\)[ -]?|\d{3}[ -])\d{3}[ -]?\d{4}(?![\w.])"
        ),
        0.7,
        None,
    ),
    (
        "IBAN_CODE",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
        0.8,
        None,
    ),
    (
        "PASSPORT",
        re.compile(r"\b[A-PR-WY][1-9]\d\s?\d{4}[1-9]\b"),
        0.6,
        None,
    ),
    (
        "IP_ADDRESS",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
        ),
        0.6,
        _ipv4_is_routable,
    ),
    (
        "AWS_ACCESS_KEY",
        re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b"),
        0.99,
        None,
    ),
    (
        "AWS_SECRET_KEY",
        re.compile(
            r"(?i)aws.{0,20}(?:secret|private).{0,20}['\"]([A-Za-z0-9/+=]{40})['\"]"
        ),
        0.9,
        None,
    ),
    (
        "GITHUB_TOKEN",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
        0.99,
        None,
    ),
    (
        "SLACK_TOKEN",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        0.99,
        None,
    ),
    (
        "STRIPE_KEY",
        re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),
        0.99,
        None,
    ),
    (
        "GOOGLE_API_KEY",
        re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        0.99,
        None,
    ),
    (
        "JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        0.95,
        None,
    ),
    (
        "BEARER_TOKEN",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}\b"),
        0.9,
        None,
    ),
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
            r"[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
        ),
        0.99,
        None,
    ),
    (
        "CONNECTION_STRING",
        re.compile(
            r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)"
            r"://[^\s:@'\"]+:[^\s:@'\"]+@[^\s'\"]+"
        ),
        0.95,
        None,
    ),
    (
        "GENERIC_SECRET",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token)"
            r"\s*[=:]\s*['\"]([^'\"\s]{8,})['\"]"
        ),
        0.75,
        None,
    ),
)


class PatternEngine:
    """Deterministic, validated recogniser set (the no-Presidio tier)."""

    name = "pattern"

    @staticmethod
    def analyze(text: str) -> List[PIIFinding]:
        findings: List[PIIFinding] = []
        for entity_type, pattern, score, validator in _RECOGNIZERS:
            for match in pattern.finditer(text):
                if pattern.groups:
                    start, end = match.span(1)
                    value = match.group(1)
                else:
                    start, end = match.span()
                    value = match.group(0)

                if validator is not None and not validator(value):
                    continue

                findings.append(
                    PIIFinding(
                        entity_type=entity_type,
                        start=start,
                        end=end,
                        score=score,
                        text=value,
                    )
                )
        return findings


class PresidioEngine:
    """Adapter over presidio-analyzer - the implementation the design names."""

    name = "presidio"

    # NER-backed entities.
    NER_ENTITIES = ("PERSON", "LOCATION", "ORGANIZATION", "NRP", "DATE_TIME")

    @staticmethod
    @lru_cache(maxsize=1)
    def _analyzer():
        from presidio_analyzer import AnalyzerEngine  # type: ignore

        return AnalyzerEngine()

    @staticmethod
    def available() -> bool:
        try:
            PresidioEngine._analyzer()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Presidio unavailable: %s", exc)
            return False

    @staticmethod
    def analyze(text: str, language: str = "en") -> List[PIIFinding]:
        analyzer = PresidioEngine._analyzer()
        results = analyzer.analyze(text=text, language=language)
        return [
            PIIFinding(
                entity_type=r.entity_type,
                start=r.start,
                end=r.end,
                score=float(r.score),
                text=text[r.start:r.end],
            )
            for r in results
        ]


class PIIDetector:
    """Front door for Layer 3's PII check."""

    CRITICAL_ENTITIES = frozenset(
        {
            "PRIVATE_KEY",
            "AWS_SECRET_KEY",
            "AWS_ACCESS_KEY",
            "GITHUB_TOKEN",
            "SLACK_TOKEN",
            "STRIPE_KEY",
            "CONNECTION_STRING",
        }
    )

    _presidio_checked = False
    _presidio_ok = False

    @classmethod
    def _presidio_enabled(cls) -> bool:
        if not cls._presidio_checked:
            cls._presidio_checked = True
            cls._presidio_ok = PresidioEngine.available()
            if cls._presidio_ok:
                logger.info("Presidio analyzer active for PII detection.")
            else:
                logger.info(
                    "Presidio not installed; using the deterministic "
                    "recogniser set (NER entities will not be detected)."
                )
        return cls._presidio_ok

    @classmethod
    def engine_name(cls) -> str:
        return "presidio+pattern" if cls._presidio_enabled() else "pattern"

    @classmethod
    def analyze(cls, text: str) -> List[PIIFinding]:
        findings = PatternEngine.analyze(text)

        if cls._presidio_enabled():
            try:
                findings.extend(PresidioEngine.analyze(text))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Presidio analysis failed (%s); patterns only.", exc)

        return cls._resolve_overlaps(findings)

    @staticmethod
    def _resolve_overlaps(findings: List[PIIFinding]) -> List[PIIFinding]:
        """Keep the highest-scoring finding for any overlapping span."""
        ordered = sorted(findings, key=lambda f: (-f.score, f.start, -f.end))
        kept: List[PIIFinding] = []
        for finding in ordered:
            if any(
                finding.start < k.end and k.start < finding.end for k in kept
            ):
                continue
            kept.append(finding)
        return sorted(kept, key=lambda f: f.start)

    @classmethod
    def redact(cls, text: str) -> RedactionResult:
        """Replace every detected entity with a typed placeholder."""
        findings = cls.analyze(text)
        redacted = text
        for finding in sorted(findings, key=lambda f: f.start, reverse=True):
            placeholder = f"<REDACTED_{finding.entity_type}>"
            redacted = redacted[: finding.start] + placeholder + redacted[finding.end:]

        return RedactionResult(
            text=redacted,
            findings=findings,
            engine=cls.engine_name(),
        )

    @classmethod
    def critical_findings(cls, findings: List[PIIFinding]) -> List[PIIFinding]:
        return [f for f in findings if f.entity_type in cls.CRITICAL_ENTITIES]

    @classmethod
    def summary(cls, findings: List[PIIFinding]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for finding in findings:
            counts[finding.entity_type] = counts.get(finding.entity_type, 0) + 1
        return counts
