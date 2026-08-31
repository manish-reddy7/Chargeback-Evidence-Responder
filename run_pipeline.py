"""
run_pipeline.py — orchestrate the full pipeline over the frozen test set (Phase 4).

For every case:  classify -> retrieve -> score -> recommend -> (packet) -> audit log.

Two outputs:
  * data/pipeline_output.json  — exactly what the pipeline decided, per case. Contains
      NO ground-truth labels (the pipeline never sees them). eval/metrics.py re-joins
      the labels from the frozen test set by dispute_id, so there is no leakage path
      (rules.md R4). This file also feeds the dashboard.
  * audit/trail.jsonl          — one immutable decision entry per case (rules.md R16).

The system stops at "packet ready for human sign-off." It NEVER files a dispute
(rules.md R5) — there is no network call anywhere in this run.

Usage:
  python3 run_pipeline.py                 # run over data/test_set.json
  python3 run_pipeline.py --backend deterministic
  python3 run_pipeline.py --demo-override # also append one sample human override (R17)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from audit.logger import log_decision, record_override, reset_trail
from pipeline.classifier import classify_case
from pipeline.common import PIPELINE_OUTPUT_PATH, TEST_SET_PATH
from pipeline.packet_generator import default_backend, generate_packet
from pipeline.retriever import retrieve
from pipeline.scorer import recommend, score


def _punt_records(case):
    """Stand-in score/packet results for an unmapped reason code (a punt)."""
    dispute = case.get("dispute", {})
    score_result = {
        "confidence": None, "raw_confidence": None, "per_field": {},
        "critical_gaps": [], "gate_reasons": [
            f"Reason code '{dispute.get('reason_code')}' is not mapped to a known "
            f"dispute family — routed to a human for manual triage."
        ],
        "present_fields": [], "weak_fields": [], "missing_fields": [],
    }
    packet_result = {
        "recommendation": "punt", "packet_text": None, "backend": None,
        "evidence_used": [], "validation_warnings": [], "flagged_for_review": True,
        "explanation": score_result["gate_reasons"][0],
    }
    return score_result, packet_result


def process_case(case, backend):
    """Run one case end to end. Returns (result_record, score_result, packet_result)."""
    dispute = case.get("dispute", {})
    family = classify_case(case)

    if family is None:
        score_result, packet_result = _punt_records(case)
        what_would_help = []
    else:
        evidence = retrieve(case, family)
        score_result = score(evidence, family)
        packet_result = generate_packet(case, family, score_result, backend=backend)
        what_would_help = recommend(score_result)["what_would_help"]

    record = {
        "dispute_id": dispute.get("dispute_id"),
        "family": family,
        "reason_code": dispute.get("reason_code"),
        "is_punt": family is None,
        "amount_inr": dispute.get("amount_inr"),
        "deadline": dispute.get("deadline"),
        "confidence": score_result.get("confidence"),
        "recommendation": packet_result["recommendation"],
        "explanation": packet_result.get("explanation", ""),
        "flagged_for_review": packet_result.get("flagged_for_review", False),
        "backend": packet_result.get("backend"),
        "packet_text": packet_result.get("packet_text"),
        "evidence_used": packet_result.get("evidence_used", []),
        "validation_warnings": packet_result.get("validation_warnings", []),
        "what_would_help": what_would_help,
        # scorer detail for the dashboard's evidence checklist + confidence bar
        # (pipeline output only — contains no ground-truth labels)
        "score": {
            "raw_confidence": score_result.get("raw_confidence"),
            "per_field": score_result.get("per_field", {}),
            "present_fields": score_result.get("present_fields", []),
            "weak_fields": score_result.get("weak_fields", []),
            "missing_fields": score_result.get("missing_fields", []),
            "critical_gaps": score_result.get("critical_gaps", []),
            "gate_reasons": score_result.get("gate_reasons", []),
        },
    }
    return record, score_result, packet_result


def run(backend=None, demo_override=False):
    backend = backend or default_backend()
    with open(TEST_SET_PATH, "r", encoding="utf-8") as f:
        test_set = json.load(f)

    reset_trail()  # fresh trail for this reproducible batch run
    results = []
    for case in test_set["cases"]:
        record, score_result, packet_result = process_case(case, backend)
        log_decision(case, record["family"], score_result, packet_result)
        results.append(record)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": backend,
        "n_cases": len(results),
        "results": results,
    }
    with open(PIPELINE_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Demonstrate a human override being captured (rules.md R17). We pick the first
    # 'submit_with_caveats' case and record a reviewer downgrading it pending more
    # evidence. This appends a NEW trail entry; it never edits the machine decision.
    if demo_override:
        caveat = next((r for r in results if r["recommendation"] == "submit_with_caveats"), None)
        if caveat:
            record_override(
                dispute_id=caveat["dispute_id"],
                original_recommendation="submit_with_caveats",
                override_recommendation="do_not_submit",
                actor="risk_reviewer:demo",
                note="Reviewer withheld filing pending stronger delivery confirmation.",
            )

    # console summary
    from collections import Counter
    recs = Counter(r["recommendation"] for r in results)
    flagged = sum(1 for r in results if r["flagged_for_review"])
    print(f"Processed {len(results)} cases with backend='{backend}'.")
    print("  recommendations:", dict(recs))
    print(f"  flagged for human review: {flagged}")
    print(f"  wrote {PIPELINE_OUTPUT_PATH}")
    return payload


def main():
    ap = argparse.ArgumentParser(description="Run the chargeback evidence pipeline over the test set.")
    ap.add_argument("--backend", default=None, choices=["deterministic", "anthropic", "ollama"],
                    help="LLM backend for packet drafting (default: auto-detect).")
    ap.add_argument("--demo-override", action="store_true",
                    help="Append one sample human override to the audit trail (rules.md R17).")
    args = ap.parse_args()
    run(backend=args.backend, demo_override=args.demo_override)


if __name__ == "__main__":
    main()
