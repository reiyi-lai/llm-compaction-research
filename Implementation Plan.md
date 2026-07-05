# Implementation Plan — Structured Consolidation Formats for LLM Agent Context Compression

Companion to **Evaluation Set-up.md**. This doc translates the research design into concrete, repo-grounded engineering work: what to build, where in the tau2-bench codebase, and in what order. It also records the finalized design decisions and the reasoning behind the tricky ones.

---

## 0. Finalized design decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Consolidation harness | **Build natively inside tau2** as a custom agent subclass | Self-contained; no external "Focus" dependency; orchestrator treats agent state as opaque, so no orchestrator/scoring changes needed for the mechanism |
| Agent model | **gpt-4o-mini**, same model performs summarization | OpenAI-only; cheap pilot; summarizer = agent model |
| Consolidation cadence | **Single cut** (one gather→act boundary) for the pilot | Cleanest causal claim; multi-cycle deferred to a follow-up |
| Boundary trigger | **Intercept the first WRITE tool-call attempt** | Deterministic; cut always sits between gather and act; keeps the consolidation *input* identical across all three formats (format is applied only at summarizer output, never in phase 1) |
| Format visibility | **Format hidden from the acting agent during phase 1** | Keeps phase-1 behavior format-invariant; the format lives only in the summarizer's system prompt |
| Compression pressure | **Swept instructional budget** in the summarizer prompt (e.g. "≤ 400/200/100/50 words") + a generous `max_tokens` safety ceiling | Instruction = a budget the model plans around (graceful, prioritized compression); `max_tokens` alone would truncate mid-sentence / produce invalid JSON |
| Ratio measurement | **Measure realized ratio** (`block_tokens ÷ phase1_input_tokens`); plot performance/retention against the realized value | You induce a target budget and measure what actually comes out — you can't dial in an exact ratio |
| Phase-1 density | **Per-task `initial_state.initialization_data`** (inject custom flights/reservations) | Controlled, reproducible, does not mutate the shared `db.json` |
| Conditions | **No-Compression ceiling** = vanilla `llm_agent` (full history). Format conditions: **prose = control format**, **markdown** & **JSON** = structured treatments | Two must-succeeds: No-Compression must pass everywhere (task solvable); prose must pass at the gentle end of the sweep (control anchor). Signal = md/JSON holding where prose degrades, esp. on exact identifiers |
| Tasks | **Task A** (economy → modify) and **Task B** (basic-economy → do-not-modify) | Matched request differing only by cabin tier; the decisive fact (cabin) sits on the far side of the consolidation boundary |

---

## 1. How the repo works (grounding for the plan)

Concrete anchors so the edits below are unambiguous.

### Agent loop
- Agents live in `src/tau2/agent/llm_agent.py`. Default `LLMAgent` (subclasses `LLMConfigMixin` + `HalfDuplexAgent` from `agent/base_agent.py`).
- **System prompt** = `AGENT_INSTRUCTION` + `SYSTEM_PROMPT` template (`<instructions>…</instructions><policy>{domain_policy}</policy>`), assembled in the `system_prompt` property (`llm_agent.py:78–82`). `domain_policy` comes from `environment.get_policy()`.
- **Tool definitions are NOT in the system-prompt text** — they are passed to the LLM as native function-calling schemas (`tools=[t.openai_schema …]` in `utils/llm_utils.py:generate()`).
- **State** (`LLMAgentState`): `system_messages` + `messages`. History grows monotonically; the full list is rebuilt every turn (`state.system_messages + state.messages`, `llm_agent.py:127`). **Nothing trims or summarizes it.**
- Turn logic: `_generate_next_message` (`llm_agent.py:105–135`) — append incoming msg → concat → `generate(...)` → append assistant msg → return.

### Orchestrator
- `src/tau2/orchestrator/orchestrator.py`. `Orchestrator.step()` routes one in-flight message between `AGENT`/`USER`/`ENV`. Action cap via `max_steps` (default `DEFAULT_MAX_STEPS=200`, `config.py:4`). **Treats agent state as opaque** → our compaction can live entirely inside the agent.

### LLM call
- `src/tau2/utils/llm_utils.py:generate()` wraps litellm `completion()`. Native function calling. `temperature`/`seed`/`max_tokens` flow through `llm_args`/`**kwargs`. `litellm.drop_params=True`. Per-message `.usage` and `.cost` are captured and persisted.

### No existing compaction
- Full-tree search confirms **no compaction / consolidation / summarization / pruning** in the agent loop. The only "summarize"-adjacent thing is `banking_knowledge/retrieval_mixins.py:rewrite_context` — an agent-*invokable* tool that echoes a string and does **not** prune history. **Our mechanism is net-new.**

### Registry & CLI
- `src/tau2/registry.py` — agents registered as factories `factory(tools, domain_policy, **kwargs)` via `register_agent_factory(factory, name, …)` (built-ins at ~lines 297–312).
- `src/tau2/cli.py` — `--agent` (choices from registry), `--agent-llm`, `--agent-llm-args` (default `{"temperature":0.0}`), `--user-llm`, `--task-ids`, `--num-trials`, `--max-steps`, `--seed`, `--save-to`, `--verbose-logs`, `--max-concurrency`.
- `--agent-llm-args` feeds the **LLM**, not agent-construction kwargs → simplest way to select a format condition is **one registered agent name per condition**.

### Tasks & scoring
- Airline tasks: `data/tau2/domains/airline/tasks.json` (array of `Task` objects); splits in `split_tasks.json`. Model: `src/tau2/data_model/tasks.py` (`Task`, `EvaluationCriteria`, `Action`, `UserScenario`, `StructuredUserInstructions`, `InitialState`, `InitializationData`).
- Airline `reward_basis = ["DB","COMMUNICATE"]`, final reward = `r_DB × r_COMMUNICATE ∈ {0,1}`.
- **r_DB** (`evaluator/evaluator_env.py`): replay the agent's actual WRITE tool calls onto a fresh DB, replay the gold `evaluation_criteria.actions` onto another fresh DB, **compare full-DB SHA-256 hashes** (`get_db_hash`). Exact-match: any value change anywhere flips the hash. `actions: []` ⇒ gold DB == initial DB ⇒ passes only if the agent writes nothing.
- **r_COMMUNICATE** (`evaluator/evaluator_communicate.py`): every string in `communicate_info` must appear (case-insensitive substring) in some assistant message.
- Only the 6 WRITE tools mutate the DB (`book_reservation`, `cancel_reservation`, `update_reservation_flights`, `update_reservation_baggages`, `update_reservation_passengers`, `send_certificate`); reads/`calculate` never affect the hash. `update_reservation_flights` in `domains/airline/tools.py:591`.
- Airline DB: `data/tau2/domains/airline/db.json` (300 flights / 500 users / 2000 reservations). Policy: `data/tau2/domains/airline/policy.md`.

### User simulator
- `src/tau2/user/user_simulator.py` — **LLM-driven, not scriptable** (except `DummyUser`, solo-mode only). Determinism via temperature 0 + seed + fully-specified `known_info`. "Scripted" content should come from **deterministic tool outputs**, not user chatter.

---

## 2. Trigger & compression-pressure reasoning (why the locked choices)

**Separate two things the trigger conflates:**
- **Boundary** = *where* the gather→act cut is. → `write-intercept`.
- **Compression pressure** = *how hard* we squeeze. → swept **instructional** summary budget.

**Validity rule:** the *input* to consolidation must be identical across the three formats; format may differ only at the *output*. Write-intercept guarantees this because the format is never revealed in phase 1 — all three formats consolidate the same phase-1 trajectory.

**Why not a context-% threshold (Anthropic-style):** in a *single* cut it fires at the same place for all formats (harmless), but it buys nothing over write-intercept and — the moment we go **multi-cycle** — it silently makes each cycle's *input size* depend on the previous block's size, i.e. a more compact format digests a bigger haystack per round. That confounds format with input-size. Deferred with the multi-cycle extension.

**"JSON = compact" is an assumption, not a fact.** JSON pays structural overhead (field names, braces, quotes); for the same facts it is often *more* tokens than terse prose. Compactness is an **outcome we measure** (token-efficiency metric), never an input we bake into the trigger. Corollary: a *fixed* output budget would penalize JSON's overhead — so we sweep the budget and plot against the **realized** ratio instead.

**Instructional budget vs `max_tokens`:**
- `max_tokens` = hard API cap the model is unaware of → truncates mid-sentence / yields invalid JSON. Use only as a safety ceiling set *above* the instruction.
- Instructional budget (in the summarizer prompt) = a target the model plans around → graceful, prioritized compression. **This is the swept pressure knob.**

---

## 3. Workstreams

### Workstream A — The consolidation agent (core mechanism, build first)
New class `ConsolidatingLLMAgent(LLMAgent)` (new file `src/tau2/agent/consolidating_agent.py`). Everything below lives here.

- **A1 · State.** Extend `LLMAgentState` with `phase` (`"gather"|"act"`), `knowledge_block: str|None`, `consolidated: bool`, and a stash of the pre-consolidation raw phase-1 history + its token count (for the retention audit later). Provide a `get_init_state` that seeds `phase="gather"`.
- **A2 · Trigger.** In `_generate_next_message`, after the LLM returns an `AssistantMessage`: if `not consolidated` and the message contains a **WRITE** tool call (detect via the tool's `ToolType.WRITE` / `mutates_state`), **do not return that tool call to the orchestrator.** Instead fire consolidation (A3), then re-generate so the agent re-decides the write from the block alone.
  - *Min-gather guard:* optionally require that the necessary READ tools have been called before allowing the intercept, so an early write doesn't consolidate an incomplete haystack.
- **A3 · Summarizer call.** A **separate, transient `generate()` call** whose messages are the phase-1 history (`state.messages`) and whose **own summarizer system prompt** = `[constant retention specification (A6)] + [format scaffolding (A5, the variable)]`. Pass the instructional budget (varied) in the prompt and a generous `max_tokens` ceiling. For **JSON**, additionally pass OpenAI structured output (`response_format={"type":"json_schema","json_schema":{…}}`) so the schema is API-enforced.
  - *Terminology note:* two unrelated things are called "policy." The **domain policy** (airline `policy.md`) = rules the acting agent obeys, lives in the agent's `system_messages` and is untouched (persists into phase 2 via A4). The **retention specifications** (A6) = instructions to the summarizer about what to keep/discard. They are different system prompts on different LLM calls.
- **A4 · Prune + re-inject.** Replace `state.messages` with single Knowledge-block at the top of context; keep the system prompt `system_messages` (instructions + policy) intact. Set `phase="act"`, `consolidated=True`. Phase 2 now sees **only** block + system prompt.
- **A5 · Three format configs.** `prose`, `markdown`, `json` summary system prompts. JSON also carries the typed schema (fields: attempted actions; facts-learned typed as {file/location, behavioral observation, negative finding}; active constraints + source; outcomes; unresolved items — per Evaluation Set-up.md §Overview).
- **A6 · Constant retention specification.** The summarizer's what-to-keep/discard instructions, shared verbatim across all three formats: "keep decisions / constraints / state / exact identifiers; discard intermediate reasoning and verbose tool dumps; keep recent turns." Only the **format scaffolding (A5)** varies on top of this — that is what makes format the sole experimental variable. (Not to be confused with the domain policy; see A3 terminology note.)
- **A7 · Instrumentation.** Persist into the simulation record (surface via agent state → `SimulationRun.info`): the Knowledge block (verbatim), phase-1 input token count, block token count, realized ratio, chosen format, instructed budget. These feed Workstream D with no re-derivation.

### Workstream B — Register & select conditions
- **B1** Factory `create_consolidating_agent(tools, domain_policy, **kwargs)` reading `consolidation_format`, `summary_budget`, `summarizer_model` (default = agent llm).
- **B2** Register **four agents** in `registry.py`: `consolidate_prose` (**control format**), `consolidate_md`, `consolidate_json` (structured **treatments**; each pins its format), plus built-in `llm_agent` as the **No-Compression ceiling** (not a format condition). Run each with `--agent <name>`.
  - *Two must-succeeds:* **No-Compression** must pass on both tasks (proves the task is solvable — critical since our tasks are custom). **Prose** must pass at the gentle end of the compression sweep (anchors the control); it is *expected* to fail as pressure rises — that failure is the signal. Pick the gentle operating point so both pass there.
- **B3** (Optional) allow overriding `summary_budget` per run via an env var read in the factory, so the budget sweep needs no code edits.

### Workstream C — Tasks + dense Phase 1
- **C1 · Anchor data.** Choose/craft a user with an **economy** reservation (Task A) and a **basic-economy** reservation (Task B), an existing registered **Visa ending 7447** (the Task-A payment method), plus decoy methods (other cards / certificates), on a route with many post-11:00-EST lookalike flights.
- **C2 · Task A (modify).** `user_scenario.instructions` with all constraints front-loaded (after-11:00 EST on <date(s)>, keep cabin, cheapest qualifying, **pay the difference with the existing Visa ending 7447** — see Risk 1); `evaluation_criteria.actions` = the exact gold WRITE(s) using **real IDs** (including the resolved `credit_card_…` payment_id); `communicate_info` for required spoken values; `reward_basis:["DB","COMMUNICATE"]`.
- **C3 · Task B (do-not-modify).** Identical request but basic-economy; `actions: []` (⇒ pass only if the agent writes nothing); `nl_assertions` for the policy-cited refusal (diagnostic).
- **C4 · Register tasks.** Append both to `tasks.json` with unique IDs; add IDs to `split_tasks.json` (or run with an unfiltered split).
- **C5 · Phase- 1 Density** via `initial_state`. Inject ~15 lookalike flights + multiple competing reservations through `initial_state.initialization_data.agent_data` (merged into `FlightDB`), so gather produces a large, identifier-dense history without touching shared `db.json`.
- **C6 · Gold-action validation.** Replay each gold trajectory on a fresh env; confirm it executes cleanly and yields the intended DB hash. **See Risk 1** (certificate payment).

### Workstream D — Metrics & analysis (offline, on `results.json`)
- **D1** Per-category retention audit against the stored Knowledge block: regex/substring for exact IDs & numbers; LLM-judge for semantic facts / preferences / negative findings. By-category retention table.
- **D2** Compression-ratio computation from stored token counts (D uses A7's fields directly).
- **D3** Failure-taxonomy classifier: wrong-argument / wrong-info / wrong-decision / partial-resolution; separate compression-caused from unrelated reasoning errors.
- **D4** Sweep harness: run the matrix (format × budget × task × trials), collect realized ratios, plot **retention** and **task-success** vs **realized ratio** (the headline curve). Also needle-position analysis (early/middle/late within tool outputs).

### Workstream E — Validation (the doc's to-do)
- **E1** Confirm consolidation fires at the intended boundary (first write), on the vanilla task set first.
- **E2** Confirm the **No-Compression ceiling** passes on both tasks (task solvable), and **prose passes at the gentle operating point** (control anchor).
- **E3** Confirm that under aggressive compression at least one format breaks the constraint (signal exists; avoid the "all succeed" no-signal regime).
- **E4** Dump intermediate history / block / token counts for inspection.

---

## 4. Design risks

1. **Certificate payment in Task A — CONFIRMED invalid (blocker, resolved).** Verified: `_payment_for_update` raises `"Certificate cannot be used to update reservation"` (`tools.py`), and `policy.md:131`+`:80` require a flight change be paid by **a single gift card or credit card already in the user profile** — no certificates, no splitting, no unregistered cards. The doc's "larger certificate first, then Visa 7447" is impossible and would fail the No-Compression ceiling. **Fix:** pay the full fare difference with the user's **existing registered Visa ending 7447** (single credit card; credit cards have no balance check, so any positive difference clears). Stays policy-valid and preserves an exact-ID needle — user names "Visa ending 7447", agent must resolve it to the exact `credit_card_…` payment_id across the boundary. The "cheapest qualifying flight" constraint already supplies the numerical needle, so no gift-card split is needed; certificates/other methods stay in-profile as decoys. (A card *number stated but not registered* is impossible — tool rejects unknown ids, policy forbids it — and would wrongly turn Task A into a refusal.)
2. **r_DB is an exact full-DB hash match.** Task A passes only if the agent's net mutation *exactly* equals the gold trajectory (fields, `payment_history` entries, ordering effects). The gold `actions` must be constructed precisely and replay-verified (C6).
3. **No scripted user.** Phase-1 determinism relies on deterministic tool outputs + fully-specified `known_info` + temperature 0 + seed. If the LLM user proves too variable, consider a custom registered user class (extra work, out of pilot scope).
4. **Early-write intercept.** If the agent writes before gathering all needles, consolidation captures an incomplete haystack → use the A2 min-gather guard and/or design tasks so the write is impossible without the searches.
5. **Prompt-cache invalidation.** Consolidation rewrites the prefix → cache resets at the boundary (cost note; affects the "cache static context" cost lever, not validity).

---

## 5. Deferred / follow-up

- **Multi-cycle consolidation** (matches the abstract's "multiple turns of consolidation"). Extend `ConsolidatingLLMAgent` to re-fire on a context threshold. **Requires** fixing per-cycle *input* (not context %) to avoid the format×input-size confound; structure A1–A4 so this extension is clean.
- **Separate small summarizer model** as a distinct compression knob (currently summarizer = agent model).
- **Token-efficiency-per-format** as a first-class result (does JSON/MD naturally compress to a different realized ratio than prose?).

---

## 6. Suggested build order

1. **A1–A6** — `ConsolidatingLLMAgent` + `create_consolidating_agent` + register (B1–B2). Run against the **existing** airline tasks and **watch a consolidation fire** (E1). *(Prove the mechanism before investing in custom tasks.)*
2. **A7** instrumentation — confirm block + token counts land in `results.json`.
3. **C1, C6, Risk 1** — nail down anchor data and validate the Task A gold action executes (the highest-uncertainty content work).
4. **C2–C5** — author both tasks + density injection.
5. **E2–E3** — ceiling + prose-at-gentle succeed; aggressive compression breaks something (signal check).
6. **D1–D4** — analysis harness + the budget sweep + the ratio curve.
