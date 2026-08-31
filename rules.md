# Rules — Chargeback Evidence Responder

These are the hard constraints for the build. Anything that violates one of these should be treated as a blocker, not a trade-off to revisit later.

## 1. Data & Evidence Integrity
- **R1.** The Packet Generator may only reference evidence fields that were explicitly retrieved and marked present/weak by the Evidence Retriever. It must never introduce a claim not backed by an input field.
- **R2.** Every sentence in a generated evidence packet must be traceable to a specific source field. If you can't point to the field, cut the sentence.
- **R3.** The Sufficiency Scorer's checklist and weights live in a config file, not inline code — they must be visibly inspectable and tunable for the demo.
- **R4.** Ground-truth labels for the held-out test set must be decided **before** running the pipeline on them, by a human, independent of any model output. No retroactive labeling to make numbers look better.

## 2. Defense-Only / Safety Boundary
- **R5.** This system never calls a live dispute-filing API. Output terminates at "packet ready for human sign-off." This is a hard line, not a v2 feature to relax.
- **R6.** Nothing in this system may be used to fabricate, alter, or misrepresent evidence. If a field is missing, the correct output is "missing," never a plausible-sounding substitute.
- **R7.** The system must be able to recommend **Do-not-submit**, and this path must be exercised and shown in the demo — not hidden or minimized because it's a less flashy result.
- **R8.** Confidence thresholds that gate Submit vs. Submit-with-caveats vs. Do-not-submit must be explicit, documented, and shown in the pitch — this is the "bounded and gated" story for judges.

## 3. Evaluation Honesty
- **R9.** Report precision/recall on the full held-out set, not a cherry-picked subset.
- **R10.** Report the punt rate (% of disputes the system couldn't confidently classify or score) honestly, even if it's higher than you'd like.
- **R11.** False-positive cost must be expressed in a concrete unit (₹, hours of ops time, or a defined penalty-risk score) — not just accuracy percentages.
- **R12.** If a metric looks too good (e.g., >95% precision on a synthetic set), treat that as a signal to check for data leakage or an unrealistically easy test set before reporting it.

## 4. Scope Discipline
- **R13.** Stick to the 4 reason code families defined in the PRD. Do not expand scope mid-build — depth over breadth is the explicit judging criterion.
- **R14.** No live payment gateway integration. Razorpay test-mode / synthetic data only.
- **R15.** No fraud-detection-upstream features (that's a different track/problem) — this system responds to disputes that already exist, it doesn't try to prevent them.

## 5. Audit Trail
- **R16.** Every processed dispute produces exactly one immutable audit entry. Entries are appended, never edited or deleted.
- **R17.** If a human overrides the system's recommendation, the override and its stated reason must be captured in the audit trail.

## 6. Team Working Rules
- **R18.** The eval harness (synthetic data + ground truth + metrics) is built in Phase 1, before pipeline logic is optimized. See `phases.md`.
- **R19.** Any change to scoring weights, thresholds, or prompts must be re-run against the full held-out set before being called "an improvement" — no single-case anecdotal tuning.
- **R20.** Keep the classifier and retriever deterministic (no LLM) — the only LLM call in the pipeline is the constrained narrative generation step in R1/R2.
