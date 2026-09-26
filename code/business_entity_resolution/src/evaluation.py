"""Exact macro F0.5 evaluation for complete per-S1 entity-ID sets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationResult:
    macro_precision: float
    macro_recall: float
    macro_f05: float
    singleton_accuracy: float
    singleton_false_positive_rate: float
    average_predicted_matches_per_s1: float
    evaluated_source1_count: int
    singleton_count: int


def score_entity(true_ids: set[str] | frozenset[str], predicted_ids: set[str] | frozenset[str]) -> tuple[float, float, float]:
    """Return exact precision, recall, F0.5 for one Source-1 entity."""
    true_set, predicted_set = set(true_ids), set(predicted_ids)
    if not true_set:
        return (1.0, 1.0, 1.0) if not predicted_set else (0.0, 0.0, 0.0)
    intersection = len(true_set & predicted_set)
    precision = intersection / len(predicted_set) if predicted_set else 0.0
    recall = intersection / len(true_set)
    f05 = (1.25 * precision * recall / (0.25 * precision + recall)) if precision and recall else 0.0
    return precision, recall, f05


def evaluate_predictions(
    truth: Mapping[str, set[str] | frozenset[str]], predictions: Mapping[str, set[str] | frozenset[str]]
) -> EvaluationResult:
    """Macro-average per-S1 exact set scores; missing predictions are empty sets."""
    if not truth:
        raise ValueError("Truth mapping is empty")
    total_precision = total_recall = total_f05 = total_predictions = 0.0
    singleton_count = singleton_correct = singleton_false_positive = 0
    for s1_id, true_ids in truth.items():
        predicted_ids = predictions.get(s1_id, frozenset())
        precision, recall, f05 = score_entity(true_ids, predicted_ids)
        total_precision += precision
        total_recall += recall
        total_f05 += f05
        total_predictions += len(predicted_ids)
        if not true_ids:
            singleton_count += 1
            if predicted_ids:
                singleton_false_positive += 1
            else:
                singleton_correct += 1
    count = len(truth)
    return EvaluationResult(
        macro_precision=total_precision / count,
        macro_recall=total_recall / count,
        macro_f05=total_f05 / count,
        singleton_accuracy=singleton_correct / singleton_count if singleton_count else 0.0,
        singleton_false_positive_rate=singleton_false_positive / singleton_count if singleton_count else 0.0,
        average_predicted_matches_per_s1=total_predictions / count,
        evaluated_source1_count=count,
        singleton_count=singleton_count,
    )
