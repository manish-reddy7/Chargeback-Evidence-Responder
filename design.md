# Design — Chargeback Evidence Responder Dashboard

## 0. Brief, pinned down
**Subject:** a risk-ops tool for reviewing chargeback disputes and their evidence.
**Audience:** a merchant risk/ops analyst working a dispute queue under deadline pressure, deciding whether to submit, caveat, or decline a rebuttal.
**Page's single job:** let the analyst see, in one glance, whether a case has enough evidence to fight — and why.

The domain itself has strong material to draw from: case files, evidence checklists, stamps of approval/rejection, ledgers, chain-of-custody. That's the world this design should live in — not a generic SaaS dashboard template.

## 1. Design Plan (pass 1 — brainstorm)

### Color — "Evidence Locker" palette
A working, slightly institutional palette — think case-file folders and status stamps, not a marketing site.
- `--paper: #EDEAE2` — warm off-white, like case-file stock (not cream-#F4F1EA-flat; slightly greyer/cooler)
- `--ink: #22241F` — near-black warm charcoal for body text
- `--ledger-green: #2F4B3C` — deep forest green, used for "sufficient evidence / submit" states and primary structure (this is the anchor color, not an accent)
- `--stamp-red: #8C3A2B` — brick/rust red (deliberately duller than terracotta #D97757 — a stamp-ink red, not a warm decorative accent), used only for "insufficient / do-not-submit" states
- `--caution-ochre: #B4863C` — mustard/ochre for "submit-with-caveats" / medium confidence
- `--line: #C7C0AF` — hairline rule color for dividers and table borders

### Type — case-file typography
- Display/headers: a condensed slab serif or typewriter-adjacent face (e.g., **Roboto Slab** or **Courier Prime** for real typewriter character) — evokes stamped case numbers and official documents.
- Body: a plain, highly legible sans (e.g., **IBM Plex Sans**) for scanability during real work.
- Data/mono: **IBM Plex Mono** for transaction IDs, amounts, timestamps, confidence scores — anything that needs to look like a precise, verifiable value.

### Layout concept
Not a dashboard-with-cards template. Instead, structure the page like a **case file**: a queue is a stack of folders (list), and opening a case shows a "file" with a checklist stapled to it and a stamp in the corner showing the recommendation.

```
┌─────────────────────────────────────────────────────────┐
│  DISPUTE QUEUE                     [filter: confidence▾] │
├─────────────────────────────────────────────────────────┤
│  #DP-0142   Not Received      ₹4,200   ⬤ high   Sep 12  │
│  #DP-0143   Unauthorized      ₹1,050   ⬤ low    Sep 12  │
│  #DP-0144   Defective         ₹890     ⬤ medium Sep 13  │
└─────────────────────────────────────────────────────────┘

  (click a row → case detail, styled as an open file)

┌─────────────────────────────────────────────────────────┐
│  CASE #DP-0142                          [STAMP: SUBMIT]  │
│  ─────────────────────────────────────────────────────  │
│  Reason: Goods Not Received        Amount: ₹4,200        │
│                                                            │
│  EVIDENCE CHECKLIST                                       │
│  ✓ Tracking number ............... present   (strong)    │
│  ✓ Delivery confirmation ......... present   (strong)    │
│  ✗ Delivery photo ................ missing   (n/a)       │
│  Confidence: 87%  ████████████████░░░                     │
│                                                            │
│  GENERATED PACKET                    [view / export]      │
│  AUDIT TRAIL                         [view log]           │
└─────────────────────────────────────────────────────────┘
```

### Signature element
**The stamp.** Every case gets a rendered "stamp" in the header — like a rubber ink stamp — reading SUBMIT / CAVEATS / DO NOT SUBMIT, rotated a few degrees, in the state color (ledger-green / caution-ochre / stamp-red), with a slightly rough/textured edge (SVG filter or a stamp-texture PNG mask). This is the one place the design allows itself a physical, tactile flourish — everywhere else stays quiet and functional. It also does real work: it's the fastest way for an analyst to triage a queue at a glance, and it visually embodies the product's core promise (a defensible, explainable verdict) rather than being decoration.

## 2. Self-critique (pass 2)

- Checked against generic defaults: no cream-#F4F1EA + terracotta (rejected — too close to the AI-generated default and to Anthropic's own accent), no near-black + neon accent, no broadsheet hairline-grid look. The evidence-locker palette and stamp motif are specific to this domain, not portable to any other dashboard brief.
- Numbered markers: not used for the reason-code families or steps — reason codes aren't sequential, so no 01/02/03 treatment. The only place a genuine sequence exists (evidence checklist items being gathered in pipeline order) could use a subtle order indicator, but it's optional and shouldn't be a numbered-marker set piece.
- Restraint check: the stamp is the one bold, textured, "designed" element. The queue list, tables, and checklist stay in plain hairline-rule, monospace-data, no-shadow, no-gradient territory — quiet enough that the stamp actually reads as a moment rather than getting lost among other flourishes.
- Accessibility floor: ledger-green, stamp-red, and caution-ochre all need to be checked for contrast against `--paper` and should not be the *only* signal for status — pair each with the text label (SUBMIT/CAVEATS/DO NOT SUBMIT) and a distinct icon/shape, not color alone, for colorblind users.

## 3. Component Notes

- **Queue row:** case ID (mono), reason family (plain text), amount (mono), confidence dot (color + label, not color alone), date. Hover state: subtle background shift to a slightly darker paper tone, no shadow.
- **Confidence bar:** simple horizontal bar, filled portion in the state color, numeric % alongside in mono type — not a circular gauge or a gradient meter (those read as generic dashboard decoration).
- **Evidence checklist:** checkmarks/x-marks with a strength qualifier (strong / weak / n/a) next to each — this is where the "explainable" story lives visually, so don't compress it into icons-only.
- **Packet viewer:** rendered as a document (serif body text, page-like white/paper background, generous margins) — it should visually read as "a document you could hand someone," reinforcing that this is a real deliverable, not just a UI state.
- **Audit trail:** a simple vertical log/ledger list, monospace timestamps, append-only visual metaphor (entries stack downward, nothing editable-looking).

## 4. Writing / Copy Direction

- Status labels are plain and literal: **Submit**, **Submit with caveats**, **Do not submit** — not "Approved"/"Rejected" (those imply a human dispute-resolution outcome, not this system's recommendation) and not cutesy alternatives.
- Empty/missing evidence fields say exactly what's missing and why it matters: "Delivery confirmation missing — required to support a Goods Not Received rebuttal," not a generic "No data available."
- The do-not-submit explanation is written in plain, non-apologetic terms: state what's missing and what would change the recommendation, not "Sorry, we couldn't process this."
- Buttons/actions are named by what the analyst does: "Export packet," "View audit trail," "Override recommendation" — never system-internal language like "Trigger packet generation."

## 5. Build Notes
- Keep this to a single-page app or a couple of routes (queue, case detail) — don't over-invest in the UI relative to the eval harness (see `phases.md` Phase 5 guidance).
- Respect `prefers-reduced-motion`: the stamp can have a brief page-load "stamp down" animation, but only once, and it should be skipped entirely under reduced-motion settings.
- Responsive floor: the queue and case-detail views should degrade to a usable single-column layout on a narrow viewport, even if the demo is shown on a laptop.
