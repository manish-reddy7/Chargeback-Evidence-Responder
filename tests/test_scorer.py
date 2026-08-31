"""Unit tests for the deterministic sufficiency scorer + recommendation (Phase 2/3)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json  # noqa: E402
from pipeline.common import DATA_DIR, load_thresholds  # noqa: E402
from pipeline.retriever import retrieve  # noqa: E402
from pipeline.scorer import score, recommend  # noqa: E402

TH = load_thresholds()
SUBMIT_MIN = TH["recommendation"]["submit_min"]
CAVEATS_MIN = TH["recommendation"]["caveats_min"]
REQ_CEIL = TH["scoring"]["required_missing_ceiling"]
ANY_CEIL = TH["scoring"]["require_any_ceiling"]


def _ev(**fields):
    """Build an evidence map directly: name -> 'present' | 'weak' | None."""
    out = {}
    for name, state in fields.items():
        if state is None:
            out[name] = {"value": None, "weak": None, "source": None}
        elif state == "weak":
            out[name] = {"value": "…", "weak": True, "source": None}
        else:
            out[name] = {"value": "…", "weak": False, "source": None}
    return out


def _seed(fam):
    return json.load(open(DATA_DIR / "seed_examples" / f"{fam}_should_win.json", encoding="utf-8"))


def test_all_present_scores_100_and_submits():
    ev = _ev(tracking_number="p", delivery_confirmation="p", carrier="p",
             shipment_date="p", delivery_date="p", delivery_photo="p")
    s = score(ev, "not_received")
    assert s["confidence"] == 100.0
    assert recommend(s)["recommendation"] == "submit"


def test_missing_required_field_gates_to_do_not_submit():
    # tracking_number is required; drop it, keep everything else strong
    ev = _ev(delivery_confirmation="p", carrier="p", shipment_date="p",
             delivery_date="p", delivery_photo="p")  # tracking_number missing
    s = score(ev, "not_received")
    assert "tracking_number" in s["critical_gaps"]
    assert s["confidence"] <= REQ_CEIL
    assert recommend(s)["recommendation"] == "do_not_submit"


def test_require_any_gate_for_unauthorized():
    # no threeds/avs/cvv/device -> require_any gate fires
    ev = _ev(ip_match="p", prior_purchase_history="p")
    s = score(ev, "unauthorized")
    assert s["gate_reasons"], "expected a require_any gate reason"
    assert s["confidence"] <= ANY_CEIL
    assert recommend(s)["recommendation"] == "do_not_submit"


def test_weak_field_earns_half_weight():
    ev = _ev(tracking_number="p", delivery_confirmation="weak")
    s = score(ev, "not_received")
    pf = s["per_field"]
    assert pf["delivery_confirmation"]["status"] == "weak"
    # delivery_confirmation weight is 35 -> weak earns 17.5
    assert pf["delivery_confirmation"]["earned"] == 17.5
    assert pf["tracking_number"]["earned"] == 25.0


def test_caveats_band_middle_confidence():
    # tracking(25)+delivery_confirmation(35) = 60 -> between caveats_min and submit_min
    ev = _ev(tracking_number="p", delivery_confirmation="p")
    s = score(ev, "not_received")
    assert CAVEATS_MIN <= s["confidence"] < SUBMIT_MIN
    assert recommend(s)["recommendation"] == "submit_with_caveats"


def test_should_win_seed_fixtures_recommend_fighting():
    for fam in ["not_received", "defective", "unauthorized", "duplicate"]:
        case = _seed(fam)
        s = score(retrieve(case, fam), fam)
        rec = recommend(s)["recommendation"]
        assert rec in ("submit", "submit_with_caveats"), f"{fam} fixture got {rec} (conf {s['confidence']})"


def test_do_not_submit_explains_what_would_help():
    ev = _ev(carrier="p")  # both required fields missing
    r = recommend(score(ev, "not_received"))
    fields = [x["field"] for x in r["what_would_help"]]
    assert "tracking_number" in fields and "delivery_confirmation" in fields
    # required-missing fields are surfaced first
    assert r["what_would_help"][0]["required"] is True


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
