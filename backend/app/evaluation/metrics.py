"""Evaluation metric calculations."""

from dataclasses import dataclass
from typing import List


@dataclass
class ClassificationMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    def as_dict(self) -> dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "f1": round(self.f1, 3),
        }


def classification_metrics(
    expected: set,
    predicted: set,
) -> ClassificationMetrics:
    """Compare a set of expected labels against predicted labels."""
    tp = len(expected & predicted)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    return ClassificationMetrics(tp, fp, fn)


def hallucination_rate(
    flagged_samples: int,
    total_samples: int,
) -> float:
    """Share of samples whose generated output was flagged as hallucinated."""
    return round(flagged_samples / total_samples, 3) if total_samples else 0.0


def guardrail_recall(
    caught_unsafe: int,
    total_unsafe: int,
) -> float:
    """Share of known-unsafe suggestions caught by the output guardrails."""
    return round(caught_unsafe / total_unsafe, 3) if total_unsafe else 1.0


def latency_stats(latencies_ms: List[float]) -> dict:
    """Summarise a list of latency samples (milliseconds)."""
    if not latencies_ms:
        return {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}

    ordered = sorted(latencies_ms)
    n = len(ordered)

    def percentile(p: float) -> float:
        idx = min(n - 1, int(round((p / 100.0) * (n - 1))))
        return round(ordered[idx], 2)

    return {
        "count": n,
        "mean_ms": round(sum(ordered) / n, 2),
        "p50_ms": percentile(50),
        "p95_ms": percentile(95),
        "max_ms": round(ordered[-1], 2),
    }
