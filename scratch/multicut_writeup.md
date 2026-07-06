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

## 3b. Budget sweep — compression-ratio curve

Sweeping the summarizer length budget (250 / 500 / 900 / 1500 words; k=5 per cell, 900 reused from the k-run) shows *where* under budget pressure each format's retention breaks — `ratio = block_tokens / summarizer_input_tokens` (lower = more compression), averaged over cuts:

| format | ratio (block/input) | block tok | Visa-needle retention @ 250 / 500 / 900 / 1500 |
|--------|:---:|:---:|:---|
| **json** | **~0.25 (flat)** | 262–339 | **3/5 · 5/5 · 19/20 · 3/5** |
| prose | 0.25 → 0.41 (rises) | 325–615 | 1/5 · 3/5 · 9/20 · 1/5 |
| markdown | 0.29 → 0.46 (rises) | 369–721 | 0/5 · 3/5 · 17/20 · 3/5 |
| **json_struct** | **~0.6 (flat, high)** | ~1,100 | **5/5 · 5/5 · 13/15 · 4/5** |

**DB success (task outcome) by budget × format:**

| format | DB @ 250 | @ 500 | @ 900 | @ 1500 |
|--------|:---:|:---:|:---:|:---:|
| prose | 3/4 | 2/5 | 9/18 | 3/5 |
| markdown | 1/5 | 4/5 | 10/20 | 3/5 |
| **json** | 4/5 | 5/5 | 18/20 | 3/5 |
| **json_struct** | 5/5 | 3/5 | 13/15 | 4/5 |

The JSON formats dominate DB across budgets — and, tellingly, **at the tightest budget (250w) the ordering is starkest**: `json_struct` 5/5 and `json` 4/5 vs `markdown` 1/5. (The 900w column is the higher-powered k≈15–20 point; the rest are k=5.) DB tracks the needle-retention curve only *loosely* — it is noisier because reads-on lets the agent sometimes recover a dropped needle by re-fetching, and because the 1500w cells are subject to n=5 reasoning variance (e.g. prose/md/json all dip to 3/5 at 1500w despite ample budget). So **needle retention is the cleaner signal; DB is the downstream, buffered readout.**

**The crossover.** As the budget tightens, only the JSON formats still hold the exact identifier. At **250w**: `json_struct` **5/5** and `json` **3/5** retain the Visa needle, while `prose` **1/5** and `markdown` **0/5** lose it. So under budget pressure structured formats preserve the identifier and prose/markdown blur it — and the gap widens as budget shrinks.

**Two very different compression behaviors among the JSON arms:**
- **naive `json` is the efficient sweet spot** — it *honors* the budget (ratio flat ~0.25, ~290-tok blocks = most compressed) **and** retains the scalar identifier well. A scalar id fits cheaply in a lean field, so json gets tight compression *and* fidelity.
- **`json_struct` largely *ignores* the budget** — blocks stay ~1,100 tok even at a "250-word" instruction (ratio ~0.6). Its perfect low-budget retention is partly because it *does not actually compress* to the budget: block size tracks the *number of records the model chooses to emit*, not the word budget.

**Prose/markdown compress but lossily** — at 250w their blocks are a similar size (325–369 tok) yet they lose the needle (1/5, 0/5); they spend the budget on narrative that blurs the identifier.

*Per-token fidelity ranking (at a fixed budget):* **naive json > json_struct > markdown > prose**, with the gap widening as budget tightens.

> **Caveat — `json_struct` numbers are pre-flattening.** This sweep used the original strict `{key,value}` schema. The flat-record redesign cuts ~40% per record (a 900w block dropped ~1,700 → ~960 tok), but a single check showed it still ignores the word budget (a 500w block emitted *all* 15 flights → ~1,456 tok). The `json_struct` row above will be re-measured with the flat schema; **prose / markdown / json rows are unaffected.**

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
