"""
pipeline/packet_generator.py — Stage 4: the ONE generative step (Phase 3).

This is the only place in the pipeline that may call an LLM (rules.md R20). Every
other stage (classifier / retriever / scorer) is deterministic. Even here, the
model is boxed in on all sides:

  * It is given ONLY the present/weak evidence fields — missing fields are filtered
    out before the prompt is ever built (`_present_and_weak`). The model literally
    cannot "fill a gap" because the gap is not in its context. This is the primary,
    STRUCTURAL anti-fabrication guardrail (rules.md R1, R6).
  * The system prompt forbids inventing facts, dates, names, or policy language.
  * After generation, `validate_packet()` scans the draft for number/date/ID-like
    tokens that do not trace back to a provided value and flags them for human
    review (rules.md R2 — evidentiary chain; belt-and-braces over the prompt).
  * Do-not-submit cases produce NO rebuttal packet at all — just an explanation of
    what evidence would change the call (rules.md R7).

The system NEVER files the packet. Output terminates at "packet ready for human
sign-off" (rules.md R5) — there is no network call to any dispute-filing API here
or anywhere downstream.

Backend selection (provider-agnostic):
  * "anthropic"      — used only if ANTHROPIC_API_KEY is set AND the `anthropic`
                       SDK imports. Makes exactly one constrained Messages call.
  * "ollama"         — calls a local/remote Ollama server's /api/chat endpoint
                       (OLLAMA_HOST, default http://localhost:11434; OLLAMA_MODEL,
                       default "llama3.1"). Auto-selected if OLLAMA_HOST or
                       OLLAMA_MODEL is set and no Anthropic key is present. Uses
                       only the Python standard library (urllib) — no extra
                       dependency needed.
  * "deterministic"  — the default fallback. Renders the packet from fixed per-field
                       clause templates using ONLY the provided evidence values, so
                       the whole pipeline runs + evaluates reproducibly with no key,
                       no SDK, and no network. The deterministic renderer is also the
                       reference for what a compliant packet looks like.

Both backends consume the SAME family structure (family_structures.yaml), so a
packet written by the model and one written by the template have the same shape.
"""
from __future__ import annotations

import os
import re

from pipeline.common import load_family_structures, read_prompt
from pipeline.scorer import recommend

# ---------------------------------------------------------------------------
# Deterministic renderer: one clause template per (family, field). Each template
# uses ONLY the field's provided {value} — never any other fact. Adding a field
# to a family_structures evidence section without a clause here will simply omit
# it from the rendered packet (safe by default — it can never fabricate), but the
# DRY invariant between family_structures.yaml and these templates is enforced by
# a unit test via `missing_clause_templates()` below.
# ---------------------------------------------------------------------------
CLAUSE_TEMPLATES = {
    "not_received": {
        "tracking_number":       "The shipment was dispatched under tracking number {value}.",
        "carrier":               "The parcel was handled by carrier {value}.",
        "shipment_date":         "Carrier records show the order was shipped on {value}.",
        "delivery_date":         "Carrier records show the order was delivered on {value}.",
        "delivery_confirmation": "Delivery was confirmed by the carrier: {value}.",
        "delivery_photo":        "A proof-of-delivery photo is on file: {value}.",
    },
    "defective": {
        "product_listing":           "The product listing shown to the buyer at the time of sale described the item as: {value}.",
        "item_condition_proof":      "The condition of the item prior to shipment was documented: {value}.",
        "return_policy":             "The return and refund policy presented to the buyer at purchase stated: {value}.",
        "support_ticket_resolution": "The buyer's support interaction was resolved as follows: {value}.",
    },
    "unauthorized": {
        "threeds_status":         "The transaction carried the following 3-D Secure authentication status: {value}.",
        "avs_result":             "Address Verification (AVS) on the transaction returned: {value}.",
        "cvv_result":             "Card Verification (CVV2) on the transaction returned: {value}.",
        "device_match":           "Device analysis on the order returned: {value}.",
        "ip_match":               "The originating network of the order was assessed as: {value}.",
        "prior_purchase_history": "The account's prior purchase history on file shows: {value}.",
    },
    "duplicate": {
        "distinct_order_ids":    "The disputed charges correspond to distinct order identifiers: {value}.",
        "distinct_timestamps":   "The charges were authorized at distinct times: {value}.",
        "idempotency_key_trace": "The payment processing trace shows distinct idempotency keys: {value}.",
        "itemization_match":     "The cart contents differ across the charges: {value}.",
    },
}

WEAK_MARKER = " [qualified / limited evidence]"


def missing_clause_templates() -> dict:
    """Fields named in a family_structures evidence section that have no clause
    template here. The renderer safely omits such fields (it never fabricates), but
    they would silently never appear in a packet — so a unit test asserts this is
    empty, keeping family_structures.yaml and CLAUSE_TEMPLATES in sync (DRY)."""
    gaps = {}
    for family, fam in load_family_structures().items():
        clauses = CLAUSE_TEMPLATES.get(family, {})
        for sec in fam.get("sections", []):
            if sec.get("kind") != "evidence":
                continue
            for field in sec.get("fields", []):
                if field not in clauses:
                    gaps.setdefault(family, []).append(field)
    return gaps


# ---------------------------------------------------------------------------
# Backend selection + the single LLM call
# ---------------------------------------------------------------------------
def default_backend() -> str:
    """Prefer a real Anthropic call when possible; then Ollama; otherwise deterministic.

    We only pick "anthropic" if BOTH the key is set and the SDK imports. We pick
    "ollama" if OLLAMA_HOST or OLLAMA_MODEL is set (opt-in, since an unreachable
    Ollama server would otherwise silently swallow every case into the fallback
    path). The pipeline never hard-fails in an offline environment (this repo is
    built to run with no key/SDK/network — the deterministic backend is fully
    sufficient).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
            return "anthropic"
        except Exception:
            pass
    if os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_MODEL"):
        return "ollama"
    return "deterministic"


def _call_anthropic(system_prompt: str, user_prompt: str) -> str:
    """Exactly one constrained Messages call. Any failure raises to the caller,
    which falls back to the deterministic renderer."""
    import anthropic

    model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=1500,
        temperature=0,  # this is a factual document, not creative writing
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    """Exactly one constrained chat call to a local/remote Ollama server. Any
    failure raises to the caller, which falls back to the deterministic renderer.

    Uses the stdlib (urllib) rather than the `ollama` package, so no extra
    dependency is needed beyond a reachable server (stack.md: don't add deps
    without updating that file first).
    """
    import json as _json
    import urllib.error
    import urllib.request

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0},  # this is a factual document, not creative writing
    }
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=_json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = _json.loads(resp.read().decode("utf-8"))
    return (body.get("message", {}).get("content") or "").strip()


# ---------------------------------------------------------------------------
# Prompt assembly (shared by the LLM backend)
# ---------------------------------------------------------------------------
def _present_and_weak(score_result) -> list:
    """The evidence the packet is allowed to use: present + weak fields ONLY, in
    family order. Missing fields are dropped here so they never reach the model —
    the structural anti-fabrication guardrail (rules.md R1/R6)."""
    used = []
    for field, d in score_result["per_field"].items():
        if d["status"] in ("present", "weak"):
            used.append({
                "field": field,
                "status": d["status"],
                "value": d["value"],
                "source": d["source"],
            })
    return used


def build_evidence_block(evidence_used) -> str:
    """Format the present/weak evidence for the user prompt (spec format)."""
    if not evidence_used:
        return "(no admissible evidence was provided)"
    lines = []
    for e in evidence_used:
        lines.append(f"- Field: {e['field']}")
        lines.append(f"  Status: {e['status']}")
        lines.append(f"  Value: {e['value']}")
    return "\n".join(lines)


def render_family_structure(family) -> str:
    """Human-readable 'PACKET STRUCTURE TO FOLLOW' block for the LLM prompt,
    derived from family_structures.yaml so prompt + template never diverge."""
    fam = load_family_structures()[family]
    out = []
    for i, sec in enumerate(fam["sections"], 1):
        out.append(f"{i}. {sec['name']} — {sec['instruction']}")
    return "\n".join(out)


def build_user_prompt(case, family, evidence_used) -> str:
    dispute = case.get("dispute", {})
    template = read_prompt("user_template.txt")
    fam_display = load_family_structures().get(family, {}).get("claim", family)
    return template.format(
        family_name=family.replace("_", " ").title(),
        dispute_id=dispute.get("dispute_id", "—"),
        amount=f"₹{dispute.get('amount_inr', '—')}",
        transaction_id=dispute.get("transaction_id", "—"),
        evidence_block=build_evidence_block(evidence_used),
        family_structure=render_family_structure(family),
    )


# ---------------------------------------------------------------------------
# Deterministic renderer (the default backend)
# ---------------------------------------------------------------------------
def _summary_section(case) -> str:
    dispute = case.get("dispute", {})
    txn = case.get("transaction", {})
    txn_id = dispute.get("transaction_id") or txn.get("transaction_id")
    amount = dispute.get("amount_inr", txn.get("amount_inr"))
    when = txn.get("timestamp")
    bits = []
    if txn_id:
        bits.append(f"transaction {txn_id}")
    if amount is not None:
        bits.append(f"in the amount of ₹{amount}")
    if when:
        bits.append(f"processed on {when}")
    if not bits:
        return "Transaction details were not available."
    return "This rebuttal concerns " + ", ".join(bits) + "."


def _render_deterministic(case, family, evidence_used) -> str:
    """Render the packet from fixed clause templates using ONLY provided values."""
    fam = load_family_structures()[family]
    used_by_field = {e["field"]: e for e in evidence_used}
    clauses = CLAUSE_TEMPLATES.get(family, {})
    parts = []

    for sec in fam["sections"]:
        kind = sec["kind"]
        parts.append(f"## {sec['name']}")

        if kind == "summary":
            parts.append(_summary_section(case))

        elif kind == "evidence":
            body = []
            for field in sec.get("fields", []):
                e = used_by_field.get(field)
                if not e or field not in clauses:
                    continue  # field missing OR no template -> silently omit (never fabricate)
                sentence = clauses[field].format(value=e["value"])
                if e["status"] == "weak":
                    sentence += WEAK_MARKER
                body.append(sentence)
            parts.append(" ".join(body) if body else "Not available.")

        elif kind == "conclusion":
            claim = fam["claim"]
            parts.append(
                f"Based solely on the evidence set out above, the merchant's records "
                f"support that {claim}."
            )
        parts.append("")  # blank line between sections

    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Post-generation validator (rules.md R2 — evidentiary chain)
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./:\-]*\d[A-Za-z0-9./:\-]*")


def _allowed_tokens(case, evidence_used) -> set:
    """The set of digit-bearing tokens a packet is allowed to contain: those that
    appear in a provided evidence value or in the dispute/transaction metadata we
    render in the summary.

    Tokenized with the SAME regex used on the packet, then compared by
    token-EQUALITY (membership in this set) — not substring containment. Substring
    containment used to let a fabricated '2024' slip through just because it sits
    inside a real transaction id like 'txn-2024-0142'; equality closes that hole."""
    dispute = case.get("dispute", {})
    txn = case.get("transaction", {})
    allowed_values = []
    for e in evidence_used:
        if e.get("value") is not None:
            allowed_values.append(str(e["value"]))
    for src in (dispute, txn):
        for k in ("dispute_id", "transaction_id", "amount_inr", "reason_code",
                  "deadline", "timestamp"):
            if src.get(k) is not None:
                allowed_values.append(str(src[k]))
    tokens = set()
    for val in allowed_values:
        for m in _TOKEN_RE.findall(val):
            t = m.strip(".-/:").lower()
            if t:
                tokens.add(t)
    return tokens


def validate_packet(packet_text, case, evidence_used) -> list:
    """Flag number/date/ID-like tokens in the packet that do NOT appear in any
    provided value or dispute metadata. Returns a list of warning strings.

    The deterministic renderer, using only provided values, should always return
    []. For the LLM backend this is the safety net that catches a hallucinated
    date, amount, or tracking number and routes the packet to human review.

    Scope note (honest limitation): this nets digit-bearing tokens — the
    high-value fabrication vectors in chargeback evidence (amounts, dates,
    tracking/order IDs). It is a backstop OVER the primary, structural guarantee
    (missing fields are filtered out before generation in `_present_and_weak`), not
    a substitute for it; a purely alphabetic fabrication on the LLM path would
    still rely on human sign-off (rules.md R5) to catch."""
    if not packet_text:
        return []
    allowed = _allowed_tokens(case, evidence_used)
    warnings = []
    seen = set()
    for m in _TOKEN_RE.findall(packet_text):
        tok = m.strip(".-/:")
        low = tok.lower()
        if not tok or low in seen:
            continue
        seen.add(low)
        if low not in allowed:
            warnings.append(
                f"Unverifiable token '{tok}' does not trace to any provided evidence "
                f"value — requires human verification before filing."
            )
    return warnings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def _do_not_submit_explanation(rec) -> str:
    """Plain-language explanation for a do-not-submit call (no packet is drafted)."""
    lines = [rec["reason"], ""]
    if rec["what_would_help"]:
        lines.append("Evidence that would change this recommendation:")
        for item in rec["what_would_help"]:
            tag = "required" if item["required"] else "supporting"
            lines.append(f"  - {item['field']} ({tag}): {item['why']}")
    else:
        lines.append("No additional evidence is available to strengthen this case.")
    return "\n".join(lines)


def generate_packet(case, family, score_result, backend=None) -> dict:
    """Produce a rebuttal packet (or a do-not-submit explanation) for one case.

    Returns:
        {
          recommendation:      submit | submit_with_caveats | do_not_submit,
          packet_text:         str | None (None for do_not_submit),
          backend:             "anthropic" | "deterministic" | None,
          evidence_used:       [{field, status, value, source}],  # present/weak only
          validation_warnings: [str],
          flagged_for_review:  bool,
          explanation:         str,   # why this call / what would help
        }
    """
    rec = recommend(score_result)
    decision = rec["recommendation"]
    evidence_used = _present_and_weak(score_result)

    # Do-not-submit: NO packet is drafted (rules.md R7). We return the honest
    # explanation of what evidence is missing instead.
    if decision == "do_not_submit":
        return {
            "recommendation": decision,
            "packet_text": None,
            "backend": None,
            "evidence_used": evidence_used,
            "validation_warnings": [],
            "flagged_for_review": False,
            "explanation": _do_not_submit_explanation(rec),
        }

    backend = backend or default_backend()
    used_backend = backend
    packet_text = None

    if backend == "anthropic":
        try:
            system_prompt = read_prompt("system.txt")
            user_prompt = build_user_prompt(case, family, evidence_used)
            packet_text = _call_anthropic(system_prompt, user_prompt)
            if not packet_text:
                raise RuntimeError("empty completion")
        except Exception as exc:  # fall back, never hard-fail the pipeline
            used_backend = f"deterministic (anthropic fallback: {type(exc).__name__})"
            packet_text = _render_deterministic(case, family, evidence_used)
    elif backend == "ollama":
        try:
            system_prompt = read_prompt("system.txt")
            user_prompt = build_user_prompt(case, family, evidence_used)
            packet_text = _call_ollama(system_prompt, user_prompt)
            if not packet_text:
                raise RuntimeError("empty completion")
        except Exception as exc:  # fall back, never hard-fail the pipeline
            used_backend = f"deterministic (ollama fallback: {type(exc).__name__})"
            packet_text = _render_deterministic(case, family, evidence_used)
    else:
        packet_text = _render_deterministic(case, family, evidence_used)

    warnings = validate_packet(packet_text, case, evidence_used)
    flagged = bool(warnings) or decision == "submit_with_caveats"

    return {
        "recommendation": decision,
        "packet_text": packet_text,
        "backend": used_backend,
        "evidence_used": evidence_used,
        "validation_warnings": warnings,
        "flagged_for_review": flagged,
        "explanation": rec["reason"],
    }
