"""Unit tests for the deterministic classifier (Phase 2). Runs under pytest OR
as `python3 tests/test_classifier.py`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json  # noqa: E402
from pipeline.classifier import classify, classify_case  # noqa: E402
from pipeline.common import TEST_SET_PATH  # noqa: E402


def test_known_codes_map_to_expected_families():
    assert classify("13.1") == "not_received"
    assert classify("4855") == "not_received"
    assert classify("13.3") == "defective"
    assert classify("10.4") == "unauthorized"
    assert classify("4837") == "unauthorized"
    assert classify("12.6.1") == "duplicate"


def test_unknown_code_returns_none():
    for code in ["13.7", "4999", "ZZ01", "15.2", "", None]:
        assert classify(code) is None


def test_whitespace_is_tolerated():
    assert classify("  13.1 ") == "not_received"


def test_every_case_in_test_set_classifies_correctly():
    data = json.load(open(TEST_SET_PATH, encoding="utf-8"))
    for c in data["cases"]:
        fam = classify_case(c)
        if c["family_expected"] == "unknown":
            assert fam is None, f"{c['dispute_id']} should punt but got {fam}"
        else:
            assert fam == c["family_expected"], f"{c['dispute_id']}: {fam} != {c['family_expected']}"


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
