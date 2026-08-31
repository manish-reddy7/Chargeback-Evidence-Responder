# Pitch video script — Chargeback Evidence Responder

**Track:** AI Risk Manager (Razorpay AI Buildathon)
**Target length:** 5:00. Timestamps are pacing targets, not hard cuts — practice once
and adjust.

Judging bar this script is written to hit: *"measured precision/recall metrics on
held-out test data, strictly defense-focused."* Every section either shows the number
or shows the guardrail that makes the number trustworthy.

---

## 0:00–0:30 — The problem (talk over a blank slide or your face cam)

> "When a customer disputes a Razorpay charge, the merchant gets a short window to
> submit evidence or lose the money automatically. The obvious build here is an LLM
> that writes a persuasive rebuttal. That's the wrong bar.
>
> Auto-fighting a *weak* dispute costs ops time, a representment fee, and — if you
> lose anyway — it inflates the merchant's dispute-response ratio, which card networks
> penalize. So the hard decision isn't 'write a good rebuttal.' It's: **is this dispute
> even worth fighting?**
>
> That triage decision is what this project treats as the product. The rebuttal text
> is a by-product."

## 0:30–1:15 — Architecture (screen: `architecture.md` diagram or README §3)

> "Five stages. Four are fully deterministic — only one is generative, and it's boxed
> in on every side.
>
> One: classify the reason code into one of four families — deterministic lookup,
> unknown codes get punted to a human, never force-fit.
> Two: retrieve the evidence fields for that family from the merchant's records —
> every value keeps the record key it came from.
> Three: score each field present, weak, or missing against a config-driven checklist
> — that produces a 0-to-100 confidence score.
> Four: draft the rebuttal. This is the one LLM call, and it only ever sees fields the
> scorer already marked present or weak. Missing fields are filtered out *before* the
> prompt is built — the model literally cannot reference evidence that isn't there.
> Five: recommend — submit, submit with caveats, or do not submit — off explicit,
> tunable thresholds.
>
> Every case writes one immutable entry to an append-only audit trail. And critically:
> the system never files a dispute. It stops at a packet ready for a human to sign off."

## 1:15–2:15 — Demo, case 1: a clean win (screen: dashboard, `DP-0041`)

> "Here's the dashboard on a real case. DP-0041, an unauthorized-transaction dispute
> for ₹2,450. 3-D Secure authenticated with liability shift, AVS full match, CVV
> match, device fingerprint matches three prior orders, fourteen prior undisputed
> orders on the account.
>
> Every authentication signal is present — confidence hits 100 — the system drafts a
> packet citing each signal by name, and recommends Submit. [click into the packet,
> point at one sentence, then point at the evidence field it traces back to] Every
> factual claim in this packet traces to a specific field in the merchant's records.
> Nothing here is generated from nothing."

## 2:15–3:30 — Demo, case 2: the honest decline (screen: dashboard, `DP-0069`)

> "Now the case that actually makes the point. DP-0069 — Not Received, ₹7,999. This
> order genuinely was delivered: there's a signature *and* a delivery photo on file.
> By most measures, this is winnable.
>
> But it shipped through a local courier with no carrier tracking number, and the
> checklist treats tracking as required for this family. So the system caps
> confidence at 30, drafts *no packet*, and tells the merchant exactly what's missing:
> a tracking number.
>
> This is a false negative, and we accept it on purpose. It costs ₹7,999 in forgone
> recovery. But the alternative — drafting a rebuttal that leans on 'it was delivered'
> without the evidence a card network actually wants — is the thing this system is
> built to refuse to do. It would rather decline a winnable case than fabricate its
> way into one. [optional: mention the threshold is one YAML line in
> `families.yaml` — a visible, tunable policy choice, not a hidden guess.]"

## 3:30–4:30 — The numbers (screen: `eval/metrics.py` output or dashboard summary)

> "This is scored against a frozen, hand-labeled, 80-case held-out set. Ground truth
> is assigned independently in the data generator — the pipeline never sees the
> labels; they're only re-joined at scoring time. So there's no leakage path.
>
> Precision 84.8%, recall 90.3%, F1 87.5%, on 60 binary-evaluable cases — 28 true
> positives, 5 false positives, 3 false negatives, 24 true negatives. False-positive
> cost: ₹7,000. False-negative cost: ₹8,997. Fifteen borderline cases — 100% of them
> get routed to caveats or human review, never a blind auto-submit. Coverage 93.8%,
> with the rest honestly punted to a human on unmapped reason codes.
>
> This isn't tuned toward 100%. The eval script itself prints a warning if precision
> comes back above 95% — because on real disputes, that number is a sign of a leaky
> test set, not a good model. The false positives and negatives here are the
> adversarial cases the generator deliberately includes: account takeovers where every
> auth signal passes because the fraudster had the real card, and genuinely delivered
> orders missing the one required field."

## 4:30–5:00 — Guardrails + close (screen: README §4 guardrail list or code)

> "Three things that make this defensible, not just plausible: it never auto-files —
> there's no filing API call anywhere in this repo. It never fabricates a missing
> field — that's structural, not a prompt instruction, since the model never receives
> fields the scorer marked missing. And every decision, every override, is logged to
> an append-only audit trail.
>
> The whole thing runs offline, one command, no API key required — reproducible with
> a deterministic fallback renderer, or with a real LLM backend when you want one.
>
> This is a triage system that knows when *not* to act. That's the product."

---

## Filming notes

- Screen-record the dashboard (`dashboard/index.html`) live — don't use static
  screenshots for the two case walkthroughs; judges want to see it's real software.
- Have `eval/metrics.py`'s printed report on screen (or the dashboard's summary
  panel) during 3:30–4:30 rather than reading numbers off a slide.
- If time is tight, cut from the back: the guardrails close (4:30–5:00) can compress
  to 15 seconds; the two-case demo (1:15–3:30) is the part that actually
  differentiates this from "LLM writes a rebuttal."
- Say the ₹ numbers out loud slowly once each — they're doing the work of proving
  this is a business decision, not just a classifier.
