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

| format | **Summarizer** in / out / $ | **Agent** in / out / $ | **TOTAL tok** | **TOTAL $** |
|--------|:---:|:---:|:---:|:---:|
| prose | 3,589 / 1,230 / 1.28 | 96,162 / 12,074 / 30.90 | 113,055 | 32.18 |
| markdown | 3,775 / 1,441 / 1.43 | 101,367 / 13,318 / 33.54 | 119,901 | 34.97 |
| **json** | **3,012 / 635 / 0.83** | **84,383 / 11,571 / 28.73** | **99,601** | **29.56** |

*k = 20 per format (900-word budget); per-trial averages, 2 cuts each.
Summarizer / Agent cells are shown as input / output / cost.
$ in units of 10⁻³. TOTAL tok = summarizer (in+out) + agent (in+out); TOTAL $ = summarizer $ + agent $.
`agent input` includes the block re-sent every turn.*

**Summarizer overhead is dwarfed by agent execution** (~1–2 vs ~29–35), so block size matters mainly through the *re-send* — the block is re-injected every turn — not the one-time generation. On every axis (summarizer input, block output, summarizer cost, agent input/output, TOTAL tokens, TOTAL cost) **json is the cheapest format**. **Markdown is the most expensive**: its blocks are the largest (1,441 output tok vs json's 635) and are re-sent each turn, pushing agent input to 101K.

**Prose's cost is a runaway *tail*, not a high mean.** Prose was the only format to produce non-terminating trials: 2 of 20 hit the 60-step cap (`max_steps`) without ever completing a write, at ~3× the tokens of a normal trial (≈268K and ≈303K tok) — the extreme of needle-loss recovery churn. There is nothing comparable to exclude for markdown/json (both completed 20/20). Excluding prose's two runaways, its *completed-trial* mean is **93,914 tok / $0.0295** — essentially **tied with json** on raw cost. So prose's headline expense comes from worst-case blow-ups, a failure mode the structured formats never enter.

| format | normal `user_stop` | `max_steps` runaway | trials with a write |
|--------|:---:|:---:|:---:|
| prose | 18 | **2** | 18 |
| markdown | 20 | 0 | 20 |
| json | 20 | 0 | 20 |

### Cost per *correct* task (efficiency × correctness)

| format | $/trial | DB | **$ per correct task** |
|--------|:---:|:---:|:---:|
| prose | 32.18 | 45% | 71.5 |
| markdown | 34.97 | 50% | 69.9 |
| **json** | 29.56 | 90% | **32.8** |

*(DB at k = 20, 900-word budget; $/trial is the all-20 mean. $ in units of 10⁻³.)*

**JSON delivers a correct outcome for ~2.1× fewer tokens than prose or markdown** — it costs *less* and succeeds *more*. Once the low success rate is priced in, the "cheap" lean-prose block is the most expensive per useful result.

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
