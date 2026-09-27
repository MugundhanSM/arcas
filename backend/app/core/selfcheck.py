"""SelfCheckGPT hallucination detection."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("arcas.guardrails.selfcheck")


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*\-#])|\n(?=\s*[-*#\d])|\n{2,}")
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Laplace smoothing constant for the unigram model fitted over the samples.
_SMOOTHING = 0.4

# Function words carry no factual claim.
_STOPWORDS = frozenset(
    """a an the this that these those it its is are was were be been being am
    do does did done can could will would shall should may might must have has
    had of to in on at by for with from into onto over under about as and or
    but if then than so such not no nor only very more most much many few
    which who whom whose what when where why how all any both each other some
    use uses used using make makes made get gets got take takes taken give
    gives given call calls called set sets put puts show shows see sees also
    you your we our they their he she his her i me my them us here there now
    because while during before after between within without via per each
    e g ie eg etc"""
    .split()
)

# A token that looks like a code symbol rather than English prose.
_IDENTIFIER_SHAPE = re.compile(
    r"^(?:[a-z]+_[a-z0-9_]+|[a-z]+[A-Z]\w*|[A-Z][a-z]+[A-Z]\w*)$"
)

# Weight split between the identifier channel and the prose channel.
_IDENTIFIER_WEIGHT = 0.75
_PROSE_WEIGHT = 0.25


@dataclass
class SentenceScore:
    text: str
    score: float  # 0 = fully supported by samples, 1 = wholly unsupported
    unsupported_tokens: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "sentence": self.text[:180],
            "hallucination_score": round(self.score, 3),
            "unsupported_tokens": self.unsupported_tokens[:8],
        }


@dataclass
class SelfCheckResult:
    """Outcome of a consistency check."""

    ran: bool
    consistency: float = 1.0  # 1 = perfectly consistent
    hallucination_score: float = 0.0  # max-aggregated, the paper's flagging metric
    avg_score: float = 0.0
    samples_used: int = 0
    sentences: List[SentenceScore] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    skip_reason: str = ""

    # Bands used to turn a continuous score into an operator-facing verdict.
    HIGH_RISK = 0.60
    MEDIUM_RISK = 0.35

    @property
    def risk_level(self) -> str:
        if not self.ran:
            return "not_checked"
        if self.hallucination_score >= self.HIGH_RISK:
            return "high"
        if self.hallucination_score >= self.MEDIUM_RISK:
            return "medium"
        return "low"

    def as_dict(self) -> dict:
        return {
            "ran": self.ran,
            "skip_reason": self.skip_reason or None,
            "samples_used": self.samples_used,
            "consistency": round(self.consistency, 3),
            "hallucination_score": round(self.hallucination_score, 3),
            "avg_sentence_score": round(self.avg_score, 3),
            "risk_level": self.risk_level,
            "flagged_sentences": [
                s.as_dict()
                for s in sorted(self.sentences, key=lambda x: -x.score)[:5]
                if s.score >= self.MEDIUM_RISK
            ],
            "warnings": self.warnings,
        }


def split_sentences(text: str) -> List[str]:
    """Split a markdown-ish review into scoreable units."""
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_RE.split(text) if p and p.strip()]
    # Ignore fragments too short to carry a factual claim.
    return [p for p in parts if len(_TOKEN_RE.findall(p)) >= 4]


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _is_dotted_symbol(token: str, sentence: str) -> bool:
    return bool(
        re.search(rf"\b{re.escape(token)}\s*[.(\[]", sentence)
        or re.search(rf"[.`]{re.escape(token)}\b", sentence)
    )


class SelfCheckGPT:
    """Consistency-based hallucination detection over stochastic samples."""

    @staticmethod
    def score_with_samples(
        primary_response: str,
        samples: Sequence[str],
    ) -> SelfCheckResult:
        """Score primary_response against pre-drawn samples."""
        result = SelfCheckResult(ran=False)

        if not primary_response or not primary_response.strip():
            result.skip_reason = "empty primary response"
            return result

        usable = [s for s in samples if s and s.strip()]
        if len(usable) < 2:
            # The method is meaningless with fewer than two comparison points.
            result.skip_reason = (
                f"insufficient samples ({len(usable)}; need at least 2)"
            )
            return result

        result.ran = True
        result.samples_used = len(usable)

        # Fit a unigram LM over the concatenated samples.
        sample_counts: Counter = Counter()
        for sample in usable:
            sample_counts.update(_tokenize(sample))
        total = sum(sample_counts.values())
        vocabulary = len(sample_counts) or 1

        def neg_log_prob(token: str) -> float:
            count = sample_counts.get(token, 0)
            probability = (count + _SMOOTHING) / (
                total + _SMOOTHING * vocabulary
            )
            return -math.log(probability)

        # Normalisation ceiling: the penalty a token absent from every sample receives.
        max_penalty = -math.log(_SMOOTHING / (total + _SMOOTHING * vocabulary))

        sentences: List[SentenceScore] = []
        for sentence in split_sentences(primary_response):
            raw_tokens = _TOKEN_RE.findall(sentence)
            tokens = [t.lower() for t in raw_tokens]
            if not tokens:
                continue

            # Split the sentence into two channels.
            identifiers, prose = [], []
            for raw, token in zip(raw_tokens, tokens):
                if token in _STOPWORDS:
                    continue
                if _IDENTIFIER_SHAPE.match(raw) or _is_dotted_symbol(raw, sentence):
                    identifiers.append(token)
                else:
                    prose.append(token)

            unsupported = [
                token
                for token in identifiers + prose
                if sample_counts.get(token, 0) == 0
            ]

            identifier_score = (
                sum(1 for t in identifiers if sample_counts.get(t, 0) == 0)
                / len(identifiers)
                if identifiers
                else None
            )

            if prose:
                penalties = [neg_log_prob(token) for token in prose]
                worst_two = sorted(penalties, reverse=True)[:2]
                prose_score = (
                    min(1.0, (sum(worst_two) / len(worst_two)) / max_penalty)
                    if max_penalty
                    else 0.0
                )
            else:
                prose_score = None

            if identifier_score is None and prose_score is None:
                continue
            if identifier_score is None:
                normalized = prose_score
            elif prose_score is None:
                normalized = identifier_score
            else:
                normalized = (
                    _IDENTIFIER_WEIGHT * identifier_score
                    + _PROSE_WEIGHT * prose_score
                )

            sentences.append(
                SentenceScore(
                    text=sentence,
                    score=round(float(normalized), 4),
                    unsupported_tokens=list(dict.fromkeys(unsupported)),
                )
            )

        if not sentences:
            result.ran = False
            result.skip_reason = "no scoreable sentences in primary response"
            return result

        result.sentences = sentences
        scores = [s.score for s in sentences]
        result.hallucination_score = round(max(scores), 4)
        result.avg_score = round(sum(scores) / len(scores), 4)
        result.consistency = round(1.0 - result.avg_score, 4)

        if result.risk_level == "high":
            worst = max(sentences, key=lambda s: s.score)
            result.warnings.append(
                f"Hallucination risk: HIGH ({result.hallucination_score:.2f}). "
                f"A claim is not corroborated by any of the "
                f"{result.samples_used} resamples: "
                f"\"{worst.text[:110]}…\" - verify before applying."
            )
        elif result.risk_level == "medium":
            result.warnings.append(
                f"Hallucination risk: MEDIUM "
                f"({result.hallucination_score:.2f}). Some claims vary across "
                f"{result.samples_used} resamples."
            )

        return result

    @staticmethod
    def check(
        prompt: str,
        primary_response: str,
        num_samples: Optional[int] = None,
        sampler: Optional[Callable[[str], str]] = None,
        system_prompt: str = "",
    ) -> SelfCheckResult:
        """Draw samples for prompt and score primary_response."""
        if num_samples is None:
            num_samples = int(
                getattr(settings, "SELFCHECK_SAMPLES", 0) or 0
            ) or 3

        if sampler is None:
            from app.tools.llm_tool import LLMTool

            if not LLMTool.is_available():
                return SelfCheckResult(
                    ran=False, skip_reason="LLM not configured"
                )

            def sampler(text: str) -> str:  # type: ignore[misc]
                return LLMTool.generate(text, system_prompt=system_prompt)

        samples: List[str] = []
        for index in range(num_samples):
            try:
                samples.append(sampler(prompt))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SelfCheck sample %d/%d failed: %s", index + 1, num_samples, exc
                )

        result = SelfCheckGPT.score_with_samples(primary_response, samples)
        if result.ran:
            logger.info(
                "SelfCheckGPT: %d samples, hallucination=%.2f (%s)",
                result.samples_used,
                result.hallucination_score,
                result.risk_level,
            )
        return result

    @staticmethod
    def enabled() -> bool:
        return bool(getattr(settings, "ENABLE_SELFCHECK", False))
