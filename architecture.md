# Architecture — Chargeback Evidence Responder

## 1. System Overview

```
                    ┌─────────────────────┐
                    │   Synthetic Data     │
                    │   Generator (offline)│
                    └──────────┬───────────┘
                               │ seeds
                               ▼
 ┌──────────────┐     ┌────────────────────┐     ┌──────────────────┐
 │  Dispute      │────▶│  1. Classifier      │────▶│  2. Evidence      │
 │  Event Input  │     │  (reason code →     │     │  Retriever        │
 │  (webhook/    │     │   family)           │     │  (deterministic,  │
 │   test event) │     └────────────────────┘     │   rule-based)     │
 └──────────────┘                                  └────────┬──────────┘
                                                              │ evidence map
                                                              ▼
                                                    ┌────────────────────┐
                                                    │  3. Sufficiency    │
                                                    │  Scorer            │
                                                    │  (checklist +      │
                                                    │   confidence)      │
                                                    └────────┬──────────┘
                                                              │
                                       ┌──────────────────────┼──────────────────────┐
                                       ▼                      ▼                      ▼
                              High confidence         Medium confidence     Low confidence
                                       │                      │                      │
                                       ▼                      ▼                      ▼
                          ┌─────────────────────┐   ┌─────────────────┐   ┌──────────────────┐
                          │ 4. Packet Generator  │   │ Same as high,   │   │ Do-not-submit     │
                          │ (LLM, constrained    │   │ flagged for     │   │ explanation +      │
                          │  to retrieved fields)│   │ human review    │   │ missing-evidence   │
                          └──────────┬───────────┘   └────────┬────────┘   │ list               │
                                     │                        │            └────────┬──────────┘
                                     └────────────┬───────────┘                     │
                                                  ▼                                 ▼
                                       ┌────────────────────────────────────────────────┐
                                       │  5. Audit Trail Logger (immutable per case)     │
                                       └─────────────────────┬────────────────────────────┘
                                                              ▼
                                                    ┌────────────────────┐
                                                    │  Dashboard (UI)     │
                                                    │  Queue → Detail →   │
                                                    │  Packet → Trail     │
                                                    └────────────────────┘
```

## 2. Components

### 2.1 Synthetic Data Generator (offline, pre-buildathon-demo)
- Produces 50–100 dispute cases spanning the 4 reason code families.
- Each case includes: transaction record, order record, customer history, optional support ticket, dispute metadata.
- Each case is tagged with a **ground-truth label** (should-win / should-lose / borderline) decided independently of the model, before any pipeline run — this is the held-out eval set.
- Deliberately includes edge cases: missing tracking data, ambiguous AVS mismatch, genuine duplicate charges, legitimate "not received" claims.

### 2.2 Classifier
- Input: dispute reason code string + metadata.
- Output: one of the 4 families.
- Implementation: simple mapping/lookup table (reason codes are a fixed, known vocabulary per card network) — no ML needed here, keep it deterministic and auditable.

### 2.3 Evidence Retriever
- Input: family + transaction/order/customer IDs.
- Output: a structured evidence map — one field per checklist item for that family (e.g., `tracking_number`, `delivery_confirmation`, `avs_result`).
- Implementation: deterministic field lookups against the synthetic data store. No generation, no LLM. This keeps the evidentiary chain auditable ("this claim came from field X").

### 2.4 Sufficiency Scorer
- Input: evidence map for the family.
- Output: per-field status (present / missing / weak) + an overall confidence score.
- Implementation: rule-based checklist with weights per field (e.g., delivery confirmation is a hard requirement for "not received"; a device match is a strong but not sufficient signal alone for "unauthorized"). Weights and thresholds should be a config file, not hardcoded, so they're visibly tunable in the demo.

### 2.5 Packet Generator
- Input: evidence map (only fields marked present/weak, never missing ones) + family template.
- Output: formatted rebuttal narrative + evidence attachments list.
- Implementation: LLM call (Claude), but constrained — the prompt passes only the retrieved structured fields and instructs the model to reference only those fields, no invented claims. Optionally validate output post-hoc by checking every factual assertion maps to a passed-in field (simple keyword/field-presence check).

### 2.6 Audit Trail Logger
- Writes one immutable record per processed dispute: input snapshot, classifier output, evidence map, confidence score, recommendation, timestamp, and (if overridden by a human) the override reason.
- Storage: append-only log (flat file or simple DB table) — no edits, only appends.

### 2.7 Dashboard
- Dispute queue (list, filterable by recommendation type and confidence).
- Case detail: evidence checklist view, generated packet, confidence breakdown.
- Audit trail view per case.
- See `design.md` for visual/UX direction.

## 3. Data Model (simplified)

```
Dispute
 ├─ dispute_id
 ├─ transaction_id
 ├─ reason_code
 ├─ amount
 ├─ deadline
 └─ status (pending / submitted / declined-to-submit)

Transaction
 ├─ transaction_id
 ├─ avs_result, cvv_result, threeds_status
 ├─ device_id, ip_address
 └─ timestamp

Order
 ├─ order_id
 ├─ transaction_id (fk)
 ├─ sku, shipping_address
 ├─ carrier, tracking_number, delivery_status
 └─ delivery_confirmation (bool/photo ref)

CustomerHistory
 ├─ customer_id
 ├─ account_age_days
 ├─ prior_order_count
 └─ device_ip_match_history

AuditEntry
 ├─ dispute_id (fk)
 ├─ pipeline_stage_snapshot (json)
 ├─ confidence_score
 ├─ recommendation
 └─ timestamp
```

## 4. Why this shape wins on the judging bar
- **Explainable**: every stage's output is inspectable; the packet generator can't introduce unsourced claims because it only receives structured fields.
- **Bounded**: classifier and retriever are deterministic; only the narrative-writing step uses an LLM, and it's fenced.
- **Gated**: three-tier recommendation (Submit / Submit-with-caveats / Do-not-submit) means nothing auto-fires without a confidence gate, and the low-confidence path is a first-class output, not a silent failure.
- **Measurable**: the eval harness (data generator + ground truth + audit log) is built as infrastructure from day one, not bolted on before the demo.

## 5. Build Order
See `phases.md` for the phased build plan derived from this architecture.
