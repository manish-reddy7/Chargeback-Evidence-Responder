"""
Shared helpers: repo paths + config loading.

Every pipeline stage reads its knobs from pipeline/config/*.yaml through here so
there is exactly one place that knows where config lives (rules.md R3: checklists
and weights are config, not code).
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import yaml

# common.py lives in pipeline/, so parents[1] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "pipeline" / "config"
PROMPTS_DIR = REPO_ROOT / "pipeline" / "prompts"
DATA_DIR = REPO_ROOT / "data"
AUDIT_DIR = REPO_ROOT / "audit"
DASHBOARD_DIR = REPO_ROOT / "dashboard"

TEST_SET_PATH = DATA_DIR / "test_set.json"
PIPELINE_OUTPUT_PATH = DATA_DIR / "pipeline_output.json"
AUDIT_TRAIL_PATH = AUDIT_DIR / "trail.jsonl"


@lru_cache(maxsize=1)
def load_families() -> dict:
    """Return the families config dict: {family_key: {display_name, evidence, ...}}."""
    with open(CONFIG_DIR / "families.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["families"]


@lru_cache(maxsize=1)
def load_thresholds() -> dict:
    """Return the full thresholds/scoring/costs config dict."""
    with open(CONFIG_DIR / "thresholds.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_family_structures() -> dict:
    """Return the per-family packet structure that drives BOTH the LLM prompt
    and the deterministic fallback renderer (pipeline/prompts/family_structures.yaml)."""
    with open(PROMPTS_DIR / "family_structures.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_prompt(name: str) -> str:
    """Read a versioned prompt file from pipeline/prompts/."""
    with open(PROMPTS_DIR / name, "r", encoding="utf-8") as f:
        return f.read()


def reason_code_to_family_map() -> dict:
    """Build {reason_code: family_key} from families.yaml (deterministic lookup)."""
    mapping = {}
    for fam_key, fam in load_families().items():
        for code in fam.get("reason_codes", []):
            mapping[str(code)] = fam_key
    return mapping


# Deterministic map from a family's evidence field to WHERE it lives in a case's
# source records: field_name -> (record_name, key_in_record). Both the synthetic
# data generator and the Evidence Retriever import this, so there is exactly one
# schema they agree on. This is the "evidentiary chain" backbone (rules.md R2):
# every retrieved value can name the source record + key it came from.
FIELD_SOURCES = {
    "not_received": {
        "tracking_number":       ("order", "tracking_number"),
        "delivery_confirmation": ("order", "delivery_confirmation"),
        "carrier":               ("order", "carrier"),
        "shipment_date":         ("order", "shipment_date"),
        "delivery_date":         ("order", "delivery_date"),
        "delivery_photo":        ("order", "delivery_photo"),
    },
    "defective": {
        "product_listing":           ("order", "product_listing"),
        "return_policy":             ("order", "return_policy"),
        "support_ticket_resolution": ("support_ticket", "resolution"),
        "item_condition_proof":      ("order", "item_condition_proof"),
    },
    "unauthorized": {
        "threeds_status":         ("transaction", "threeds_status"),
        "avs_result":             ("transaction", "avs_result"),
        "cvv_result":             ("transaction", "cvv_result"),
        "device_match":           ("customer_history", "device_match"),
        "ip_match":               ("customer_history", "ip_match"),
        "prior_purchase_history": ("customer_history", "prior_purchase_history"),
    },
    "duplicate": {
        "distinct_order_ids":    ("duplicate_info", "distinct_order_ids"),
        "distinct_timestamps":   ("duplicate_info", "distinct_timestamps"),
        "idempotency_key_trace": ("duplicate_info", "idempotency_key_trace"),
        "itemization_match":     ("duplicate_info", "itemization_match"),
    },
}

