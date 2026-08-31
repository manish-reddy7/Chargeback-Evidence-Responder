"""
pipeline/classifier.py — Stage 1: reason code -> family (Phase 2).

Deterministic lookup ONLY (rules.md R20: no LLM here). Reason codes are a fixed,
known vocabulary; a code not in families.yaml classifies as UNKNOWN and is punted
to a human rather than force-fit into a family (rules.md R10 punt honesty).
"""
from __future__ import annotations

from typing import Optional

from pipeline.common import reason_code_to_family_map


def classify(reason_code) -> Optional[str]:
    """Return the family key for a reason code, or None if unsupported (punt)."""
    if reason_code is None:
        return None
    return reason_code_to_family_map().get(str(reason_code).strip())


def classify_case(case) -> Optional[str]:
    return classify(case.get("dispute", {}).get("reason_code"))
