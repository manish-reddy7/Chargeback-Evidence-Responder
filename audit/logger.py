"""
audit/logger.py — append-only decision + override log (Phase 4).

Every case that flows through the pipeline writes exactly ONE decision entry
(rules.md R16). Entries are only ever appended as JSON lines — there is no public
function that edits or deletes a prior entry. Human overrides of a recommendation
are captured as their OWN appended entries (rules.md R17), so the original machine
decision and the human's change both survive, in order, forever.

Why JSONL: each line is a self-contained, immutable record; appending is atomic-ish
and never rewrites history; and the file is trivially diffable and greppable for a
demo. The full packet text lives in the pipeline output file (for the dashboard);
the trail stores a sha256 of the packet so you can prove *what* was signed off on
without duplicating it.

`reset_trail()` exists ONLY to start a fresh reproducible batch evaluation run; it
is never called during live operation. The append-only guarantee is about never
mutating an entry once written — not about the file being eternal across dev runs.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pipeline.common import AUDIT_DIR, AUDIT_TRAIL_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(text) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _append(entry: dict) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_TRAIL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def reset_trail() -> None:
    """Start a fresh trail for a reproducible batch run. NOT used in live operation.

    We truncate (open in "w" mode) rather than unlink: some mounted/synced
    filesystems disallow delete but permit write, and truncation empties the file
    just the same. The append-only guarantee is about never mutating a *written*
    entry mid-run — not about the dev file surviving across reproducible re-runs.
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_TRAIL_PATH, "w", encoding="utf-8") as f:
        f.write("")


def log_decision(case, family, score_result, packet_result) -> dict:
    """Append one immutable decision record for a case (rules.md R16).

    Stores the decision, the evidentiary chain (field + status + source, no raw
    values), any gate reasons / validation warnings, and a hash of the packet.
    """
    dispute = case.get("dispute", {})
    entry = {
        "entry_type": "decision",
        "ts": _now_iso(),
        "dispute_id": dispute.get("dispute_id"),
        "reason_code": dispute.get("reason_code"),
        "family": family,
        "confidence": score_result.get("confidence"),
        "recommendation": packet_result.get("recommendation"),
        "evidence_chain": [
            {"field": e["field"], "status": e["status"], "source": e["source"]}
            for e in packet_result.get("evidence_used", [])
        ],
        "critical_gaps": score_result.get("critical_gaps", []),
        "gate_reasons": score_result.get("gate_reasons", []),
        "validation_warnings": packet_result.get("validation_warnings", []),
        "flagged_for_review": packet_result.get("flagged_for_review", False),
        "backend": packet_result.get("backend"),
        "packet_sha256": _sha256(packet_result.get("packet_text")),
        "packet_drafted": packet_result.get("packet_text") is not None,
        "human_review_required": packet_result.get("recommendation") == "submit_with_caveats"
        or bool(packet_result.get("validation_warnings")),
    }
    _append(entry)
    return entry


def record_override(dispute_id, original_recommendation, override_recommendation,
                    actor, note="") -> dict:
    """Append a human override as its own entry (rules.md R17). Never edits the
    original decision — the machine call and the human change both persist."""
    entry = {
        "entry_type": "override",
        "ts": _now_iso(),
        "dispute_id": dispute_id,
        "original_recommendation": original_recommendation,
        "override_recommendation": override_recommendation,
        "actor": actor,
        "note": note,
    }
    _append(entry)
    return entry


def read_trail() -> list:
    """Return all trail entries in order (decisions + overrides)."""
    if not AUDIT_TRAIL_PATH.exists():
        return []
    out = []
    with open(AUDIT_TRAIL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
