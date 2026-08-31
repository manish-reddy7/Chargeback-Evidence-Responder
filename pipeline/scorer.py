"""
pipeline/scorer.py — Stage 3: sufficiency scoring + three-way recommendation (Phase 2/3).

Deterministic ONLY (rules.md R20). Grades each evidence field present/weak/missing,
computes a 0-100 confidence from the config-driven weights (families.yaml), applies
the gating rules, then maps confidence -> Submit / Submit-with-caveats / Do-not-submit
using the thresholds in thresholds.yaml (rules.md R3, R8).

Grading convention (set by the retriever / data):
    value is None        -> missing (earns 0; if the field is `required`, records a critical gap)
    value present & weak  -> weak    (earns weak_multiplier * weight)
    value present & strong-> present (earns full weight)

Gating:
    * any required field missing         -> confidence capped at required_missing_ceiling
    * gate.require_any present but none of
      those fields present/weak          -> confidence capped at require_any_ceiling
"""
from __future__ import annotations

from pipeline.common import load_families, load_thresholds


def score(evidence_map, family) -> dict:
    fam_cfg = load_families()[family]
    th = load_thresholds()["scoring"]
    weak_mult = th["weak_multiplier"]
    req_ceiling = th["required_missing_ceiling"]
    any_ceiling = th["require_any_ceiling"]

    fields_cfg = fam_cfg["evidence"]
    require_any = fam_cfg.get("gate", {}).get("require_any", []) or []
    total_weight = sum(f["weight"] for f in fields_cfg.values())

    per_field = {}
    earned = 0.0
    critical_gaps = []

    for field, fcfg in fields_cfg.items():
        weight = fcfg["weight"]
        required = bool(fcfg.get("required", False))
        ev = evidence_map.get(field, {"value": None, "weak": None, "source": None})

        if ev.get("value") is None:
            status, pts = "missing", 0.0
            if required:
                critical_gaps.append(field)
        elif ev.get("weak"):
            status, pts = "weak", weight * weak_mult
        else:
            status, pts = "present", float(weight)

        earned += pts
        per_field[field] = {
            "status": status,
            "weight": weight,
            "earned": round(pts, 1),
            "required": required,
            "why": fcfg["why"],
            "value": ev.get("value"),
            "source": ev.get("source"),
        }

    raw_conf = 100.0 * earned / total_weight if total_weight else 0.0
    conf = raw_conf
    gate_reasons = []

    if critical_gaps:
        if conf > req_ceiling:
            conf = req_ceiling
        gate_reasons.append(
            f"Required evidence missing ({', '.join(critical_gaps)}); confidence capped at {req_ceiling}."
        )

    if require_any:
        satisfied = any(
            evidence_map.get(f, {}).get("value") is not None for f in require_any
        )
        if not satisfied:
            if conf > any_ceiling:
                conf = any_ceiling
            gate_reasons.append(
                f"No authentication signal present (need one of: {', '.join(require_any)}); "
                f"confidence capped at {any_ceiling}."
            )

    return {
        "family": family,
        "confidence": round(conf, 1),
        "raw_confidence": round(raw_conf, 1),
        "per_field": per_field,
        "critical_gaps": critical_gaps,
        "gate_reasons": gate_reasons,
        "present_fields": [f for f, d in per_field.items() if d["status"] == "present"],
        "weak_fields": [f for f, d in per_field.items() if d["status"] == "weak"],
        "missing_fields": [f for f, d in per_field.items() if d["status"] == "missing"],
    }


def recommend(score_result) -> dict:
    """Map a score result to Submit / Submit-with-caveats / Do-not-submit.

    Thresholds come from thresholds.yaml (rules.md R8: explicit + tunable). A
    missing required field caps confidence below submit_min, so a critical gap
    can never reach 'submit' — the `not critical_gaps` check is belt-and-braces.
    """
    rec_cfg = load_thresholds()["recommendation"]
    submit_min = rec_cfg["submit_min"]
    caveats_min = rec_cfg["caveats_min"]
    conf = score_result["confidence"]
    gaps = score_result["critical_gaps"]

    if conf >= submit_min and not gaps:
        rec = "submit"
        reason = f"Confidence {conf} ≥ {submit_min} with all required evidence present."
    elif conf >= caveats_min:
        rec = "submit_with_caveats"
        if gaps:
            reason = (f"Confidence {conf} in the caveats band [{caveats_min}, {submit_min}); "
                      f"gaps present — route to human review before filing.")
        else:
            reason = (f"Confidence {conf} in the caveats band [{caveats_min}, {submit_min}) — "
                      f"file only after human review.")
    else:
        rec = "do_not_submit"
        reason = (f"Confidence {conf} < {caveats_min}. "
                  + (score_result["gate_reasons"][0] if score_result["gate_reasons"]
                     else "Insufficient evidence to substantiate a rebuttal."))

    # what would change the recommendation: the missing evidence and why it matters
    missing_explain = [
        {"field": f, "why": score_result["per_field"][f]["why"],
         "required": score_result["per_field"][f]["required"]}
        for f in score_result["missing_fields"]
    ]
    missing_explain.sort(key=lambda x: (not x["required"]))  # required first

    return {
        "recommendation": rec,
        "reason": reason,
        "confidence": conf,
        "what_would_help": missing_explain,
    }
