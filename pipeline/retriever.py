"""
pipeline/retriever.py — Stage 2: evidence field lookup (Phase 2).

Deterministic field lookups ONLY (rules.md R20). Given a case + its family, pull
the family's evidence fields out of the case's source records via the shared
common.FIELD_SOURCES map. No generation, no inference — every returned value
carries the source record + key it came from, so the evidentiary chain stays
auditable (rules.md R2).

Output shape (the "evidence map"):
    { field_name: { "value": <str|None>,   # None => the field is absent in the data
                    "weak":  <bool|None>,   # True => present but qualified/weak
                    "source": "record.key" } }
"""
from __future__ import annotations

from pipeline.common import FIELD_SOURCES


def retrieve(case, family) -> dict:
    if family not in FIELD_SOURCES:
        return {}
    evidence = {}
    for field, (record_name, key) in FIELD_SOURCES[family].items():
        record = case.get(record_name) or {}
        raw = record.get(key)  # None, or {"value": ..., "weak": bool}
        source = f"{record_name}.{key}"
        if raw is None:
            evidence[field] = {"value": None, "weak": None, "source": source}
        else:
            evidence[field] = {
                "value": raw.get("value"),
                "weak": bool(raw.get("weak", False)),
                "source": source,
            }
    return evidence
