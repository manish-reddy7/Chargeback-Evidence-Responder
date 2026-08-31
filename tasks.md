# Tasks — Chargeback Evidence Responder

Phases from `phases.md` broken into small, one-prompt-sized tasks. Check items off as you go — a coding agent should be able to pick up at the first unchecked box and know exactly what to do next.

## Phase 0 — Setup
- [ ] Init repo, create folder structure per `stack.md`
- [ ] Add `README.md` stub (fill in properly in Phase 6)
- [ ] Create `pipeline/config/families.yaml` with the 4 reason-code families and their evidence checklists (from `prd.md` §4)
- [ ] Create `pipeline/config/thresholds.yaml` with placeholder confidence thresholds (to be tuned in Phase 2)
- [ ] Confirm `agent.md`, `stack.md`, `rules.md` are all in repo root and read

## Phase 1 — Synthetic Data + Eval Harness
- [ ] Write `data/seed_examples/` — 1-2 hand-written example records per family (transaction, order, customer history, dispute metadata) to pin down data shapes
- [ ] Write `data/generator.py` to produce dispute cases programmatically from the seed shapes
- [ ] Generate 50-100 cases across the 4 families, including deliberate edge cases:
  - [ ] Missing tracking data (Not Received family)
  - [ ] Ambiguous AVS/CVV mismatch (Unauthorized family)
  - [ ] Genuine duplicate charge (Duplicate family)
  - [ ] Legitimate "not received" claim with full evidence present (should-win case)
  - [ ] Weak/fabricated-sounding "not received" claim with no tracking (should-lose case)
- [ ] Hand-label ground truth (should-win / should-lose / borderline) for every case, independently — write to `data/test_set.json`
- [ ] Freeze `data/test_set.json` — treat as read-only from this point forward
- [ ] Write `eval/metrics.py`: precision/recall calculation, false-positive cost calculation, punt rate calculation
- [ ] Run `eval/metrics.py` against a dummy/random pipeline output to confirm the scoring script itself works before any real pipeline exists

**Phase 1 exit check:** can you run `eval/metrics.py` against `data/test_set.json` and get a metrics report, even with fake inputs? If not, don't move to Phase 2.

## Phase 2 — Deterministic Core
- [ ] Write `pipeline/classifier.py`: reason code string → family (lookup table)
- [ ] Unit test classifier against all reason codes present in `data/test_set.json`
- [ ] Write `pipeline/retriever.py`: given a case ID + family, return the structured evidence map
- [ ] Unit test retriever against a few seed examples, confirm correct fields are pulled per family
- [ ] Write `pipeline/scorer.py`: evidence map → per-field present/missing/weak + overall confidence score, using `pipeline/config/families.yaml` and `thresholds.yaml`
- [ ] Unit test scorer against seed examples with known expected confidence bands
- [ ] Run classifier → retriever → scorer end-to-end against all of `data/test_set.json`
- [ ] Eyeball the confidence score distribution against your ground truth labels — do high-confidence cases roughly line up with should-win labels? If not, revisit checklist weights before moving on

**Phase 2 exit check:** deterministic pipeline runs on all test cases, confidence scores look directionally sane against ground truth.

## Phase 3 — Packet Generator
- [ ] Create `pipeline/prompts/` folder, write the packet-generation prompt template (system + user prompt) — pass only the retrieved evidence map, explicitly instruct no claims beyond given fields
- [ ] Write `pipeline/packet_generator.py`: calls Claude with the constrained prompt, returns narrative text
- [ ] Write a post-hoc validator: check that key factual claims in the generated packet map to fields actually present in the evidence map (simple keyword/field presence check is fine for hackathon scope)
- [ ] Wire in the three-way recommendation logic (Submit / Submit-with-caveats / Do-not-submit) using thresholds from `pipeline/config/thresholds.yaml`
- [ ] Run full pipeline (classifier → retriever → scorer → packet generator → recommendation) on 5-10 sample cases, manually review packet quality and recommendation sanity
- [ ] Confirm the Do-not-submit path actually fires on the cases designed to trigger it (from Phase 1 edge cases)

**Phase 3 exit check:** full pipeline produces a packet + recommendation + confidence for a sample of cases, all three recommendation types have been observed at least once.

## Phase 4 — Audit Trail + Metrics Report
- [ ] Write `audit/logger.py`: append-only JSONL writer, one entry per processed case
- [ ] Wire audit logging into the full pipeline run
- [ ] Run the complete pipeline against all of `data/test_set.json`
- [ ] Run `eval/metrics.py` against the real pipeline output — get real precision/recall, false-positive cost, punt rate numbers
- [ ] Sanity-check any suspiciously high metric (>95% precision) — investigate for data leakage or an unrealistically easy test set before trusting it
- [ ] Pick and write up 2 demo cases: one clean Submit win, one correct Do-not-submit, with reasoning
- [ ] Write `run_eval.sh` — single command to reproduce the full metrics report from a clean checkout

**Phase 4 exit check:** you have real, sanity-checked numbers you're prepared to defend live, and `run_eval.sh` works from a fresh clone.

## Phase 5 — Dashboard
- [ ] Scaffold minimal frontend (per `stack.md`) with two views: queue, case detail
- [ ] Build queue view per `design.md` §1 layout (case ID, reason family, amount, confidence dot + label, date)
- [ ] Build case detail view: evidence checklist, confidence bar, the stamp element, packet viewer, audit trail viewer
- [ ] Implement the stamp signature element (SUBMIT / CAVEATS / DO NOT SUBMIT, colored, textured) per `design.md` §1
- [ ] Wire dashboard to real pipeline output (via a minimal API layer or static JSON export from Phase 4's run)
- [ ] Check responsive behavior at a narrow viewport
- [ ] Check `prefers-reduced-motion` is respected for the stamp animation

**Phase 5 exit check:** you can click through the queue → a case → its packet → its audit trail live, for both a Submit and a Do-not-submit case.

## Phase 6 — Pitch Prep
- [ ] Write the real `README.md`: problem, approach, guardrails (explicitly call out R5-R8 from `rules.md`), eval results, how to run `run_eval.sh`
- [ ] Simplify `architecture.md`'s diagram into a slide-ready version
- [ ] Record 5-minute pitch video following `prd.md` §10 demo script
- [ ] Clean repo: remove dead code, confirm a judge can clone + run `run_eval.sh` with no manual setup beyond documented steps
- [ ] Final check against `prd.md` §12 Success Criteria checklist before submitting

**Phase 6 exit check:** submission-ready repo + video + README, `run_eval.sh` verified to work from a completely clean clone.
