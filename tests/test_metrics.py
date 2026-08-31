"""Unit tests for eval/metrics.py — the honest-scoring harness itself.

These don't touch the pipeline; they build tiny synthetic test sets + outputs
in memory so the precision/recall/cost math and the error-case audit (are FP/FN
cases pre-labeled adversarial hard cases, or unexplained?) are checked directly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval.metrics import compute_metrics  # noqa: E402


def _case(did, ground_truth, amount_inr=1000, gt_rationale=""):
    return {
        "dispute_id": did,
        "ground_truth": ground_truth,
        "gt_rationale": gt_rationale,
        "dispute": {"dispute_id": did, "amount_inr": amount_inr},
    }


def _result(did, family, recommendation):
    return {"dispute_id": did, "family": family, "is_punt": recommendation == "punt",
            "recommendation": recommendation}


def test_basic_precision_recall_and_costs():
    test_set = {"cases": [
        _case("A", "should_win"), _case("B", "should_win"),
        _case("C", "should_lose"), _case("D", "should_lose"),
    ]}
    output = [
        _result("A", "not_received", "submit"),          # TP
        _result("B", "not_received", "do_not_submit"),   # FN
        _result("C", "not_received", "submit"),          # FP
        _result("D", "not_received", "do_not_submit"),   # TN
    ]
    m = compute_metrics(test_set, output)
    assert m["counts"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5
    assert m["false_negative_cost_inr"] == 1000  # B's amount
    assert m["false_positive_cost_inr"] == m["false_positive_unit_cost_inr"]


def test_borderline_and_punt_excluded_from_binary_metrics():
    test_set = {"cases": [
        _case("A", "should_win"),
        _case("B", "borderline"),
        _case("C", "n/a"),
    ]}
    output = [
        _result("A", "not_received", "submit"),
        _result("B", "not_received", "submit_with_caveats"),
        _result("C", None, "punt"),
    ]
    m = compute_metrics(test_set, output)
    assert m["binary_evaluable"] == 1          # only A
    assert m["punts"] == 1                     # only C
    assert m["borderline_handling"]["submit_with_caveats"] == 1


def test_error_case_audit_flags_pre_labeled_hard_cases_as_explained():
    test_set = {"cases": [
        _case("A", "should_lose", gt_rationale="HARD CASE (expected false positive): ..."),
        _case("B", "should_win"),
    ]}
    output = [
        _result("A", "not_received", "submit"),        # FP, pre-labeled hard case
        _result("B", "not_received", "do_not_submit"), # FN, NOT pre-labeled -> unexplained
    ]
    m = compute_metrics(test_set, output)
    assert m["hard_case_errors"] == ["A"]
    assert m["unexplained_errors"] == ["B"]


def test_error_case_audit_empty_when_no_errors():
    test_set = {"cases": [_case("A", "should_win")]}
    output = [_result("A", "not_received", "submit")]
    m = compute_metrics(test_set, output)
    assert m["hard_case_errors"] == []
    assert m["unexplained_errors"] == []


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1; print(f"FAIL {fn.__name__}: {e}"); traceback.print_exc()
    raise SystemExit(1 if failed else 0)
