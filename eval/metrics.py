"""
eval/metrics.py — Honest metrics for the Chargeback Evidence Responder (Phase 1 + 4).

Scores any pipeline output against the frozen, hand-labeled test set. The pipeline
NEVER sees ground-truth labels; this script joins them back in by dispute_id, so
there is no leakage path (rules.md R4).

Reported (rules.md R9-R12):
  * Precision / recall / F1 on the "fight this dispute" decision
      positive prediction := recommendation in {submit, submit_with_caveats}
      positive truth      := ground_truth == should_win
    (borderline and punted cases are excluded from the binary P/R and reported
     separately — penalizing an ambiguous case either way would be dishonest.)
  * Full recommendation x ground-truth confusion matrix (nothing hidden).
  * False-positive cost in INR (concrete unit, from thresholds.yaml cost model).
  * False-negative cost in INR (forgone recoverable revenue = dispute amount).
  * Punt rate (% of cases the classifier could not map to a family).
  * Coverage and per-family breakdown.

Usage:
  python3 eval/metrics.py                      # scores data/pipeline_output.json
  python3 eval/metrics.py path/to/output.json  # scores a specific output file
  python3 eval/metrics.py --dummy              # sanity-check the harness itself
                                               # with a random dummy pipeline
"""
from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.common import (  # noqa: E402
    TEST_SET_PATH, PIPELINE_OUTPUT_PATH, load_thresholds, reason_code_to_family_map,
)

POSITIVE_RECS = {"submit", "submit_with_caveats"}
ALL_RECS = ["submit", "submit_with_caveats", "do_not_submit", "punt"]


def load_test_set():
    with open(TEST_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _fp_unit_cost(costs):
    return (costs["ops_hours_per_submission"] * costs["ops_hourly_rate_inr"]
            + costs["representment_fee_inr"] + costs["lost_dispute_penalty_inr"])


def compute_metrics(test_set, output_list):
    costs = load_thresholds()["costs"]
    by_id = {c["dispute_id"]: c for c in test_set["cases"]}
    amount = {c["dispute_id"]: c["dispute"]["amount_inr"] for c in test_set["cases"]}

    total = len(output_list)
    punts = 0
    tp = fp = fn = tn = 0
    submit_only_tp = submit_only_fp = 0
    fp_cases, fn_cases = [], []
    # confusion[recommendation][ground_truth]
    confusion = {r: {"should_win": 0, "should_lose": 0, "borderline": 0, "n/a": 0} for r in ALL_RECS}
    borderline_handling = {r: 0 for r in ALL_RECS}
    per_family = {}  # family -> counts

    for res in output_list:
        did = res["dispute_id"]
        gt = by_id[did]["ground_truth"]
        rec = res["recommendation"]
        fam = res.get("family") or "unknown"
        confusion.setdefault(rec, {"should_win": 0, "should_lose": 0, "borderline": 0, "n/a": 0})
        confusion[rec][gt] += 1

        pf = per_family.setdefault(fam, {"n": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0, "punt": 0, "borderline": 0})
        pf["n"] += 1

        if rec == "punt" or res.get("is_punt"):
            punts += 1
            pf["punt"] += 1
            continue

        if gt == "borderline":
            borderline_handling[rec] += 1
            pf["borderline"] += 1
            continue
        if gt == "n/a":
            # a non-punt on an unsupported code would be a classifier bug; count it
            continue

        pred_pos = rec in POSITIVE_RECS
        if pred_pos and gt == "should_win":
            tp += 1; pf["tp"] += 1
        elif pred_pos and gt == "should_lose":
            fp += 1; pf["fp"] += 1
            fp_cases.append(did)
        elif not pred_pos and gt == "should_win":
            fn += 1; pf["fn"] += 1
            fn_cases.append(did)
        elif not pred_pos and gt == "should_lose":
            tn += 1; pf["tn"] += 1

        # strict variant: only a full "submit" counts as fighting
        if rec == "submit" and gt == "should_win":
            submit_only_tp += 1
        elif rec == "submit" and gt == "should_lose":
            submit_only_fp += 1

    def safe_div(a, b):
        return (a / b) if b else 0.0

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    binary_total = tp + fp + fn + tn
    accuracy = safe_div(tp + tn, binary_total)

    fp_unit = _fp_unit_cost(costs)
    fp_cost = fp * fp_unit
    fn_cost = sum(amount[d] for d in fn_cases)

    # R12-adjacent honesty check: is every error a pre-labeled adversarial "hard
    # case" (data/test_set.json's gt_rationale is written independently of the
    # scorer), or is some error unexplained by the test set's own design? This
    # distinguishes "the evidence-only architecture has a known, named blind spot"
    # from "the scorer got something it shouldn't have wrong" — the two look
    # identical in a bare confusion matrix but mean very different things.
    def _is_hard_case(did):
        rationale = by_id.get(did, {}).get("gt_rationale", "") or ""
        return rationale.strip().upper().startswith("HARD CASE")

    error_cases = fp_cases + fn_cases
    hard_case_errors = [d for d in error_cases if _is_hard_case(d)]
    unexplained_errors = [d for d in error_cases if not _is_hard_case(d)]

    return {
        "total_cases": total,
        "punts": punts,
        "punt_rate": safe_div(punts, total),
        "coverage": safe_div(total - punts, total),
        "binary_evaluable": binary_total,
        "borderline_excluded": sum(borderline_handling.values()),
        "confusion": confusion,
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "submit_only": {
            "precision": safe_div(submit_only_tp, submit_only_tp + submit_only_fp),
            "tp": submit_only_tp, "fp": submit_only_fp,
        },
        "false_positive_cost_inr": fp_cost,
        "false_positive_unit_cost_inr": fp_unit,
        "false_negative_cost_inr": fn_cost,
        "fp_cases": fp_cases,
        "fn_cases": fn_cases,
        "hard_case_errors": hard_case_errors,
        "unexplained_errors": unexplained_errors,
        "borderline_handling": borderline_handling,
        "per_family": per_family,
        "currency": costs.get("currency", "INR"),
    }


def format_report(m):
    L = []
    a = L.append
    a("=" * 66)
    a("  CHARGEBACK EVIDENCE RESPONDER — EVALUATION REPORT")
    a("=" * 66)
    a(f"  Total cases evaluated : {m['total_cases']}")
    a(f"  Coverage (processed)  : {m['coverage']*100:5.1f}%   "
      f"(punts: {m['punts']}, punt rate {m['punt_rate']*100:.1f}%)")
    a(f"  Binary-evaluable      : {m['binary_evaluable']} "
      f"(win/lose; {m['borderline_excluded']} borderline excluded)")
    a("")
    a("  DECISION QUALITY  (positive = recommend fighting: submit or caveats)")
    a(f"    Precision : {m['precision']*100:5.1f}%")
    a(f"    Recall    : {m['recall']*100:5.1f}%")
    a(f"    F1        : {m['f1']*100:5.1f}%")
    a(f"    Accuracy  : {m['accuracy']*100:5.1f}%")
    c = m["counts"]
    a(f"    TP={c['tp']}  FP={c['fp']}  FN={c['fn']}  TN={c['tn']}")
    a(f"    (strict, submit-only precision: {m['submit_only']['precision']*100:.1f}%"
      f"  [TP={m['submit_only']['tp']}, FP={m['submit_only']['fp']}])")
    a("")
    a(f"  FALSE-POSITIVE COST : {m['currency']} {m['false_positive_cost_inr']:,.0f}"
      f"   ({m['counts']['fp']} FP x {m['currency']} {m['false_positive_unit_cost_inr']:,.0f})")
    a(f"    -> wrongly recommending a fight on a should-lose dispute")
    a(f"    -> FP cases: {', '.join(m['fp_cases']) if m['fp_cases'] else 'none'}")
    a(f"  FALSE-NEGATIVE COST : {m['currency']} {m['false_negative_cost_inr']:,.0f}"
      f"   (forgone recoverable revenue)")
    a(f"    -> FN cases: {', '.join(m['fn_cases']) if m['fn_cases'] else 'none'}")
    a("")
    n_err = len(m["fp_cases"]) + len(m["fn_cases"])
    n_hard = len(m["hard_case_errors"])
    n_unexplained = len(m["unexplained_errors"])
    if n_err:
        if n_unexplained == 0:
            a(f"  ERROR-CASE AUDIT : {n_err}/{n_err} errors are pre-labeled adversarial hard")
            a(f"                     cases (test_set.json gt_rationale, written independently")
            a(f"                     of the scorer) — 0 unexplained errors.")
        else:
            a(f"  ERROR-CASE AUDIT : {n_hard}/{n_err} errors are pre-labeled adversarial hard")
            a(f"                     cases; {n_unexplained} UNEXPLAINED — investigate:")
            a(f"                     {', '.join(m['unexplained_errors'])}")
        a("")
    a("  CONFUSION MATRIX  (rows = recommendation, cols = ground truth)")
    a(f"    {'':22}{'win':>7}{'lose':>7}{'border':>8}{'n/a':>6}")
    for r in ALL_RECS:
        row = m["confusion"].get(r, {})
        a(f"    {r:22}{row.get('should_win',0):>7}{row.get('should_lose',0):>7}"
          f"{row.get('borderline',0):>8}{row.get('n/a',0):>6}")
    a("")
    a("  BORDERLINE HANDLING (ideal: caveats / human review)")
    bh = m["borderline_handling"]
    a(f"    submit={bh.get('submit',0)}  caveats={bh.get('submit_with_caveats',0)}  "
      f"do_not_submit={bh.get('do_not_submit',0)}  punt={bh.get('punt',0)}")
    a("")
    a("  PER-FAMILY")
    for fam, pf in sorted(m["per_family"].items()):
        a(f"    {fam:14} n={pf['n']:2}  TP={pf['tp']} FP={pf['fp']} FN={pf['fn']} "
          f"TN={pf['tn']}  border={pf['borderline']} punt={pf['punt']}")
    a("")
    # R12 honesty guard
    if m["precision"] > 0.95 and m["counts"]["tp"] + m["counts"]["fp"] > 5:
        a("  [R12 WARNING] Precision > 95% — check for data leakage or an")
        a("               unrealistically easy test set before trusting this.")
        a("")
    a("=" * 66)
    return "\n".join(L)


def make_dummy_output(test_set):
    """Random pipeline output for validating the harness itself (Phase 1 check).
    Respects the punt path on unsupported reason codes so the join logic is
    exercised realistically."""
    random.seed(7)
    fam_map = reason_code_to_family_map()
    out = []
    for c in test_set["cases"]:
        code = c["dispute"]["reason_code"]
        fam = fam_map.get(str(code))
        if fam is None:
            out.append({"dispute_id": c["dispute_id"], "family": None,
                        "is_punt": True, "confidence": None, "recommendation": "punt"})
        else:
            rec = random.choice(["submit", "submit_with_caveats", "do_not_submit"])
            out.append({"dispute_id": c["dispute_id"], "family": fam, "is_punt": False,
                        "confidence": round(random.uniform(0, 100), 1), "recommendation": rec})
    return out


def main(argv):
    test_set = load_test_set()
    if "--dummy" in argv:
        print(">>> DUMMY MODE: scoring a random pipeline output to validate the harness.\n")
        output = make_dummy_output(test_set)
    else:
        path = next((a for a in argv[1:] if not a.startswith("--")), str(PIPELINE_OUTPUT_PATH))
        with open(path, "r", encoding="utf-8") as f:
            output = json.load(f)
        if isinstance(output, dict) and "results" in output:
            output = output["results"]
    m = compute_metrics(test_set, output)
    print(format_report(m))
    return m


if __name__ == "__main__":
    main(sys.argv)
