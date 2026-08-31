#!/usr/bin/env bash
# run_eval.sh — reproduce the full evaluation end to end.
#
#   1. run every unit test
#   2. run the pipeline over the frozen test set (writes data/pipeline_output.json
#      + audit/trail.jsonl, and one demo human override)
#   3. score the output against the held-out labels and print the report
#
# No API key or network needed: the pipeline auto-falls back to the deterministic
# packet backend. Set ANTHROPIC_API_KEY (and `pip install anthropic`) to draft
# packets with a live model instead — metrics are unaffected either way.

set -euo pipefail
cd "$(dirname "$0")"

echo "### [1/3] unit tests"
for t in tests/test_*.py; do
  echo "--- $t"
  python3 "$t"
done

echo
echo "### [2/3] pipeline run over the frozen test set"
python3 run_pipeline.py --demo-override

echo
echo "### [3/3] evaluation report (pipeline output vs. held-out labels)"
python3 eval/metrics.py

echo
echo "### refreshing dashboard data"
python3 dashboard/build_dashboard_data.py

echo
echo "Done. Artifacts:"
echo "  data/pipeline_output.json   (per-case decisions, no ground-truth labels)"
echo "  audit/trail.jsonl           (immutable decision + override log)"
echo "  dashboard/index.html        (open in a browser to walk the queue)"
