# Phases — Chargeback Evidence Responder

Build order derived from `architecture.md`, constrained by `rules.md`. Eval infrastructure comes before pipeline polish — this is the single biggest lever on your final score.

## Phase 0 — Setup (few hours)
- Repo scaffold, README stub, pick stack (suggest: Python for pipeline/data gen, simple web frontend for dashboard).
- Define the 4 reason code families and their evidence checklists in a config file (this is the artifact R3 requires).
- Write out `prd.md`, `architecture.md`, `rules.md` into the repo (done).

**Exit criteria:** repo exists, config schema for evidence checklists is defined, team agrees on the 4 families.

## Phase 1 — Synthetic Data + Eval Harness (do this before any model logic)
- Build the synthetic data generator: transactions, orders, customer history, support tickets, dispute metadata.
- Generate 50–100 cases across the 4 families, deliberately including edge cases (missing tracking, ambiguous AVS, genuine duplicates, legit "not received").
- Hand-label ground truth (should-win / should-lose / borderline) independently, before any pipeline exists (R4).
- Define your metrics script: precision/recall, false-positive cost calculation, coverage/punt rate.

**Exit criteria:** you have a frozen held-out test set with ground truth labels and a metrics script that can score any pipeline output against it — even a dummy pipeline. This is your yardstick for every phase after this.

## Phase 2 — Deterministic Core (Classifier + Retriever + Scorer)
- Classifier: reason code → family mapping.
- Evidence Retriever: field lookups per family from the synthetic data store.
- Sufficiency Scorer: checklist + weights (config-driven, R3) → confidence score.
- Run this against the Phase 1 test set — you can already measure classification accuracy and see how confidence scores distribute, before any LLM is involved.

**Exit criteria:** deterministic pipeline runs end-to-end on all test cases and produces a confidence score per case. Sanity-check the score distribution against your ground truth labels.

## Phase 3 — Packet Generator (constrained LLM step)
- Build the prompt that takes only the retrieved evidence map (never missing fields) and generates the rebuttal narrative.
- Add the post-hoc check: every factual claim in the output maps to a passed-in field (R1, R2).
- Wire in the three-way recommendation output: Submit / Submit-with-caveats / Do-not-submit, using the confidence thresholds from Phase 2 (make thresholds a config value, R8).

**Exit criteria:** full pipeline produces a packet + recommendation + confidence for every test case, with the do-not-submit path actually firing on the cases designed to trigger it.

## Phase 4 — Audit Trail + Metrics Report
- Implement the audit log (append-only, R16).
- Run the full held-out set through the complete pipeline.
- Generate the metrics report: precision/recall, false-positive cost, punt rate (R9–R12). Sanity check anything that looks too good (R12).
- Pick your two demo cases: one clean win, one correct do-not-submit.

**Exit criteria:** you have real numbers you're prepared to defend, and two walked-through cases ready for the pitch.

## Phase 5 — Dashboard (only after Phase 4 numbers exist)
- Dispute queue view, case detail view (evidence checklist + packet + confidence), audit trail view.
- Follow `design.md` for visual direction.
- Keep this scoped — a clean, minimal UI beats an elaborate one you didn't have time to polish. The eval harness is what wins, not the UI.

**Exit criteria:** a demoable UI that can walk through the queue → a case → its packet → its audit trail live.

## Phase 6 — Pitch Prep
- 5-minute video following the demo script in `prd.md` section 10.
- Architecture diagram (reuse `architecture.md` diagram, simplify for slides).
- README covering: problem, approach, guardrails (R5–R8 explicitly called out), eval results, how to run.
- Public repo cleanup — remove dead code, make sure the eval script is runnable by a judge.

**Exit criteria:** submission-ready repo + video + one-pager.

## Time-boxing guidance
If you're running short on time, cut in this order: Phase 5 (dashboard) polish first, then reduce reason code family count from 4 to 3 (never below 3), then reduce test set size (never below ~30 cases — you need enough for the precision/recall numbers to mean something). **Never cut Phase 1 (eval harness) or Phase 4 (honest metrics reporting)** — those are what the judges are explicitly scoring on.
