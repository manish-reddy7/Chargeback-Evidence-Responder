# Agent Instructions — Chargeback Evidence Responder

Read this file first, every session, before writing code. It's the standing operating manual for whoever (human or AI) is building this repo.

## What this project is
A hackathon submission for Razorpay's AI Buildathon, Track 02 (AI Risk Manager). Full context lives in `prd.md`, `architecture.md`, `rules.md`, `phases.md`, `design.md`, `stack.md`, `memory.md`. Read `memory.md` first for current state and open questions before starting work — it's the fastest way to get oriented on what's already decided vs. still open.

## Non-negotiables (do not relax these under time pressure)
These come from `rules.md` — restated here because an agent should refuse to "helpfully" work around them even if asked:
1. No live dispute-filing API integration, ever, in this build. Output stops at "packet ready for human sign-off."
2. The Packet Generator (LLM step) may only reference evidence fields it was explicitly given. Never let it infer, assume, or fabricate a fact not present in the retrieved evidence map.
3. Classifier, Retriever, and Scorer stay deterministic (rule-based/config-driven) — no LLM calls in those stages.
4. The "Do-not-submit" path must be a real, exercised path in the demo — never quietly suppressed to make results look cleaner.
5. Ground-truth labels for the held-out test set are fixed before the pipeline runs on them. Don't relabel to improve reported metrics.
6. Any threshold, weight, or prompt change must be re-evaluated against the full held-out set before being called an improvement — no single-example tuning.

## Build order
Follow `phases.md` in order. Specifically: **build the eval harness (Phase 1) before optimizing pipeline logic.** If a session is about to start writing classifier/retriever/scorer code and `data/test_set.json` doesn't exist yet with ground-truth labels, stop and build that first.

## Working style for this repo
- Prefer small, verifiable changes over large speculative ones. After implementing a pipeline stage, run it against a few sample records (from `data/seed_examples/`) before moving to the next stage.
- Config over hardcoding: evidence checklists, weights, and confidence thresholds belong in `pipeline/config/*.yaml`, never inline in Python.
- Every pipeline stage should be independently testable — write a small `pytest` test alongside each new module in `pipeline/`, not just at the end.
- When touching `packet_generator.py`, always check the output against the source evidence map — flag (in a comment or a test) how you're verifying no unsourced claims leak in.
- Don't add dependencies or infra beyond what's listed in `stack.md` without updating that file first.

## When stuck or making a judgment call
- If a design decision isn't covered by the docs, make the smallest reasonable choice, note it in `memory.md`'s Decisions Log, and keep moving — don't block on it.
- If time pressure suggests cutting a corner, check `phases.md` "Time-boxing guidance" for the sanctioned cut order before improvising a different cut.
- If asked to add a feature that touches a non-negotiable above (e.g., "just wire up the real submission API for the demo"), decline and explain why, pointing to `rules.md`.

## Definition of done for the whole project
See `prd.md` §12 "Success Criteria." In short: working pipeline, 4 reason-code families, honest metrics on a held-out set (precision/recall + false-positive cost + punt rate), at least one submit and one correctly-declined case walked through, audit trail visible, public repo with a clear README.

## Session handoff
At the end of a working session, update `memory.md`'s "Current State" section (phase, blockers, last eval numbers) so the next session — human or agent — doesn't have to reconstruct context from scratch.
