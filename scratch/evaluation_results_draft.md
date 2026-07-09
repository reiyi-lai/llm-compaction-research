<!--
  DRAFT replacement prose for two sections of "Research Paper Full Updated.md":
    (A) Evaluation Design > Evaluation Metrics   (replaces the current bullet list)
    (B) Evaluation Results                        (replaces the current Results section)
  Figures live at: figures/fig1_budget_success.png, figures/fig2_retention_vs_db.png
  All numbers are pulled live from data/simulations/taskC_* (k=20 at 900w; k=5 at 250/500/1500w).
-->

## (A) Evaluation Metrics  *(prose, replaces the two-line bullet list)*

We separate the *mechanism* of compression from its *outcome*, and report three metrics.

**(i) Task success (database end state).** Our primary metric is binary task success, defined as an exact match between the final database state produced by replaying the agent’s trajectory and the gold database state (Appendix D). Success requires the write to update the reservation to the correct flight number *and* to charge the fare difference to the correct payment card; a deviation on either field yields a reward of zero. Because it compares end states rather than tool-call traces, the metric is outcome-based and path-independent — an agent that reaches the correct final state after re-reading the database scores identically to one that never lost the information.

**(ii) Needle retention in the knowledge block.** Task success is a downstream signal that is *buffered*: because reads remain enabled, an agent that has dropped an identifier from its knowledge block can sometimes recover it by re-querying the database. To measure the compression mechanism directly, we also record whether the exact payment identifier (the Visa card `credit_card_3092185`, ending 7447) survives verbatim in the *final* knowledge block — i.e. after both consolidation cuts. This isolates what the format *preserves* from what the agent can *reconstruct*.

**(iii) Token efficiency.** Finally, we measure the token cost of each format — both the summarizer’s block-generation cost, incurred at every cut, and the agent’s execution cost, since the block is re-sent on every subsequent turn — and combine it with task success to report cost per successful task.

---

# (B) Evaluation Results

## Task success and needle retention

At the 900-word block budget, with twenty trials per format, the choice of consolidation format produces a wide separation in task success: JSON succeeds on **90%** of trials, versus **50%** for Markdown and **45%** for prose. Because the fresh-payoff design searches the target flight only at the end — after both consolidation cuts, on data that is never compressed — all three formats select the correct flight (HAT909) in essentially every trial. The entire success gap is therefore attributable to a single scalar the user stated once, more than twenty turns and two re-compressions earlier: which card pays the fare difference.

Reading task success alongside block-level needle retention separates the mechanism from the outcome (Table 1, Figure 2).

**Table 1 — Needle retention vs. task success (900-word budget, k = 20).**

| format | Visa needle retained in final block | DB task success |
| ----- | :-----: | :-----: |
| prose | 9/20 (45%) | 9/20 (45%) |
| markdown | 17/20 (85%) | 10/20 (50%) |
| json | 19/20 (95%) | 18/20 (90%) |

![Figure 2. Block-level needle retention vs. DB task success by format (k = 20, 900-word budget). The light bar is the share of trials in which the exact Visa identifier survives in the final knowledge block; the solid bar is the share that end in a correct database write.](figures/fig2_retention_vs_db.png)

*Figure 2. Retention (light) vs. outcome (solid), k = 20.*

The two columns tell a mechanistic story. **JSON** preserves the identifier in 19 of 20 blocks and converts almost all of that retention into correct writes — the typed field both keeps the value and pins it to one unambiguous slot. **Prose** loses the identifier outright in more than half of trials: after two cuts the block no longer contains the Visa card at all, and task success falls in lockstep. **Markdown** is the instructive middle case — it retains the identifier in 85% of blocks yet converts only 50% into correct writes. Retention is *necessary but not sufficient*: because Markdown stores the value as free text under a heading (and in several trials lists both the Visa and the reservation’s default Mastercard), the identifier survives but is not unambiguously actionable. Structure that merely *carries* the value is not enough; JSON wins because its schema both retains the value and removes the ambiguity about which value to use.

This is precisely the failure our hypothesis predicts — *precise information degrades before categorical information*. The categorical constraint (“cheapest flight after 11:00”) survives prose compression reliably; the exact identifier (Visa …7447) is what dissolves. Section “Qualitative trace” below shows this happening inside a single prose block.

## Behavior under budget pressure

Figure 1 sweeps the summarizer’s length budget from 1500 down to 250 words. The powered point is 900 words (k = 20, tight confidence intervals); the 250-, 500-, and 1500-word points are k = 5 and carry wide Wilson intervals, so they should be read as tendencies rather than precise estimates.

![Figure 1. DB task-success rate vs. summarizer length budget, by format, with Wilson 95% confidence intervals. The 900-word point is k = 20; the others are k = 5.](figures/fig1_budget_success.png)

*Figure 1. Task success vs. block token budget (bars = 95% Wilson CIs).*

Two things are visible. First, JSON is at or above both other formats at every budget and is the only format that never drops below 60% success. Second, the formats converge at the loosest budget (1500 words), where the small k = 5 samples coincide at 3/5 and the intervals are too wide to separate — a reminder that the budget-sweep cells are exploratory. The robust claim is the powered 900-word result and the general tendency: as the block is squeezed, the structured format is the one that keeps holding the identifier. (The budget sweep is analyzed in more detail, including the compression-ratio curve, in the supplementary analysis.)

## Qualitative trace: how prose fails silently

The mechanism is clearest in the trials themselves. Both traces below come from the k = 20 run at the 900-word budget; both agents receive the identical opening turn and both correctly select HAT909 at payoff. They differ only in the format of the two knowledge blocks that carry the user’s payment instruction across the two consolidation cuts.

**Shared opening turn (stated once, never repeated):**

> “I’m reorganizing a few trips today. Later on I’ll want to change my Charlotte (CLT) to Orlando (MCO) reservation (VAAOXJ) to the cheapest flight that departs after 11:00 AM that same day, and pay any fare difference with my Visa card ending 7447 — but please do NOT look that one up or change it yet…”

**JSON — final knowledge block after 2 cuts (trial `0609d995`, ✓):** the instruction is pinned in a typed field, verbatim.

```json
"user_request_and_constraints": [
  "Reorganize trips, specifically change Charlotte (CLT) to Orlando (MCO) reservation (VAAOXJ)
   to the cheapest flight after 11:00 AM, pay fare difference with Visa card ending 7447,
   but do not change it yet.",
  ...
]
```
→ **Write:** `update_reservation_flights(… payment_id="credit_card_3092185")`  → Visa.
→ **Agent’s closing message:** *“…The $90 fare difference has been charged to your Visa ending 7447.”*  **DB ✓**

**Prose — final knowledge block after 2 cuts (trial `ff20ff08`, ✗):** the *categorical* constraint survives, but the *precise identifier* has dissolved into a generic phrase.

> “…They have a flight from Charlotte (CLT) to Orlando (MCO) with the identifier VAAOXJ, which they intend to change to **the cheapest available flight departing after 11:00 AM** on the same day… before proceeding with any bookings, the assistant will require confirmation from the user regarding their preferred flight option… including details such as the flight number, cabin class, number of passengers, and **payment method**.”

The block still knows the flight must be the *cheapest after 11:00* — the categorical rule is intact — but the Visa card and the digits 7447 are simply gone; only a generic “payment method” remains. Lacking the instruction, the agent falls back to the reservation’s stored default card, the Mastercard.

→ **Write:** `update_reservation_flights(… payment_id="credit_card_1052991")`  → Mastercard (wrong).
→ **Agent’s closing message:** *“Your reservation VAAOXJ has been updated successfully.”*  **DB ✗**

The failure is **silent**: the prose agent selects the correct flight, confirms the change, and reports success without ever naming a card — so neither the user nor a casual reviewer sees that the wrong account was charged. This is the concrete cost of losing a precise identifier in compression: not a crash or a refusal, but a confident, wrong-valued write.

## Token efficiency

*(Keep the existing two token-efficiency tables; convert the trailing bullets to the prose below.)*

The token accounting shows that structure does not pay for its fidelity with tokens. The summarizer’s block-generation cost is real and recurs at every cut, but it is second-order relative to agent execution, which re-sends the block on every turn. Prose is in fact the most expensive format overall, not because its blocks are large but because losing the identifier triggers recovery churn — extra turns re-fetching the user record and disambiguating the card. Combining cost with correctness, JSON delivers a correct outcome for roughly half the tokens of prose: its cost per *successful* task is the lowest of the three, because it both costs less and succeeds more. The “cheap” lean-prose block is the most expensive format per useful result.
