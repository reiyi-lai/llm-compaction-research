**Beyond Prose Summaries: Evaluating Structured Consolidation Formats for LLM Agent Context Compression**

# 

# **Aim**: 

To test whether the output format of compressed context (at each consolidation cycle) determines what information survives consolidation and influences reasoning for multi-turn tasks. This would represent a meaningful and underexplored lever for improving long-horizon agent reliability.

# **Hypothesis**:

Compression degrades precise information before categorical information, so structured formats (JSON, markdown) should help specifically by pinning down exact identifiers, while showing little advantage for categorical policies that survive prose compression anyway.

# **Abstract**:

The compression pipeline can be classified into three layers:

i) Text level,

ii) Token/embedding level (i.e. instead of feeding the model compressed text, we feed it “virtual tokens”), 

iii) KV cache level (i.e. methods like H2O and SnapKV that drop or quantize entries in the model's key-value cache after computation). 

Our paper critically operates at the first layer, and tests what sort of textual format works best for preserving information after multiple turns of consolidation. The text level is model-agnostic and is testable on existing LLMs that agents use like OpenAI’s and Anthropic’s, whereas representation-level methods require gradient access and aren’t production-viable.

We compare three formats – that are varied via the system prompt that determines the output at the end of each consolidation turn.

* **Free-text Prose**: the agent writes a natural language summary of what it attempted, learned, and concluded, i.e. existing representational format.

* **Hierarchical Markdown**: the agent organizes its summary under explicit section headers, with free text content under each heading. This tests whether lightweight structural cues function as attention anchors that help the model locate information.

**Pure JSON Schema**: the agent’s output must conform to a typed JSON structure with explicit fields for attempted actions, facts learned (typed as file locations, behavioral observations, negative findings), active constraints with their source, outcomes, and unresolved items. This tests whether structural rigidity helps the model’s attention mechanism locate information better.

# **Evaluation**

1. ## Overview

We vary only the knowledge block format as the experimental variable. This change will be applied via the system prompt that determines the output when complete\_focus in Focus’ architecture is called.

* **Free-text Prose**: the agent writes a natural language summary of what it attempted, learned, and concluded. This is Focus’s existing representational format.

* **Hierarchical Markdown**: the agent organizes its summary under explicit section headers, with free text content under each heading. This tests whether lightweight structural cues function as attention anchors that help the model locate information.

* **Pure JSON Schema**: the agent’s output must conform to a typed JSON structure with explicit fields for attempted actions, facts learned (typed as file locations, behavioral observations, negative findings), active constraints with their source, outcomes, and unresolved items. This tests whether structural rigidity helps the model’s attention mechanism locate information better.

2. ## Benchmark Reference

Our specific evaluation design follows τ-bench (Yao et al., 2024), where it tests customer service agents handling actionable tasks from a user in multi-turn conversations with relevant tool calls while following a domain-specific policy document.

We adopt τ-bench’s policies, API tool calls, and database-state evaluation, but replace its emergent multi-turn episodes with our own controlled, phase-structured tasks.

We use the τ-airline domain as the primary setting, because airline rules require multi-hop reasoning over gathered information, which would lead to real, measurable failure in the event that critical information is lost during compression.

3. ## Agent Interaction Flow

First, the system prompt contains

* Agent’s operating instructions  
* Airline policies (Appendix A)  
* Tool definitions (Appendix B)

Each agent’s interaction flow is structured into two phases separated by one consolidation turn:

* Opening user turn  
* Phase 1 (gather)  
  * The agent gathers information from the user and from read-only API tools. This produces a large, identifier-dense interaction history.

  * Agent authenticates the user, calls *get\_user\_details, get\_reservation\_details*, and flight-search tools. Scripted user supplies any requested info. Context of these responses along with large read-only API outputs accumulate as interaction history.

* Consolidation:   
  * Fires on reaching the trigger threshold by the harness. 

  * Harness compresses the accumulated Phase-1 history into a persistent Knowledge block in the chosen format, prunes raw history, re-injects the block at top of context.

  * The moment the agent attempts a consequential write (update\_reservation\_flights), the harness intercepts, generates the Knowledge block in the active format from the phase-1 history, prunes the raw history from task start to the boundary, and re-injects the block at the top of context.

* Phase 2 (act)  
  * Agent responds using only the Knowledge block and system prompt \- can respond with text and choose to make a write action.  
  * Policy-required user confirmation turn.  
* Scoring  
  * Compare final database state to expected outcome. Results recorded.

![][image1]

4. ## Task Design

What the task should have:

* Enough phase-1 material to warrant compression — favor compound requests and tasks that force big read outputs.   
  * The paper's Failure 3 ("the agent omits explicit user requests at the beginning of the conversation, hinting at the need for better long-context and memory") is literally your phenomenon, and Task 42 (correct all order addresses \+ conditionally swap the jigsaw) is the template: multiple requirements stated up front, large inventory lookups in the middle, multiple write actions at the end.  
* Constraints/preferences/identifiers front-loaded in phase 1 so they sit on the far side of the consolidation boundary from the phase-2 action that needs them.  
* Unique DB outcome for scoring.

We use two matched airline tasks testing the same request: change the flight for a user’s existing reservation, differing only in the user’s ticket tier/class.

Task A: Either Book flight based on user’s listed criteria, or Change flight for existing reservation in Economy (Expected Outcome: Modify)

* User Constraint: Identify flight after 11:00 EST on \<Date(s)\>.  
  * Keep the same cabin.   
  * Choose the cheapest qualifying option.  
  * Pay any difference with the larger of two certificates first, then the Visa card ending 7447\.  
* Expected Agent Behavior/Action:  
  * Agent checks against policy. Passes.  
  * Agent issues *update\_reservation\_flights* write with correct update to database:  
    * Flight number(s), cabin, and payment composition

Task B: Change flight for existing reservation in Basic Economy (Expected Outcome: Do Not Modify)

* User Constraint: Identify flight after 11:00 EST on \<Date(s)\>.  
  * Keep the same cabin.   
  * Choose the cheapest qualifying option.  
  * Pay any difference with the larger of two certificates first, then the Visa card ending 7447\.  
* Expected Agent Behavior/Action:  
  * Agent checks against policy. Fails.  
  * Agent declines modification, citing the policy (and may explain cancel-and-rebook as an alternative, subject to cancellation rules).  
    * Database unchanged (i.e. no write)

Phase-1 Context/Material  
Aim: To ensure Phase 1 gets large \+ dense

* Scale up legitimate, on-domain, needle-resembling content – NOT generic/off-topic chatter. For example:  
  * Flight search returns \~15 lookalike options (similar numbers, close prices, varied times) instead of 4  
  * Multiple reservations on the account (target ID competes with others)  
  * Fuller payment-method set, more product/flight variants

*Other Task Categories*

* Exact identifier: the one correct replacement flight number among \~10 search results; exact payment-method IDs; reservation ID.

* Numerical / threshold: certificate amounts (which is "larger"), gift-card balance, chosen flight price.

* Policy-triggering fact: cabin class (modifiability — decisive in Task B), membership tier (baggage/refund eligibility), created\_at \+ insurance (cancellation eligibility).

* Negative finding: e.g. "no direct flight after 11:00 EST — only one-stops," established by a phase-1 search; tests re-exploration in phase 2\.

5. ## How Consolidation Stage Works (for each Format)

* Trigger: token threshold enforced by the agent harness, set so it is reached before or at end-of-gather (after all needles gathered, before the first write).   
  * Vary compression ratio accordingly

* Format Enforcement  
  * JSON Schema: via OpenAI API’s forced structured output

* Implementation Variables – aligned with Anthropic compaction beta  
  * Trigger token threshold  
  * Summary prompt (where we vary our formats)  
  * Swappable summarizer model (optional small model summarizer)  
  * Constant: Summarization policy (keep decisions/constraints/state, discard intermediate reasoning/verbose output; keep recent turns)

* Hierarchical Markdown: how?

6. ## Agent Design

* Agent mode: Function Calling (FC), which τ-bench shows consistently outperforms text-formatted ReAct/Act for frontier models.   
* Agent temperature: 0.0  
* User Simulation: manual vs scripted vs simulated  
* Agent Model: TBD  
* Action cap: \~30 agent actions per episode (τ-bench default).  
* Trials: TBD ≥ N per (task × condition)  
  * Pilot to estimate N needed for adequate power

Cost Levers:

- Prompt cache the static context: policies \+ tool definitions  
- Small curated task set  
- ~~Cheap agent \+ user models~~

7. ## Evaluation Metrics

i) Task Completion

- τ-bench’s native reward: r \= r\_action × r\_output ∈ {0,1}, where  
  - r\_action requires the final database to match the ground-truth outcome  
  - r\_output requires the agent's messages to contain required information substrings.

More Evaluation Measures

*Explanation Model for Task Failure:*  
Per-category knowledge retention: 

* For each planted item, check presence/recoverability in the block (regex/substring for exact IDs and numbers; LLM-judge for semantic facts and preferences)   
* → i.e. by-category audit of the information content of the compressed Knowledge block

Failure taxonomy

* Classify reasons for task failure into 5 categories: wrong argument / wrong info / wrong decision / partial resolution   
  * Separate compression-caused failures from unrelated reasoning errors

ii) Token efficiency

**Results**:  
Broad Presentation:

* Report both task success and per-category retention – ratio curve shows where retention gaps become success gaps  
* Identify failure reason by category

- Graph of how much the context was compressed (i.e. Compression Ratio) versus task performance  
  - Considering small LLMs for the compression

Claude: *Compression-ratio curve – sweep compression pressure (haystack size and/or summary budget). Deliverable \= the order and ratio-gaps at which each format starts shedding exact identifiers. Expected results: gentle → all formats succeed; aggressive → all fail; middle band → formats diverge.*

Secondary Variables:

* Per-category retention  
  * regex/substring (exact identifiers, numbers)  
  * LLM-judge / recoverability QA (facts, findings, preferences)  
* Token efficiency (Phase-1 history tokens saved) / Free summarization:  
  * Does JSON / MD naturally compress to a different ratio / better retention-per-token than prose?  
* Needle position (early/middle/late within output)  
  * i.e. Position within a large tool output. Row number in a set index in the returned list: early (e.g. 2/15), middle (8/15), late (13/15).

Validating the Results

* Control (C0) must succeed — non-negotiable baseline.  
* Signal \= differentiation across C1/C2/C3:  
  * All succeed → compression too gentle (no signal) — avoid this regime;  
  * All fail → format irrelevant (valid negative result);  
  * Diverge (e.g. prose degrades, JSON holds) → format effect (hypothesis proven)  
* Graph of compression ratio against task completion

# Appendices

A: Airline Policies

* [https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/policy.md](https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/policy.md)

B: Simulation with tasks from user etc

* tau2: [https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/tasks.json](https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/tasks.json)  
* tau: [https://github.com/sierra-research/tau-bench/blob/main/tau\_bench/envs/airline/tasks.py](https://github.com/sierra-research/tau-bench/blob/main/tau_bench/envs/airline/tasks.py)

C: Tool Definitions / Function Calling

* [https://github.com/sierra-research/tau2-bench/blob/main/tests/test\_domains/test\_airline/test\_tools\_airline.py](https://github.com/sierra-research/tau2-bench/blob/main/tests/test_domains/test_airline/test_tools_airline.py)

D: Database End State Evaluation Setup

* To search/find out from within the repository how this works

# 

# 

# 

# To Do:

Set up agent harness (parameters according to Anthropic compaction beta)

- [ ] Select model: gpt-4o-nano (?)  
      - [ ] Set summary\_prompt  
            - [ ] System prompt to consolidate into markdown format  
            - [ ] System prompt to consolidate into .json schema format  
            - [ ] → OpenAI Structured output for .json format?

Validation

- [ ] That consolidation is triggered correctly  
- [ ] Confirm that agent violates constraint on consolidation under Control  
- [ ] How to show the intermediate history/compression/tokens

[image1]: <data:image/png;base64,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>