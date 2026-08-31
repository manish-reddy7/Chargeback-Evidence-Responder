"""Unit tests for the deterministic evidence retriever (Phase 2)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json  # noqa: E402
from pipeline.common import DATA_DIR, FIELD_SOURCES  # noqa: E402
from pipeline.retriever import retrieve  # noqa: E402


def _seed(fam):
    return json.load(open(DATA_DIR / "seed_examples" / f"{fam}_should_win.json", encoding="utf-8"))


def test_retrieve_returns_all_family_fields_with_provenance():
    case = _seed("not_received")
    ev = retrieve(case, "not_received")
    # every field in the family checklist is present in the map
    assert set(ev.keys()) == set(FIELD_SOURCES["not_received"].keys())
    # provenance points back to the exact source record + key (rules.md R2)
    assert ev["tracking_number"]["source"] == "order.tracking_number"
    assert ev["delivery_confirmation"]["source"] == "order.delivery_confirmation"


def test_present_and_missing_fields_are_distinguished():
    case = _seed("not_received")
    ev = retrieve(case, "not_received")
    # this fixture is the "win_min" recipe: tracking present, photo/shipment absent
    assert ev["tracking_number"]["value"] is not None
    assert ev["tracking_number"]["weak"] is False
    assert ev["delivery_photo"]["value"] is None  # missing in this fixture


def test_unauthorized_pulls_from_transaction_and_history():
    case = _seed("unauthorized")
    ev = retrieve(case, "unauthorized")
    assert ev["threeds_status"]["source"] == "transaction.threeds_status"
    assert ev["device_match"]["source"] == "customer_history.device_match"


def test_unknown_family_returns_empty_map():
    assert retrieve(_seed("duplicate"), "no_such_family") == {}


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
