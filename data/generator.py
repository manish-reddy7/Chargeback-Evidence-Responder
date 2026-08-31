"""
data/generator.py — Synthetic dispute-case generator (Phase 1).

Produces a frozen, hand-labeled held-out test set for the Chargeback Evidence
Responder. Run once; the output (data/test_set.json) is then treated as
read-only (rules.md R4: ground-truth labels are decided independently of, and
before, any pipeline run).

Design notes
------------
* Every case carries a GROUND-TRUTH label decided *by construction* from the
  real-world evidentiary logic of the case, NOT by running the scorer:
    - should_win  : a rebuttal is genuinely defensible / worth filing
    - should_lose : the dispute is not winnable or should be conceded
    - borderline  : genuinely ambiguous; human review is the right call
    - n/a         : reason code outside the 4 supported families (punt)
  The scorer NEVER sees these labels (no leakage). Metrics join on dispute_id.

* Evidence value convention (stored inside source records):
    None                              -> field is MISSING
    {"value": "<text>", "weak": False}-> field is PRESENT (strong)
    {"value": "<text>", "weak": True} -> field is WEAK
  The Retriever pulls these via common.FIELD_SOURCES; the Scorer grades them.

* Adversarial "hard" cases are included on purpose so the deterministic scorer
  makes *genuine* errors (false negatives + false positives). This keeps the
  reported precision/recall believable (rules.md R12) and gives the demo real
  limitation stories (rules.md R7).

Deterministic: fixed random seed => re-running reproduces the same test set.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta

# make the repo root importable whether run as `python3 data/generator.py`
# or from elsewhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.common import FIELD_SOURCES, TEST_SET_PATH, DATA_DIR  # noqa: E402

SEED = 20260827
random.seed(SEED)

# ---------------------------------------------------------------------------
# surface-value helpers (randomized flavour; do NOT change a case's label)
# ---------------------------------------------------------------------------
NAMES = ["R. Sharma", "A. Nair", "P. Iyer", "S. Gupta", "M. Khan", "D. Reddy",
         "K. Bose", "V. Menon", "T. Rao", "N. Verma"]
CARRIERS = ["BlueDart", "Delhivery", "DTDC", "India Post", "Ekart"]
CITIES = ["Mumbai", "Bengaluru", "Delhi", "Chennai", "Pune", "Hyderabad", "Kolkata"]
SKUS = [
    ("SKU-AUD-114", "Wireless over-ear headphones, black"),
    ("SKU-KTC-330", "Stainless steel cookware set, 5-piece"),
    ("SKU-APP-201", "Cotton kurta, size L, indigo"),
    ("SKU-ELC-778", "USB-C 65W fast charger"),
    ("SKU-BKS-042", "Hardcover novel, first edition"),
    ("SKU-HOM-560", "Ceramic table lamp, matte white"),
]
AMOUNTS = [499, 890, 1050, 1299, 1875, 2450, 3200, 4200, 5600, 7999, 9450, 12800]


def _present(value):
    return {"value": value, "weak": False}


def _weak(value):
    return {"value": value, "weak": True}


_counter = {"n": 0}


def _seq():
    _counter["n"] += 1
    return _counter["n"]


def rand_date(base_days_ago_min=10, base_days_ago_max=25):
    d = datetime(2026, 8, 27) - timedelta(days=random.randint(base_days_ago_min, base_days_ago_max))
    # add a realistic time-of-day so signatures/timestamps don't all read 00:00
    return d.replace(hour=random.randint(8, 20), minute=random.randint(0, 59))


def fmt_dt(d, with_time=True):
    return d.strftime("%Y-%m-%d %H:%M IST") if with_time else d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# per-family evidence catalogs: field -> (strong_factory, weak_factory)
# ---------------------------------------------------------------------------
def _nr_catalog():
    name = random.choice(NAMES)
    ship = rand_date(15, 25)
    deliv = ship + timedelta(days=random.randint(2, 5))
    carrier = random.choice(CARRIERS)
    trk = f"IN{random.randint(10**9, 10**10 - 1)}"
    return {
        "tracking_number": (lambda: trk,
                            lambda: f"{trk} (on file; carrier scan history unavailable)"),
        "delivery_confirmation": (lambda: f"Signed by: {name}, {fmt_dt(deliv)}",
                                  lambda: f"Left at door {fmt_dt(deliv, False)}; no signature captured"),
        "carrier": (lambda: carrier, lambda: f"{carrier} (self-reported, unverified)"),
        "shipment_date": (lambda: fmt_dt(ship, False), lambda: f"~{fmt_dt(ship, False)} (approx.)"),
        "delivery_date": (lambda: fmt_dt(deliv, False), lambda: f"~{fmt_dt(deliv, False)} (approx.)"),
        "delivery_photo": (lambda: "GPS-tagged drop-off photo on file",
                          lambda: "No photo on file; carrier reports GPS drop-off only"),
    }


def _def_catalog():
    sku, desc = random.choice(SKUS)
    tkt = random.randint(10000, 99999)
    return {
        "product_listing": (lambda: f"Listing snapshot at purchase: '{sku} — {desc}', full spec archived",
                            lambda: f"Partial listing text for {sku} recovered; product images not archived"),
        "return_policy": (lambda: "30-day return policy shown at checkout (policy v2.1)",
                         lambda: "Return policy referenced but version at purchase not archived"),
        "support_ticket_resolution": (lambda: f"Ticket #{tkt}: replacement offered, declined by customer",
                                      lambda: f"Ticket #{tkt} opened; no resolution recorded before dispute"),
        "item_condition_proof": (lambda: "Pre-ship QA photos + inspection checklist archived",
                                lambda: "Warehouse dispatch log only; no condition photos"),
    }


def _ua_catalog():
    n_prior = random.randint(5, 20)
    return {
        "threeds_status": (lambda: "3-D Secure authenticated (fully, liability shifted)",
                          lambda: "3-D Secure attempted, not completed"),
        "avs_result": (lambda: "AVS full match (Y)", lambda: "AVS partial match (P — ZIP only)"),
        "cvv_result": (lambda: "CVV2 match (M)", lambda: "CVV2 not provided at checkout"),
        "device_match": (lambda: f"Device fingerprint matches {random.randint(2, 6)} prior orders",
                        lambda: "New device for this account"),
        "ip_match": (lambda: f"Order IP in billing city ({random.choice(CITIES)})",
                    lambda: "Order IP same country, different city from billing"),
        "prior_purchase_history": (lambda: f"{n_prior} prior undisputed orders on this account",
                                   lambda: "2 prior orders; account 20 days old"),
    }


def _dup_catalog():
    a, b = f"ORD-{random.randint(10000,99999)}", f"ORD-{random.randint(10000,99999)}"
    t1 = rand_date(12, 20)
    t2 = t1 + timedelta(hours=random.randint(2, 8))
    return {
        "distinct_order_ids": (lambda: f"Order A: {a} / Order B: {b} (distinct order records)",
                              lambda: f"Two charges reference the same order {a}"),
        "distinct_timestamps": (lambda: f"Charge A {fmt_dt(t1)}, Charge B {fmt_dt(t2)} (hours apart)",
                               lambda: "Both charges within 40 seconds of each other"),
        "idempotency_key_trace": (lambda: "Distinct idempotency keys (idem_a / idem_b) in gateway log",
                                 lambda: "Idempotency key absent for one of the two charges"),
        "itemization_match": (lambda: "Different carts (distinct SKUs per order)",
                             lambda: "Line items identical across both charges"),
    }


CATALOG_BUILDERS = {
    "not_received": _nr_catalog,
    "defective": _def_catalog,
    "unauthorized": _ua_catalog,
    "duplicate": _dup_catalog,
}

REASON_CODE_POOL = {
    "not_received": ["13.1", "4855", "C08"],
    "defective": ["13.3", "4853", "C31"],
    "unauthorized": ["10.4", "4837", "10.1"],
    "duplicate": ["12.6.1", "4834", "P08"],
}
UNKNOWN_CODES = ["13.7", "4999", "ZZ01", "15.2", "4808"]


def build_evidence(family, spec):
    """Given a family and a {field: 'present'|'weak'} spec, return evidence values
    (fields not named in spec default to missing/None)."""
    catalog = CATALOG_BUILDERS[family]()
    out = {}
    for field, (strong_fn, weak_fn) in catalog.items():
        state = spec.get(field, "missing")
        if state == "present":
            out[field] = _present(strong_fn())
        elif state == "weak":
            out[field] = _weak(weak_fn())
        else:
            out[field] = None
    return out


def build_case(dispute_id, family, reason_code, label, rationale, spec):
    """Assemble a full case: nested source records + dispute metadata + label."""
    amount = random.choice(AMOUNTS)
    txn_id = f"TXN-{random.randint(10000, 99999)}"
    order_id = f"ORD-{random.randint(10000, 99999)}"
    cust_id = f"CUST-{random.randint(1000, 9999)}"
    created = rand_date(5, 20)
    deadline = created + timedelta(days=random.choice([7, 10, 14, 21]))

    # base source records with non-evidence context always present
    records = {
        "transaction": {
            "transaction_id": txn_id,
            "amount_inr": amount,
            "timestamp": fmt_dt(created),
            "payment_method": random.choice(["card", "card", "netbanking", "upi"]),
        },
        "order": {
            "order_id": order_id,
            "transaction_id": txn_id,
            "sku": random.choice(SKUS)[0],
            "shipping_address": f"{random.choice(CITIES)}, IN",
        },
        "customer_history": {
            "customer_id": cust_id,
            "account_age_days": random.randint(3, 1200),
            "prior_order_count": random.randint(0, 30),
        },
        "support_ticket": {},
        "duplicate_info": {},
    }

    # place evidence values into their source records via the shared FIELD_SOURCES map
    if family in FIELD_SOURCES:
        evidence = build_evidence(family, spec)
        for field, val in evidence.items():
            rec_name, key = FIELD_SOURCES[family][field]
            records[rec_name][key] = val

    return {
        "dispute_id": dispute_id,
        "family_expected": family,          # for analysis only; pipeline re-derives from reason_code
        "ground_truth": label,
        "gt_rationale": rationale,
        "dispute": {
            "dispute_id": dispute_id,
            "transaction_id": txn_id,
            "reason_code": reason_code,
            "amount_inr": amount,
            "deadline": fmt_dt(deadline, False),
            "status": "pending",
        },
        "transaction": records["transaction"],
        "order": records["order"],
        "customer_history": records["customer_history"],
        "support_ticket": records["support_ticket"] or None,
        "duplicate_info": records["duplicate_info"] or None,
    }


# ---------------------------------------------------------------------------
# RECIPES: (family, label, rationale, spec, count)
# spec maps evidence field -> 'present' | 'weak'; unlisted fields are missing.
# ---------------------------------------------------------------------------
def all_present(family):
    return {f: "present" for f in FIELD_SOURCES[family]}


RECIPES = [
    # ---------------- NOT RECEIVED ----------------
    ("not_received", "should_win",
     "Tracking, signed delivery confirmation, and supporting photo/dates all present.",
     all_present("not_received"), 6),
    ("not_received", "should_win",
     "Both required fields present with carrier and delivery date; minor supporting fields absent.",
     {"tracking_number": "present", "delivery_confirmation": "present",
      "carrier": "present", "delivery_date": "present"}, 4),
    ("not_received", "borderline",
     "Shipment is proven but delivery confirmation is weak (no signature) — outcome uncertain.",
     {"tracking_number": "present", "carrier": "present", "shipment_date": "present",
      "delivery_confirmation": "weak"}, 4),
    ("not_received", "should_lose",
     "No tracking and no delivery confirmation — delivery cannot be substantiated.",
     {"carrier": "present"}, 5),
    ("not_received", "should_lose",
     "Only an unverifiable tracking reference; no delivery confirmation of any kind.",
     {"tracking_number": "weak"}, 3),

    # ---------------- DEFECTIVE ----------------
    ("defective", "should_win",
     "Listing, return policy, support resolution, and QA condition proof all present.",
     all_present("defective"), 5),
    ("defective", "should_win",
     "Archived listing plus QA proof the item matched; policy/support absent but core defense holds.",
     {"product_listing": "present", "item_condition_proof": "present"}, 3),
    ("defective", "borderline",
     "Listing and policy shown, but no proof the shipped item matched and no resolution logged.",
     {"product_listing": "present", "return_policy": "present",
      "support_ticket_resolution": "weak"}, 4),
    ("defective", "should_lose",
     "No archived product listing — cannot show what the buyer was actually promised.",
     {"return_policy": "present", "support_ticket_resolution": "weak"}, 4),

    # ---------------- UNAUTHORIZED ----------------
    ("unauthorized", "should_win",
     "3DS authenticated, AVS/CVV match, known device, and legitimate history — strong authorization evidence.",
     {"threeds_status": "present", "avs_result": "present", "cvv_result": "present",
      "device_match": "present", "prior_purchase_history": "present", "ip_match": "present"}, 5),
    ("unauthorized", "borderline",
     "Some signals (AVS + known device) but 3DS only attempted and no CVV — mixed picture.",
     {"avs_result": "present", "device_match": "present",
      "threeds_status": "weak", "ip_match": "weak"}, 4),
    ("unauthorized", "should_lose",
     "No 3DS, AVS, CVV, or device match — no authentication evidence to rebut the fraud claim.",
     {"ip_match": "present", "prior_purchase_history": "present"}, 5),
    ("unauthorized", "should_lose",
     "No authentication signals of any kind on file.",
     {}, 2),

    # ---------------- DUPLICATE ----------------
    ("duplicate", "should_win",
     "Two distinct orders, distinct timestamps and idempotency keys, different carts — legitimately separate charges.",
     all_present("duplicate"), 5),
    ("duplicate", "borderline",
     "Different order IDs but near-identical timing and no idempotency trace — could be a double-post.",
     {"distinct_order_ids": "present", "distinct_timestamps": "weak"}, 3),
    ("duplicate", "should_lose",
     "Charges share one order with no distinct idempotency keys — a genuine duplicate; should be refunded, not fought.",
     {"itemization_match": "weak"}, 5),

    # ---------------- ADVERSARIAL / HARD CASES (create genuine scorer errors) ----------------
    # FN traps: genuinely winnable, but the rigid 'tracking required' rule misses them.
    ("not_received", "should_win",
     "HARD CASE (expected false negative): delivery confirmed by signature AND photo, but no carrier "
     "tracking number (local courier). Genuinely winnable, yet our checklist treats tracking as mandatory.",
     {"delivery_confirmation": "present", "delivery_photo": "present",
      "carrier": "present", "delivery_date": "present"}, 3),
    # FP traps: evidence looks strong to the scorer, but the dispute is genuinely not winnable.
    ("unauthorized", "should_lose",
     "HARD CASE (expected false positive): AVS/CVV/device all match, but this is a confirmed account "
     "takeover — authorization signals are present yet the charge is genuinely unauthorized. The "
     "sufficiency score cannot see the takeover.",
     {"avs_result": "present", "cvv_result": "present", "device_match": "present",
      "threeds_status": "present", "prior_purchase_history": "present"}, 3),
    ("not_received", "should_lose",
     "HARD CASE (expected false positive): tracking shows delivery, but to a superseded address the "
     "cardholder no longer controls — technically delivered, dispute still valid.",
     {"tracking_number": "present", "delivery_confirmation": "present",
      "carrier": "present", "delivery_date": "present"}, 2),
]


def generate():
    cases = []
    idx = 0
    for family, label, rationale, spec, count in RECIPES:
        for _ in range(count):
            idx += 1
            dispute_id = f"DP-{idx:04d}"
            reason_code = random.choice(REASON_CODE_POOL[family])
            cases.append(build_case(dispute_id, family, reason_code, label, rationale, spec))

    # UNKNOWN reason codes -> punt path (rules.md R10: report punts honestly)
    for _ in range(5):
        idx += 1
        dispute_id = f"DP-{idx:04d}"
        code = random.choice(UNKNOWN_CODES)
        # attach to a random family's data shape but with an unsupported code
        fam = random.choice(list(FIELD_SOURCES))
        c = build_case(dispute_id, fam, code, "n/a",
                       "Reason code outside the 4 supported families — routed to a human (punt).",
                       all_present(fam))
        c["family_expected"] = "unknown"
        cases.append(c)

    random.shuffle(cases)  # so the queue isn't grouped by family/label

    label_counts = {}
    for c in cases:
        label_counts[c["ground_truth"]] = label_counts.get(c["ground_truth"], 0) + 1

    return {
        "meta": {
            "generator_seed": SEED,
            "generated_at": "frozen — see rules.md R4 (labels fixed before pipeline runs)",
            "total_cases": len(cases),
            "label_counts": label_counts,
            "families": list(FIELD_SOURCES.keys()),
            "note": "Ground-truth labels decided by construction from evidentiary logic, "
                    "independent of any pipeline output. HARD CASE rationales flag cases "
                    "designed to make the deterministic scorer err (honesty per R12).",
        },
        "cases": cases,
    }


def write_seed_examples(dataset):
    """Write one clear should_win example per family to data/seed_examples/ for
    use as retriever/scorer unit-test fixtures (identical schema to the test set)."""
    seed_dir = DATA_DIR / "seed_examples"
    seed_dir.mkdir(parents=True, exist_ok=True)
    picked = {}
    for c in dataset["cases"]:
        fam = c["family_expected"]
        # prefer a clean, non-adversarial should_win as the canonical fixture
        if (fam in FIELD_SOURCES and c["ground_truth"] == "should_win"
                and not c["gt_rationale"].startswith("HARD CASE") and fam not in picked):
            picked[fam] = c
    for fam, c in picked.items():
        with open(seed_dir / f"{fam}_should_win.json", "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2, ensure_ascii=False)
    return list(picked.keys())


def main():
    dataset = generate()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEST_SET_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    seeds = write_seed_examples(dataset)
    print(f"Wrote {dataset['meta']['total_cases']} cases -> {TEST_SET_PATH}")
    print(f"Label counts: {dataset['meta']['label_counts']}")
    print(f"Seed examples written for families: {seeds}")


if __name__ == "__main__":
    main()
