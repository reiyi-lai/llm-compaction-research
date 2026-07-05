# Multi-Cut Analysis

*Task C (airline, id 102) · k=5 per format · agent = gpt-5-mini, summarizer = gpt-4o-mini,
user simulator = gpt-5-mini · reads-on · 2 consolidation cuts · 900-word budget · temp 0.*

## 1. What the experiment tests

Whether structured consolidation retains an exact identifier through *repeated* rounds of compression better than prose. 

**Design:**

**Two needles are stated in the opening turn and never repeated/re-read:**
  - *exact-id:* pay with the Visa `credit_card_3092185` (…7447), **not** the Mastercard `credit_card_1052991`. 
The Mastercard is the reservation's `payment_history` default, so it is a **distractor**: if the agent loses the "use the Visa" instruction in context, it falls back to the wrong card.
- *categorical:* the new flight must depart **after 11:00** and be the **cheapest** option.
- Two more searches (PHX→LAS, DFW→SEA) serve as distraction and trigger a consolidation cut each, so the initial context is **re-compressed twice** before they are acted on.
- **The actual trip (CLT→MCO) that requires a *write* is searched fresh at the end** and the read of the flight table is never compacted. Task success focuses on whether the needles survived the rounds of compaction.

## 2. Correctness results

| format | Visa needle retained | wrote Visa | wrote Mastercard | **DB success** |
|--------|:---:|:---:|:---:|:---:|
| prose | 3/5 | 3/5 | 2/5 | **60%** |
| markdown | 3/5 | 2/5 | 3/5 | **40%** |
| **json** | **5/5** | **5/5** | 0/5 | **100%** |
| **json_struct** | **5/5** | **5/5** | 0/5 | **100%** |

- **All 20 trials wrote the correct flight (HAT909).** The fresh-payoff design plus the gpt-5-mini agent removed the flight-selection confound entirely, so DB differences are attributable to the *payment needle* alone.


## 3. Token economics

Computed from actual `usage` on every LLM call (`--llm-log-mode all`).

| format | cuts | Input Tokens to Summarizer | **block gen (out)** | Total Cost of Compression Calls ($) | agent calls | agent input | **TOTAL tok** | **TOTAL $** |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| prose | 2 | 4,073 | 1,297 | 1.39 | 16 | 95,918 | **114,897** | **35.0** |
| markdown | 2 | 3,897 | 1,584 | 1.53 | 14 | 78,442 | 94,129 | 27.0 |
| json | 2 | 2,495 | **730** | **0.81** | 14 | 82,273 | 95,876 | 27.7 |
| json_struct | 2 | 3,801 | **2,329** | 1.97 | 13 | 81,515 | 97,750 | 27.6 |

*To remove `cuts` column.
$ in units of 10⁻³. 
`block gen` = summarizer output. 
`agent input` includes the blocks re-sent each turn.*

**But summarizer overhead is dwarfed by agent execution** (~2 vs ~26). Block size barely moves the total; **agent work does** — and there **prose is the outlier** (16 calls / 96K input / $35, ~30% above the rest).

**Why prose costs more — the same lesson as single-cut, via a new mechanism.** 
Prose isn't expensive because of block size (its blocks are mid-sized). Losing the needle triggers **recovery churn** — extra turns re-fetching the user and untangling the wrong card (16 calls vs 13 for json_struct). Poor retention has a token cost. **json_struct's big blocks are essentially free overall**: the overhead is tiny next to execution, and clean retention avoids the churn.

### Cost per *correct* task (efficiency × correctness)

| format | $/trial | DB | **$ per correct task** |
|--------|:---:|:---:|:---:|
| prose | 35.0 | 60% | 58.4 |
| markdown | 27.0 | 40% | 67.5 |
| json | 27.7 | 100% | **27.7** |
| json_struct | 27.6 | 100% | **27.6** |

**JSON formats deliver a correct outcome for ~2.1–2.4× fewer tokens than prose/markdown** — they cost *less* and succeed *more*. The "cheap" lean-prose block is the most expensive per useful result.

## 4. Synthesis

Under production-style compaction (reads-on, repeated cuts), the format of the compressed context has a compounding effect:

1. **Fidelity:** structured formats preserve exact identifiers across re-compressions; prose/markdown progressively lose them, causing silent wrong-value substitution (here: the wrong payment card).
2. **The block-generation cost is real and recurring** (structure pays it every cut), but it is second-order relative to agent execution, so it does not overturn the net advantage.

## 5. Relation to single-cut study

The two experiments isolate two distinct mechanisms:

- **Single-cut → collections.** Data-level structure (`json_struct` records) preserves a
  *collection* (the flight table) that prose/markdown/flat-JSON collapse into a summary
  phrase. Effect: **data-level structure vs. everything else.**
- **Multi-cut → scalars.** Repeated re-compression degrades even a *scalar* identifier in prose/markdown; any structured field (naive JSON or records) anchors it. 
Effect:  **structured vs. unstructured, emerging only under compounding.**

Together: structure protects *what it structures*, and compounding compaction is where the protection becomes decisive — for collections in one pass, and for scalars over many.

## 6. Caveats & next steps

- **n = 5 per cell.** Per-format, json_struct 5/5 vs md 2/5 is suggestive (Fisher p≈0.16); **pooled JSON 10/10 vs prose+markdown 5/10** is the stronger contrast (p≈0.03). Firm with **k ≥ 20**.
- **Uncached token counts.** Prompt caching discounts the block re-sends (shared by all formats) but not prose's extra recovery turns, so caching would **widen** prose's cost disadvantage.
- Minor needle-detection noise (1–2 prose trials wrote Visa despite the scorer not surfacing it in the block — recent-tail recovery or a missed substring); does not change the aggregate direction.
**Next:** k=20 to firm significance; optionally a position-robustness variant (introduce the needle at a later cut) and a collection-needle multi-cut (compounding × collections).
