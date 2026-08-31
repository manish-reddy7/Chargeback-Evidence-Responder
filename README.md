# Chargeback Evidence Responder

**Razorpay AI Buildathon — Track 02: AI Risk Manager**

> Given a disputed transaction and the merchant's data, this agent decides whether
> the dispute can be *defensibly fought* — and drafts the rebuttal packet only when
> the evidence is actually there. Its most important skill is knowing when **not** to
> fight, and it will decline a winnable-looking case rather than lean on evidence it
> doesn't have.

The whole thing runs offline with one command (`./run_eval.sh`) and reports precision,
recall, and false-positive cost **in rupees** against a frozen, hand-labeled test set.

---

## 1. The idea in one paragraph

When a customer disputes a charge, the merchant has a short window to submit evidence
or lose automatically. The tempting build is "LLM writes a persuasive rebuttal." That's
the wrong bar. Auto-fighting a weak dispute burns ops hours, pays a representment fee,
risks losing anyway, and — worst of all — inflates the merchant's dispute-response
ratio, which card networks penalize. **So the hard, valuable decision is triage: is
this dispute worth fighting at all?** This project treats *evidence-sufficiency
assessment* as the first-class feature and the rebuttal text as a downstream
by-product. It never fabricates evidence, and it never files anything — it stops at
"packet ready for a human to sign off."

## 2. What it does (the pipeline)

Five stages. Four are fully deterministic; exactly one is generative, and that one is
boxed in on all sides.

1. **Classify** — map the dispute's reason code to one of four families (a plain,
   auditable lookup; unknown codes are *punted* to a human, never force-fit).
2. **Retrieve** — pull the family's evidence fields from the case's records. Every
   value carries the `record.key` it came from (the evidentiary chain).
3. **Score sufficiency** — grade each field present / weak / missing against a
   config-driven checklist and weights, producing a 0–100 confidence, with gates for
   missing *required* evidence.
4. **Draft the packet** — one constrained LLM call writes the rebuttal narrative
   **from the retrieved fields only**. Missing fields are filtered out before the model
   sees anything, so it cannot fill a gap. A post-hoc validator flags any number, date,
   or ID in the draft that doesn't trace to a provided value.
5. **Recommend** — `Submit` / `Submit with caveats` / `Do not submit`, using explicit,
   tunable confidence thresholds. Do-not-submit drafts *no* packet and instead explains
   what evidence would change the call.

Every case produces one immutable audit-trail entry.

### Reason-code families

| Family | Dispute | Key evidence (required in **bold**) |
|---|---|---|
| Goods/Service Not Received | "It never arrived" | **tracking number**, **delivery confirmation**, carrier, ship/deliver dates, photo |
| Not As Described / Defective | "Wrong/damaged item" | **product listing snapshot**, return policy, support resolution, condition proof |
| Unauthorized Transaction | "I didn't buy this" | 3DS status, AVS, CVV, device match, IP match, prior history *(at least one auth signal required)* |
| Duplicate / Processing Error | "Charged twice" | **distinct order IDs**, distinct timestamps, idempotency-key trace, itemization |

28 raw reason codes across the four families are mapped in `pipeline/config/families.yaml`.

## 3. Architecture

```
  dispute + merchant records
            │
            ▼
   ┌──────────────────┐
   │  1. Classifier   │  reason_code ──► family   (deterministic; unknown ⇒ PUNT)
   └────────┬─────────┘
            ▼
   ┌──────────────────┐
   │  2. Retriever    │  family ──► {field: value, weak?, source}   (deterministic)
   └────────┬─────────┘
            ▼
   ┌──────────────────┐
   │  3. Scorer       │  checklist × weights ──► confidence + gates  (deterministic)
   └────────┬─────────┘
            ▼
   ┌──────────────────┐        present/weak fields ONLY
   │  4. Packet gen   │ ─────► ┌───────────────────────────┐
   │  (the ONE LLM    │        │ constrained draft + post-  │
   │   call)          │ ◄───── │ hoc validator (R1/R2/R6)   │
   └────────┬─────────┘        └───────────────────────────┘
            ▼
   ┌──────────────────┐
   │  5. Recommend    │  Submit / Caveats / Do-not-submit   (thresholds = config)
   └────────┬─────────┘
            ▼
   append-only audit trail   ──►   STOP. (never files a dispute — R5)
```

The design choice that matters: **the deterministic core is the source of truth.**
The LLM only turns already-verified fields into prose. It has no authority over the
decision and no access to anything the retriever didn't hand it.

## 4. Guardrails (and where they live in the code)

These are hard constraints, not aspirations. The ones the buildathon bar calls out:

- **R5 — never auto-files a dispute.** The pipeline terminates at a packet ready for
  human sign-off. There is no dispute-filing API call anywhere in the repo. *(see the
  end of `run_pipeline.py`; the packet footer states this boundary explicitly.)*
- **R6 — never fabricates a missing field.** Missing evidence is filtered out in
  `packet_generator._present_and_weak()` before the prompt is built, so the model
  literally cannot reference it. *(structural, not just a prompt instruction.)*
- **R7 — do-not-submit is a real, demoed path.** 27 of 80 cases resolve to
  do-not-submit; they draft no packet and explain what's missing.
- **R8 — thresholds are explicit and tunable.** `submit_min` / `caveats_min` and the
  full cost model live in `pipeline/config/thresholds.yaml`, surfaced in the dashboard.

Also enforced: **R1/R2** every factual sentence traces to a source field (deterministic
renderer uses per-field templates; the validator catches stray tokens); **R16** the
audit trail is append-only JSONL, one entry per case; **R17** human overrides are
captured as their own entries and never mutate the original decision; **R20** classifier,
retriever, and scorer are deterministic — the LLM is confined to stage 4.

## 5. Evaluation — the part that matters

The yardstick was built before the pipeline. `data/test_set.json` is a **frozen,
hand-labeled** set of 80 synthetic disputes; ground-truth `should_win` / `should_lose`
/ `borderline` labels are assigned *by construction* in the data generator, independent
of the scorer. The pipeline never sees a label — `data/pipeline_output.json` contains
zero ground-truth, and `eval/metrics.py` re-joins the labels only to score. So there is
no leakage path.

Results on the full held-out set (deterministic backend):

| Metric | Value |
|---|---|
| Precision (recommend-to-fight) | **84.8%** |
| Recall | **90.3%** |
| F1 | 87.5% |
| Accuracy | 86.7% |
| Confusion | TP 28 · FP 5 · FN 3 · TN 24 |
| **False-positive cost** | **₹7,000** (5 × ₹1,400: ops time + representment fee + penalty) |
| **False-negative cost** | **₹8,997** (forgone recoverable revenue) |
| Punt rate | 6.2% (5 unknown reason codes, reported honestly) |
| Coverage | 93.8% |
| Borderline (15 cases) | 100% routed to *caveats / human review* |

**Why it isn't ~100%, and why that's the point.** The test set deliberately includes
adversarial cases: account-takeover disputes that *look* authorized (AVS/CVV/3DS all
pass because the fraudster had the card), wrong-address deliveries, and genuinely
delivered orders shipped by a local courier with no tracking number. These produce real
false positives and false negatives. A model reporting 100% precision here would be a
sign of leakage or an easy test set — `eval/metrics.py` prints an explicit warning if
precision exceeds 95% (rules.md R12).

## 6. Two walked-through cases

**A clean win — `DP-0041` (Unauthorized, ₹2,450) → Submit, confidence 100.**
3-D Secure authenticated with liability shift, AVS full match, CVV2 match, device
fingerprint matches three prior orders, and 14 prior undisputed orders on the account.
Every authentication signal is present, so the system drafts a packet citing each one
and recommends submitting.

**A correct decline — `DP-0069` (Not Received, ₹7,999) → Do not submit, confidence 30.**
This one is *genuinely winnable*: the order was delivered, with a signature **and** a
delivery photo on file. But it shipped via a local courier with **no carrier tracking
number**, and the checklist treats tracking as required. The system caps confidence,
drafts **no packet**, and explains that a tracking number is missing. This is a false
negative we *accept on purpose*: it costs ₹7,999 in forgone recovery, but the honest
behavior is to flag the gap rather than draft a rebuttal that overstates the evidence.
It's the clearest illustration of the product's thesis — **it would rather decline a
winnable case than fabricate its way into one.** (Tune `tracking_number.required` in
`families.yaml` and this case flips — the threshold is a visible, defensible choice.)

## 7. How to run

```bash
# one dependency (PyYAML). The 'anthropic' SDK is optional.
pip install -r requirements.txt

# run everything: unit tests → full pipeline → metrics report → dashboard data
./run_eval.sh

# or step by step:
python3 run_pipeline.py --demo-override   # writes pipeline_output.json + audit trail
python3 eval/metrics.py                    # prints the evaluation report
python3 dashboard/build_dashboard_data.py  # bakes dashboard/data.js

# open the dashboard (no server needed — it's a local file)
open dashboard/index.html
```

**LLM backend.** The generative step is provider-agnostic. If `ANTHROPIC_API_KEY` is
set and the `anthropic` SDK is installed, packet drafting calls Claude
(`ANTHROPIC_MODEL`, default `claude-3-5-sonnet-latest`). Otherwise it falls back to a
deterministic template renderer that obeys the exact same constraints — so the pipeline
and all metrics reproduce with **no key, no network, no SDK**. The decision logic and
the numbers are identical either way; only the prose wording differs.

**Tests.** 23 unit tests cover the classifier, retriever, scorer, and the packet
generator's guardrails (no fabrication, weak-evidence marking, validator catches
hallucinated tokens, do-not-submit drafts nothing). They run under `pytest` *or* as
plain scripts: `for t in tests/test_*.py; do python3 "$t"; done`.

## 8. Repository layout

```
pipeline/
  classifier.py         reason code → family (deterministic)
  retriever.py          field lookup with provenance (deterministic)
  scorer.py             sufficiency scoring + 3-way recommendation (deterministic)
  packet_generator.py   the one constrained LLM call + fallback + validator
  common.py             config loading + the shared field→source schema
  config/
    families.yaml       evidence checklists + weights  (R3: config, not code)
    thresholds.yaml     submit/caveats thresholds + ₹ cost model  (R8)
  prompts/
    system.txt, user_template.txt, family_structures.yaml
data/
  generator.py          synthetic case generator (seeded, reproducible)
  test_set.json         FROZEN hand-labeled held-out set (80 cases)
  pipeline_output.json  per-case decisions (NO ground-truth labels)
eval/
  metrics.py            precision/recall, ₹ FP/FN cost, punt rate, confusion
audit/
  logger.py             append-only decision + override log (R16/R17)
  trail.jsonl           the immutable trail
dashboard/
  index.html            single-file "case file" dashboard
  build_dashboard_data.py
tests/                  23 unit tests (pytest or plain python3)
run_pipeline.py         orchestrates the full pipeline over the test set
run_eval.sh             one-command reproduction
```

## 9. Success criteria (PRD §9)

- [x] Working pipeline on synthetic Razorpay-test-mode-style data
- [x] 4 reason-code families supported (28 codes mapped)
- [x] Held-out test set with published precision/recall + false-positive cost framing
- [x] Two walked-through cases: one win (`DP-0041`), one correct decline (`DP-0069`)
- [x] Public repo with README explaining architecture and guardrails
- [x] Audit trail visible for every processed dispute (80 decision entries + overrides)

## 10. Honest limitations

The data is synthetic (no real cardholder data), so absolute numbers reflect the
generator's assumptions, not production traffic — the *methodology* is the deliverable,
not the specific percentages. The four families cover common disputes but not every
card-network reason code (unknowns are punted, which is why punt rate is a reported
metric). The deterministic fallback renderer writes correct, traceable, but plain prose;
a live model produces more fluent narratives without changing the decision. The
post-hoc validator is a backstop scoped to *digit-bearing* tokens (amounts, dates,
tracking/order IDs — the fabrication vectors that matter for chargeback evidence); the
*primary* anti-fabrication guarantee is structural — missing fields are filtered out
before generation, so neither backend can reference them — with human sign-off as the
final line. And the "required tracking number" rule that declines `DP-0069` is a
deliberate, tunable policy choice — the system's job is to make such choices explicit
and measurable, not to hide them.

---

*Built for the Razorpay AI Buildathon. No dispute is ever auto-filed; every packet
stops at human sign-off.*
