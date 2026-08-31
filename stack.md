# Stack — Chargeback Evidence Responder

Explicit, opinionated choices so a coding agent doesn't re-decide this every session. If you need to deviate, update this file first, then build — don't let the stack drift silently across sessions.

## Language & Runtime
- **Python 3.11+** for everything backend: synthetic data generator, classifier, retriever, sufficiency scorer, packet generator, metrics/eval script.
- Reason: the eval harness is the highest-value part of this project (per `phases.md`), and Python is fastest to iterate on for data generation, scoring logic, and metrics — don't introduce a second backend language for a hackathon timeline.

## Project Structure
```
/chargeback-evidence-responder
├── agent.md              # this project's standing agent instructions
├── prd.md / architecture.md / rules.md / phases.md / design.md / memory.md
├── stack.md               # this file
├── tasks.md               # phase-broken-into-tasks checklist
├── data/
│   ├── generator.py        # synthetic data generator (Phase 1)
│   ├── seed_examples/      # a few hand-written example records per family
│   └── test_set.json       # frozen held-out set + ground truth labels (once generated)
├── pipeline/
│   ├── classifier.py        # reason code -> family (Phase 2)
│   ├── retriever.py          # evidence field lookups (Phase 2)
│   ├── scorer.py              # sufficiency scoring + confidence (Phase 2)
│   ├── packet_generator.py    # constrained LLM narrative step (Phase 3)
│   └── config/
│       ├── families.yaml        # evidence checklist per reason-code family
│       └── thresholds.yaml      # confidence thresholds, tunable
├── audit/
│   └── logger.py            # append-only audit trail (Phase 4)
├── eval/
│   └── metrics.py            # precision/recall, false-positive cost, punt rate (Phase 1 + 4)
├── dashboard/                # frontend (Phase 5) — see design.md
│   └── ...
├── tests/
│   └── ...                   # unit tests for pipeline stages
├── README.md                 # submission-facing writeup (Phase 6)
└── run_eval.sh                # single command a judge can run to reproduce metrics
```

## Data Storage
- **Synthetic data + test set:** flat JSON files (`data/test_set.json`) — no database needed at hackathon scale (50–100 cases). Keeps everything diffable and inspectable in a PR.
- **Audit trail:** append-only JSONL file (`audit/trail.jsonl`) for the hackathon build — one line per entry, never rewritten. (Swap for a real DB only if there's time left after Phase 4 — don't do it earlier.)
- **Config (checklists, weights, thresholds):** YAML files under `pipeline/config/` — human-readable, easy to show judges as evidence of R3/R8 (tunable, visible thresholds).

## LLM Access
- **Claude via the Anthropic API** for the single constrained call in `packet_generator.py` (Phase 3). This is the *only* pipeline stage that calls an LLM — classifier, retriever, and scorer stay deterministic per `rules.md` R20.
- Prompt templates live in `pipeline/prompts/` (create when you reach Phase 3) — keep them as versioned files, not inline strings buried in code, so they're easy to iterate on and show in the repo.

## Frontend (Dashboard, Phase 5)
- **Plain React (or a single HTML/JS file if time is tight)** — no heavy framework needed for two views (queue, case detail). Follow `design.md` for visual direction (tokens, layout, the stamp signature element).
- Charting/confidence bar: plain CSS/SVG, no charting library needed for a simple horizontal bar.
- No backend framework decision needed yet beyond a minimal API layer (e.g., FastAPI) to serve the pipeline outputs to the dashboard — add this only when you reach Phase 5.

## Testing
- Lightweight unit tests (`pytest`) for classifier, retriever, and scorer — these are deterministic, so they're cheap to test and a good signal of engineering rigor for judges.
- The eval script (`eval/metrics.py` + `run_eval.sh`) IS your integration test — running it against `data/test_set.json` should be a judge's one-command way to reproduce your reported numbers.

## What NOT to add
- No database server (Postgres/Mongo/etc.) — flat files are sufficient at this scale and reduce setup friction for judges cloning the repo.
- No auth/user system — single-analyst demo, not a multi-tenant product.
- No live payment gateway / dispute API integration — explicitly out of scope (`rules.md` R5, R14).
- No microservices — this is one small pipeline + one small dashboard, keep it a monolith.
