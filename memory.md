# Memory — Chargeback Evidence Responder

Living project context. Update this as decisions get made or revised — this file is what a teammate (or an AI assistant picking the project back up) should read first to get oriented, without re-reading every doc.

## Project Identity
- **Name:** Chargeback Evidence Responder
- **Track:** Razorpay AI Buildathon — 02: AI Risk Manager
- **One-line pitch:** An agent that assembles chargeback rebuttal evidence and, critically, knows when the evidence isn't strong enough to fight — with measured precision/recall and false-positive cost on a held-out synthetic test set.
- **Related docs:** `prd.md` (what/why), `architecture.md` (how), `rules.md` (hard constraints), `phases.md` (build order), `design.md` (UI direction).

## Key Decisions Log
| Date | Decision | Why |
|---|---|---|
| — | Scope to 4 reason code families: Not Received, Not As Described/Defective, Unauthorized, Duplicate | Depth over breadth; each needs structurally different evidence, enough to show range without diluting eval quality |
| — | Classifier + Retriever are deterministic, not LLM | Keeps the auditable chain intact — only the narrative generation step uses an LLM, and it's fenced to retrieved fields only |
| — | No live dispute-filing API integration | Explicit safety boundary for the judging bar (defense-only, bounded); output stops at "packet ready for human sign-off" |
| — | Eval harness (synthetic data + ground truth + metrics) built in Phase 1, before pipeline logic | This is what the judging criteria actually reward — build the yardstick before optimizing against it |
| — | UI styled as a "case file" with a stamp motif as the signature design element | Grounded in the evidence/dispute domain rather than a generic dashboard template; see `design.md` |

## Current State
*(update this section as the build progresses — snapshot only, not a full log)*
- Phase: [update — e.g., "Phase 1: building synthetic data generator"]
- Blockers: [none yet / list here]
- Last eval run numbers: [not yet run]

## Open Questions (unresolved as of last update)
- How much unstructured data (support tickets) to simulate vs. keep everything structured — leaning toward structured-only for v1 to protect time for the eval harness.
- Whether the dashboard needs both queue + case detail views for the demo, or whether a single well-designed case-detail view (with a mocked queue list) is enough given time constraints.
- Exact confidence thresholds for Submit / Caveats / Do-not-submit — to be tuned empirically once Phase 2 (deterministic core) produces a score distribution on the held-out set, not decided a priori.

## Glossary / Shared Vocabulary
- **Family:** one of the 4 reason-code groupings (Not Received, Defective, Unauthorized, Duplicate) — each has its own evidence checklist.
- **Evidence map:** the structured set of retrieved fields for a given case, passed to the Sufficiency Scorer and (filtered) to the Packet Generator.
- **Punt rate:** % of held-out cases the pipeline couldn't confidently classify/score — must be reported honestly, not hidden.
- **False-positive cost:** the quantified cost (₹ or ops-hours) of recommending Submit on a case that shouldn't have been submitted — the core "honest metrics" requirement from the judging bar.
- **The stamp:** the UI's signature visual element — a rendered rubber-stamp graphic showing the case's recommendation, in the state color (see `design.md`).

## Reminders for Future Sessions
- Don't relax R5 (no live API calls) or R7 (Do-not-submit must be a real, demoed path) under time pressure — these are what make the submission defensible against the judging bar, not just a demo that looks good.
- If cutting scope, follow the priority order in `phases.md` "Time-boxing guidance" — dashboard polish is the first thing to cut, the eval harness is the last.
- Any threshold/weight/prompt change must be re-run against the full held-out set before being called an improvement (rule R19) — don't tune on anecdotes.
