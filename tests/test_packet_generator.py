"""Unit tests for the constrained packet generator (Phase 3).

Focus is on the guardrails, not prose quality:
  * present/weak evidence only ever reaches the packet; missing never does (R1/R6)
  * weak evidence is marked, never presented as strong (R2)
  * the deterministic renderer always passes its own validator (R2)
  * validate_packet catches a fabricated token (the LLM safety net, R2)
  * do-not-submit drafts NO packet, only an explanation (R7)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json  # noqa: E402
from pipeline.common import DATA_DIR  # noqa: E402
from pipeline.retriever import retrieve  # noqa: E402
from pipeline.scorer import score  # noqa: E402
from pipeline.packet_generator import (  # noqa: E402
    generate_packet, validate_packet, _present_and_weak, _render_deterministic,
    missing_clause_templates,
)


def _seed(fam):
    return json.load(open(DATA_DIR / "seed_examples" / f"{fam}_should_win.json", encoding="utf-8"))


def _gen(fam, backend="deterministic"):
    case = _seed(fam)
    s = score(retrieve(case, fam), fam)
    return case, s, generate_packet(case, fam, s, backend=backend)


def test_deterministic_packet_generated_for_should_win():
    for fam in ["not_received", "defective", "unauthorized", "duplicate"]:
        _, _, out = _gen(fam)
        assert out["recommendation"] in ("submit", "submit_with_caveats"), fam
        assert out["packet_text"], f"{fam} produced no packet"
        assert out["backend"].startswith("deterministic")


def test_missing_field_value_never_appears_in_packet():
    # not_received seed has shipment_date + delivery_photo missing (null in fixture).
    case, s, out = _gen("not_received")
    assert "shipment_date" in s["missing_fields"]
    # the missing fields contribute no clause, and (by construction) no value string
    used_fields = {e["field"] for e in out["evidence_used"]}
    assert "shipment_date" not in used_fields
    assert "delivery_photo" not in used_fields


def test_only_present_and_weak_reach_the_prompt():
    _, s, _ = _gen("not_received")
    used = _present_and_weak(s)
    statuses = {e["status"] for e in used}
    assert statuses <= {"present", "weak"}
    assert "missing" not in statuses


def test_weak_field_is_marked_not_presented_as_strong():
    # craft an evidence map with one weak field
    case = _seed("not_received")
    ev = retrieve(case, "not_received")
    ev["delivery_confirmation"]["weak"] = True  # force weak
    s = score(ev, "not_received")
    text = _render_deterministic(case, "not_received", _present_and_weak(s))
    # the weak marker must appear somewhere for the qualified field
    assert "[qualified" in text


def test_deterministic_packet_passes_its_own_validator():
    for fam in ["not_received", "defective", "unauthorized", "duplicate"]:
        case, _, out = _gen(fam)
        warnings = validate_packet(out["packet_text"], case, out["evidence_used"])
        assert warnings == [], f"{fam} deterministic packet raised {warnings}"


def test_validator_flags_a_fabricated_token():
    case, _, out = _gen("not_received")
    tampered = out["packet_text"] + "\nThe parcel was scanned at hub HUB-99999 on 2099-12-31."
    warnings = validate_packet(tampered, case, out["evidence_used"])
    assert any("HUB-99999" in w for w in warnings)
    assert any("2099-12-31" in w for w in warnings)


def test_validator_catches_fabricated_substring_of_a_real_id():
    # Regression (audit finding): a fabricated number that is a SUBSTRING of a
    # real id must still be flagged. The old substring-containment check let
    # '2024' pass because it sits inside the real txn id 'TXN-2024-0142'.
    case = {"dispute": {"dispute_id": "DP-0142", "transaction_id": "TXN-2024-0142",
                        "amount_inr": 4999}}
    evidence_used = [{"field": "tracking_number", "status": "present",
                      "value": "IN123456789", "source": "order.tracking_number"}]
    packet = ("This rebuttal concerns transaction TXN-2024-0142. A separate "
              "order 123 dated 2024 is unrelated.")
    warnings = validate_packet(packet, case, evidence_used)
    assert any("'123'" in w for w in warnings), warnings
    assert any("'2024'" in w for w in warnings), warnings
    # genuine, traceable tokens must NOT be flagged
    assert not any("TXN-2024-0142" in w for w in warnings), warnings


def test_clause_templates_cover_every_structure_field():
    # DRY invariant: every evidence field named in family_structures.yaml has a
    # clause template, so no field is silently dropped from a rendered packet.
    assert missing_clause_templates() == {}, missing_clause_templates()


def test_do_not_submit_produces_no_packet_but_explains():
    # empty case -> everything missing -> do_not_submit
    empty = {"dispute": {"dispute_id": "DP-X", "transaction_id": "TXN-X", "amount_inr": 100}}
    s = score(retrieve(empty, "not_received"), "not_received")
    out = generate_packet(empty, "not_received", s)
    assert out["recommendation"] == "do_not_submit"
    assert out["packet_text"] is None
    assert "tracking_number" in out["explanation"]
    assert out["flagged_for_review"] is False


def test_caveats_flags_for_review():
    # tracking + delivery_confirmation only -> 60 -> caveats band
    case = {"dispute": {"dispute_id": "DP-Y", "transaction_id": "TXN-Y", "amount_inr": 500},
            "order": {"tracking_number": {"value": "IN123", "weak": False},
                      "delivery_confirmation": {"value": "Signed", "weak": False}}}
    s = score(retrieve(case, "not_received"), "not_received")
    out = generate_packet(case, "not_received", s)
    assert out["recommendation"] == "submit_with_caveats"
    assert out["packet_text"]
    assert out["flagged_for_review"] is True


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
