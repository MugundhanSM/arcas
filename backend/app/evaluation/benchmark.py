"""Benchmark runner - all six metrics."""

import json
import re
import time
from typing import Set

from app.agents.metrics_agent import MetricsAgent
from app.agents.refactor_agent import RefactorAgent
from app.agents.review_agent import ReviewAgent
from app.agents.risk_agent import RiskAgent
from app.agents.security_agent import SecurityAgent
from app.core.output_guardrails import OutputGuardrails
from app.evaluation.datasets import BENCHMARK, CATEGORY_KEYWORDS, Sample
from app.evaluation.metrics import (
    classification_metrics,
    hallucination_rate,
    latency_stats,
)


def _categories_from_findings(findings) -> Set[str]:
    from app.evaluation.benchmark_datasets import CWE_TO_CATEGORY

    detected: Set[str] = set()
    for finding in findings or []:
        cwe = finding.get("cwe")
        if cwe and cwe in CWE_TO_CATEGORY:
            detected.add(CWE_TO_CATEGORY[cwe])
            continue

        # Fallback: match the rule id only, on word boundaries.
        rule_id = str(finding.get("check_id", "")).lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(
                re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", rule_id)
                for kw in keywords
            ):
                detected.add(category)
    return detected


def _evaluate_sample(sample: Sample) -> dict:
    start = time.perf_counter()

    review_findings = ReviewAgent.analyze(sample.code, sample.language)
    security_findings = SecurityAgent.analyze(sample.code, sample.language)
    metrics = MetricsAgent.analyze(
        sample.code, review_findings, sample.language
    )
    risk = RiskAgent.analyze(security_findings, metrics)

    refactor = RefactorAgent.analyze(
        source_code=sample.code,
        language=sample.language,
        review_findings=review_findings,
        security_findings=security_findings,
        risk_analysis=risk,
        metrics=metrics,
    )
    output_guard = OutputGuardrails.check(
        generated_text=refactor,
        source_code=sample.code,
        review_findings=review_findings,
    )

    latency_ms = (time.perf_counter() - start) * 1000.0
    detected = _categories_from_findings(security_findings)

    return {
        "name": sample.name,
        "expected": sample.expected_categories,
        "detected": detected,
        "hallucinated": bool(output_guard.hallucination_warnings),
        "security_regression": not output_guard.passed,
        "latency_ms": latency_ms,
    }


def run_benchmark() -> dict:
    expected_all: Set[str] = set()
    predicted_all: Set[str] = set()

    latencies = []
    hallucinated = 0
    false_positives_safe = 0
    total_samples = len(BENCHMARK)

    per_sample = []
    for sample in BENCHMARK:
        result = _evaluate_sample(sample)
        per_sample.append(
            {
                "name": result["name"],
                "expected": sorted(result["expected"]),
                "detected": sorted(result["detected"]),
                "hallucinated": result["hallucinated"],
                "latency_ms": round(result["latency_ms"], 1),
            }
        )

        # Aggregate detection labels (namespaced per sample to avoid cross-sample category collisions).
        for cat in result["expected"]:
            expected_all.add(f"{result['name']}:{cat}")
        for cat in result["detected"]:
            predicted_all.add(f"{result['name']}:{cat}")

        if sample.is_safe and result["detected"]:
            false_positives_safe += 1
        if result["hallucinated"]:
            hallucinated += 1
        latencies.append(result["latency_ms"])

    detection = classification_metrics(expected_all, predicted_all)

    from app.evaluation.guardrail_eval import run_guardrail_evaluation

    semgrep_available = _semgrep_available()

    guardrails = run_guardrail_evaluation()

    report = {
        "environment": {
            "semgrep_available": semgrep_available,
            "note": (
                None
                if semgrep_available
                else "Semgrep is not installed: detection metrics reflect the "
                "heuristic fallback only and understate real performance."
            ),
        },
        "metric_1_bug_detection": {
            "dataset": "built-in labelled set",
            "samples": total_samples,
            **detection.as_dict(),
            "target_f1": 0.80,
            "meets_target": detection.f1 >= 0.80,
            "false_positive_safe_samples": false_positives_safe,
            "caveat": (
                "This set has only "
                f"{total_samples} samples and the bundled offline Semgrep "
                "ruleset was authored to cover exactly its categories, so this "
                "score is an upper bound and is NOT evidence of "
                "generalisation. Run --dataset sate_iv for a held-out "
                "measurement, and set ARCAS_SATE_PATH / "
                "ARCAS_CODEREVIEWER_PATH to evaluate on the real benchmarks."
            ),
        },
        "metric_2_hallucination": {
            "rate": hallucination_rate(hallucinated, total_samples),
            "target": 0.05,
            "method": (
                "output-guardrail heuristics; enable ENABLE_SELFCHECK for "
                "SelfCheckGPT consistency sampling (requires a configured LLM)"
            ),
        },
        "metric_3_guardrail_recall": {
            "injection": guardrails["injection_guardrail"],
            "pii": guardrails["pii_guardrail"],
            "corpus": guardrails["corpus"],
            "per_technique": guardrails["per_technique"],
        },
        "metric_4_latency": latency_stats(latencies),
        "per_sample": per_sample,
    }
    return report


def _semgrep_available() -> bool:
    import shutil

    return shutil.which("semgrep") is not None


def run_dataset_benchmark(dataset_name: str, limit: int = 200) -> dict:
    """Evaluate detection against an external benchmark (or its local subset)."""
    from app.evaluation.benchmark_datasets import load_dataset

    loaded = load_dataset(dataset_name, limit=limit)

    expected_all: Set[str] = set()
    predicted_all: Set[str] = set()
    per_sample = []
    latencies = []
    safe_false_positives = 0

    for sample in loaded.samples:
        start = time.perf_counter()
        findings = SecurityAgent.analyze(sample.code, sample.language)
        latencies.append((time.perf_counter() - start) * 1000.0)

        detected = _categories_from_findings(findings)
        for category in sample.expected_categories:
            expected_all.add(f"{sample.sample_id}:{category}")
        for category in detected:
            predicted_all.add(f"{sample.sample_id}:{category}")

        if sample.is_safe and detected:
            safe_false_positives += 1

        per_sample.append(
            {
                "id": sample.sample_id,
                "language": sample.language,
                "expected": sorted(sample.expected_categories),
                "detected": sorted(detected),
                "is_safe": sample.is_safe,
            }
        )

    detection = classification_metrics(expected_all, predicted_all)
    return {
        **loaded.as_dict(),
        "detection": detection.as_dict(),
        "target_f1": 0.80,
        "meets_target": detection.f1 >= 0.80,
        "safe_samples_with_findings": safe_false_positives,
        "latency": latency_stats(latencies),
        "per_sample": per_sample,
    }


def run_full_evaluation() -> dict:
    """Every metric, including the two that need external state."""
    from app.evaluation.satisfaction import aggregate_feedback

    report = run_benchmark()
    report["metric_1b_external_datasets"] = {
        name: run_dataset_benchmark(name)
        for name in ("sate_iv", "codereviewer")
    }
    report["metric_6_user_satisfaction"] = aggregate_feedback().as_dict()
    report["metric_5_refactoring_correctness"] = {
        "note": (
            "Measured per-review by app.evaluation.refactor_correctness, which "
            "runs the generated tests against the original and refactored code "
            "and reports preserved / regression / repaired counts. It requires "
            "a configured LLM to produce a refactoring, so it is not part of "
            "the offline benchmark run."
        ),
    }
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="ARCAS evaluation harness")
    parser.add_argument(
        "--dataset",
        help="Evaluate one benchmark only (sate_iv | codereviewer).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run every metric, including external datasets and satisfaction.",
    )
    args = parser.parse_args()

    if args.dataset:
        report = run_dataset_benchmark(args.dataset)
    elif args.full:
        report = run_full_evaluation()
    else:
        report = run_benchmark()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
