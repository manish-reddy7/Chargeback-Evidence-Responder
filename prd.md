# PRD: Chargeback Evidence Responder
**Track:** Razorpay AI Buildathon — 02: AI Risk Manager
**Status:** Draft v1

---

## 1. Problem Statement

When a customer disputes a charge, the merchant has a short window (typically 7–21 days depending on card network and reason code) to submit compelling evidence or lose the dispute automatically. Today this is manual: an ops person digs through order records, shipping logs, and support tickets, matches them to the specific reason code, and writes a rebuttal — often under time pressure, often inconsistently, and often for cases that were never winnable in the first place.

**Core insight the product must demonstrate:** the hard part isn't generating a rebuttal — it's knowing *when not to*. Auto-fighting a weak dispute burns ops time, can trigger card-network penalties for high dispute-response rates, and can damage the merchant's standing. The judging bar explicitly asks for false-positive cost and defense-only behavior, so **evidence sufficiency assessment is a first-class feature, not an afterthought.**

## 2. Goal

Build an agent that, given a disputed transaction and the merchant's available order data, does three things:
1. Classifies the dispute by reason code category.
2. Assembles the reason-code-appropriate evidence packet from available data sources.
3. Outputs a **recommendation with confidence**: Submit / Submit-with-caveats / Do-not-submit (insufficient evidence), never a blind auto-submit.

## 3. Non-Goals
- Not building a payment gateway integration or a real dispute-filing API call (Razorpay test-mode data only, output is a formatted packet — no live submission).
- Not covering every card network's rulebook exhaustively — pick 3–4 common reason code families and go deep, not shallow-and-wide.
- Not doing fraud detection upstream (that's Chargeback *prevention*, a different problem) — this is response/rebuttal only, post-dispute.
- No offense-capable behavior (nothing that could be used to fabricate evidence or game a dispute outcome dishonestly) — every generated document must trace to real underlying data fields.

## 4. Reason Code Scope (pick these to start)
| Family | Example reason | Evidence needed |
|---|---|---|
| Goods/Service Not Received | "Item never arrived" | Shipping carrier tracking, delivery confirmation/signature, delivery photo if available |
| Not As Described / Defective | "Item was damaged/wrong item" | Product listing snapshot, return policy shown at purchase, any support ticket resolution |
| Unauthorized Transaction | "I didn't make this purchase" | AVS/CVV match, device fingerprint, IP geolocation vs. billing address, prior purchase history from same device/account, 3DS authentication result |
| Duplicate/Processing Error | "Charged twice" | Transaction log showing distinct order IDs, timestamps, idempotency key trace |

## 5. User & Use Case
**Primary user:** Merchant risk/ops analyst using Razorpay's dashboard, handling dispute queues.
**Trigger:** A new dispute notification comes in (webhook/test event) with a reason code and transaction ID.
**Output:** A structured evidence packet (document) + a recommendation + audit trail, ready either for human review or (in a gated future state) auto-submission.

## 6. Functional Requirements

### 6.1 Input
- Transaction record (amount, timestamp, payment method, AVS/CVV result, 3DS status)
- Order record (SKU, shipping address, delivery status, carrier tracking ID)
- Customer account history (account age, prior orders, device/IP history)
- Support ticket log tied to the order, if any
- Dispute metadata: reason code, dispute amount, deadline

### 6.2 Processing pipeline
1. **Classify** reason code into one of the 4 families above.
2. **Retrieve** the relevant evidence fields for that family from the input sources (structured lookup, not generation).
3. **Score sufficiency**: for each required evidence field in the family's checklist, mark present/missing/weak. Compute a confidence score.
4. **Generate packet**: draft the rebuttal narrative *only* from retrieved fields — no fabricated claims. Every sentence in the output should be traceable to a specific input field.
5. **Recommend action**:
   - High confidence (all key evidence present, strong match) → Submit
   - Medium confidence (partial evidence) → Submit-with-caveats, flagged for human review
   - Low confidence (missing critical evidence) → Do-not-submit, explain why, suggest what data would change the outcome
6. **Log audit trail**: input snapshot, evidence checklist result, confidence score, final recommendation, timestamp — immutable per case.

### 6.3 Output
- Formatted evidence packet (PDF/markdown) mapped to reason code
- Recommendation + confidence score + reasoning
- Audit trail entry

## 7. Evaluation Plan (this is what wins the track)

- Held-out synthetic test set: 50–100 disputes across the 4 reason code families, with a known ground-truth "should this win or lose" label decided before running the model.
- Metrics:
  - Precision/recall on the Submit decision
  - False-positive cost in ₹ or a defined unit (ops time + dispute-ratio penalty risk), not just a percentage
  - Coverage: % classified/processed vs. punted to a human, reported honestly
- Show one explicit failure case end-to-end plus one correct "do-not-submit" case, walked through in the demo.

## 8. Guardrails / "Bar" Compliance
- Every generated evidence document cites the source field it came from — no free-text fabrication.
- Confidence thresholds for Submit are tunable and shown in the demo.
- No auto-submission to a live dispute API — output stops at "packet ready for human sign-off," explicitly stated as the safety boundary.
- "Do-not-submit" cases are logged and surfaced, not cherry-picked out of the demo.

## 9. Success Criteria for the Buildathon Submission
- [ ] Working pipeline on synthetic Razorpay test-mode-style data
- [ ] 4 reason code families supported
- [ ] Held-out test set with published precision/recall + false-positive cost framing
- [ ] At least 2 walked-through cases (1 win, 1 correctly declined) in the demo
- [ ] Public repo with README explaining architecture and guardrails
- [ ] Audit trail visible for every processed dispute
