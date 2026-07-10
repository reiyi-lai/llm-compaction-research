**Beyond Prose Summaries: Evaluating Structured Consolidation Formats for LLM Agent Context Compression**

# 

# **Aim**

To test whether the output format of compressed context (at each consolidation cycle) determines what information survives consolidation and influences reasoning for multi-turn tasks. This would represent a meaningful and underexplored lever for improving long-horizon agent reliability.

# **Hypothesis**

Compression degrades precise information before categorical information, so structured formats (JSON, markdown) should help specifically by pinning down exact identifiers, while showing little advantage for categorical policies that survive prose compression anyway.

# 

# **Abstract**

The compression pipeline can be classified into three layers:

i) Text level,

ii) Token/embedding level (i.e. instead of feeding the model compressed text, we feed it “virtual tokens”), 

iii) KV cache level (i.e. methods like H2O and SnapKV that drop or quantize entries in the model's key-value cache after computation). 

Our paper critically operates at the first layer, and tests what sort of textual format works best for preserving information after multiple turns of consolidation. The text level is model-agnostic and is testable on existing LLMs that agents use like OpenAI’s and Anthropic’s, whereas representation-level methods require gradient access and aren’t production-viable.

We compare three formats – that are varied via the system prompt that determines the output at the end of each consolidation turn.

* **Free-text Prose**: the agent writes a natural language summary of what it attempted, learned, and concluded, i.e. existing representational format.

* **Hierarchical Markdown**: the agent organizes its summary under explicit section headers, with free text content under each heading. This tests whether lightweight structural cues function as attention anchors that help the model locate information.

* **Pure JSON Schema**: the agent’s output must conform to a typed JSON structure with explicit fields for attempted actions, facts learned (typed as file locations, behavioral observations, negative findings), active constraints with their source, outcomes, and unresolved items. This tests whether structural rigidity helps the model’s attention mechanism locate information better.

# **Evaluation Design**

1. ## **Overview**

We vary only the knowledge block format as the experimental variable. This change will be applied via the format-specific system prompt that determines the output when a consolidation cut is made.

* **Free-text Prose**: the agent writes a natural language summary of what it attempted, learned, and concluded. This is Focus’s existing representational format.

* **Hierarchical Markdown**: the agent organizes its summary under explicit section headers, with free text content under each heading. This tests whether lightweight structural cues function as attention anchors that help the model locate information.

* **Pure JSON Schema**: the agent’s output must conform to a typed JSON structure with explicit fields stated. This tests whether structural rigidity helps the model’s attention mechanism locate information better.

2. ## **Benchmark Reference**

Our specific evaluation design follows [τ-bench](https://github.com/sierra-research/tau2-bench) (Yao et al., 2024), where it tests customer service agents handling actionable tasks from a user in multi-turn conversations with relevant tool calls while following a domain-specific policy document.

We adopt τ-bench’s policies, API tool calls, and database-state evaluation, but replace its emergent multi-turn episodes with our own controlled, phase-structured tasks.

We use the τ-airline domain as the primary setting, because airline rules require multi-hop reasoning over gathered information, which would lead to real, measurable failure in the event that critical information is lost during compression.

3. ## **Task Design**

We designed the core task to have sufficient user preferences to warrant a heavy read from the database of flight reservations and a consequent write to the database.

Task: Change flight for existing reservation in Economy (Expected Outcome: Modify)

* User Constraint (two *needles* whose survival through consolidation the study measures):  
  * *Categorical* — the replacement flight must depart after 11:00 EST on the travel date, and be the **cheapest** qualifying option.  
  * *Exact-identifier* — pay any fare difference with the **Visa card ending 7447** (`credit_card_3092185`), **not** the Mastercard that is the reservation's on-file default.  
* Expected Agent Action: Agent issues a single *update\_reservation\_flights* write with the correct flight number, cabin (economy), and `payment_id`.

4. ## **Agent Interaction Flow**

Each episode involves three actors interacting in half-duplex (strictly turn-taking) turns: the **customer-service agent** under test, which reads the database, talks to the user, and commits the final write; the **user simulator**, which plays the customer and delivers the staged multi-turn script; and the **consolidation harness**, which — through a separate summarizer model — compresses the agent’s context into a knowledge block at each cut. The model realizing each role is specified in *Agent Implementation*.

**The agent’s standing context.** Throughout the episode the customer-service agent always has access to:

* its operating instructions,  
* the airline policy document (Appendix A), and  
* the tool definitions (Appendix B).

**The gather–consolidate–act cycle.** The agent alternates two phases, punctuated by consolidation:

* *Gather* — the agent queries the database and responds to the user, issuing read/search tool calls as needed.  
* *Consolidate* — the moment a search/read result lands in context, the harness compresses the accumulated history into a **knowledge block** in the format under test and injects it at the top of context, replacing the raw history. This is the compression event whose format the study varies.  
* *Act* — the agent responds to the user or, at the end, commits a database write, working from the knowledge block plus any fresh reads.

**Multi-Turn Flow**:

The two user constraints defined in **§3 Task Design** are stated by the user in a single opening turn and never repeated. The task is instantiated on a Charlotte (CLT) → Orlando (MCO) reservation (`VAAOXJ`).

Before that target reservation is acted on, the user requests two unrelated flight searches (PHX→LAS, then DFW→SEA) that serve as distraction; each triggers a consolidation cut, so the opening turn — and with it both needles — is re-compressed twice before it is used.

Only at the end is the target trip (CLT→MCO) searched, and that read is deliberately never compacted. 

Full Flow:

| \# | Actor | Turn | Stage |
| ----- | ----- | ----- | ----- |
| 1 | User | States all constraints \+ exact identifiers. States criteria for target flight but defers agent search for it, and asks about another flight instead. | Opening |
| 2 | Agent | Conducts search \#1 by calling read tool calls. | Gather 1 |
| ↳ | Harness | Read result lands → Consolidate into block 1\. | Consolidation |
| 3 | Agent | Reports search \#1 results to the user, from block 1\. | Act (without write) |
| 4 | User | States criteria for second unrelated flight. | — |
| 5 | Agent | Tool calls for search \#2. | Gather 2 |
| ↳ | Harness | Read result lands → *\[Block 1 \+ Gather-2 context\]* consolidated into Block 2\. | Consolidation |
| 6 | Agent | Reports search \#2 to user, from block 2\. | Act (without write) |
| 7 | User | Requests search for target flight based on requirements they stated at the start | — |
| 8 | Agent | Conducts search for the target and proposes the action, applying all constraints found in block 2\. (search results here not compacted) | Gather |
| 9 | User | Confirms the proposed action. | — |
| 10 | Agent | Commits the write action, applying the exact-identifier \+ constraint needles from the block chain. | Act (with Write) |
| ↳ | Harness | Compare final DB state to gold state. | Scoring |

Ultimately, this flow tests whether the requirements stated by the user on their first turn survive repeated rounds of consolidation.

5. ## **Evaluation Metrics**

i) Task Success (i.e. database end state matches gold state)

* Updated to correct flight number  
* Paid for with correct card

ii) Token efficiency

# 

# Agent Implementation

1. ## **Customer Service Agent** 

* LLM Model: gpt-5-mini, temperature: 0.0  
  * gpt-4o-mini kept failing “cheapest flight” condition and picking the first flight after 11:00 instead, reflecting agent reasoning limits – so we upgraded to gpt–5-mini  
* Trials:   
  * k=12 per format at block token budget=900  
  * k=5 per format per token budget when varying block token budget

2. ## **User Simulation Agent**

* LLM Model: gpt-5-mini, temperature 0.0.   
  * gpt-4o-mini could not reliably follow the multi-step, deferral-based instructions (it scrambled the turn order or skipped the intermediate flight lookups) – we upgraded to gpt-5-mini to stage the user conversation reliably.  
* User instructions: \`[user\_scenario.instructions\`](https://github.com/reiyi-lai/llm-compaction-research/blob/main/scratch/task_c_multicut.py)  
* User is simulated by LLM, not manually scripted: [src/tau2/user/user\_simulator.py](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/user/user_simulator.py)

The following is added as a new task to [data/…/domains/airline/tasks.json](https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/tasks.json) to initialize.

TASK\_C \= {  
    "id": "102",  
    "user\_scenario": USER\_SCENARIO,   \# phased multi-step instructions (see Agent Interaction Flow)  
    "initial\_state": {  
        "initialization\_data": {"agent\_data": AGENT\_DATA, "user\_data": None},  
        "initialization\_actions": None, "message\_history": None,  
    },  
    "evaluation\_criteria": {  
    "actions": GOLD\_ACTIONS,          \# VAAOXJ \-\> \[HAT909\] economy, pay credit\_card\_3092185  
    "communicate\_info": \["HAT909"\],  
    "reward\_basis": \["DB", "COMMUNICATE"\],  
    }  
}  
GOLD\_ACTIONS \= \[...  
    {"action\_id": "A\_3", "name": "update\_reservation\_flights",  
     "arguments": {  
         "reservation\_id": "VAAOXJ", "cabin": "economy",  
         "flights": \[{"flight\_number": "HAT909", "date": DATE}\],  
         "payment\_id": "credit\_card\_3092185",  
     }},  
\]

3. ## **Summarizer Agent** 

* Model: gpt-4o-mini, temperature 0.0, decoupled from the agent model  
* Consolidation trigger: Fires the moment the agent’s search/read tool result lands in context.   
* Defined in [src/tau2/agent/consolidating\_agent.py](https://github.com/reiyi-lai/llm-compaction-research/blob/main/src/tau2/agent/consolidating_agent.py)  
* Enable reads always  
  * While the consolidated block becomes the agent’s only memory, the database stays readable to the agent, matching frontier models’ compaction behavior.

* ### Summary Prompt

A single domain and format-agnostic summarization instruction is defined first, adapted from Anthropic's default compaction prompt:

SUMMARIZATION\_INSTRUCTION \= """  
You are given a partial transcript of a task an assistant is working on. Please write a summary ... Write down anything that would be helpful, including the state, decisions made, next steps, learnings, etc. Pay attention to specific quotes/snippets, variable names, identifiers, and exact values where applicable.  
""".strip()

* ### Per Format Prompt

PROSE\_FORMAT       \= "Write the Knowledge block as a concise natural-language narrative, in plain prose paragraphs."

MARKDOWN\_FORMAT    \= "Write ... hierarchical Markdown ... under explicit section headers — '\#\# User Request & Constraints', '\#\# Facts Gathered', '\#\# Active Constraints (with source)', '\#\# Decisions / Current State', '\#\# Unresolved' ..."

JSON\_FORMAT        \= "Return ONLY a JSON object conforming to the provided schema: the user's request and constraints, the facts learned, the decisions made and current state, and any unresolved items."

JSON format is enforced with OpenAI’s strict response\_format, with a schema specified as follows:

{"type": "json\_schema",   
"json\_schema": {"name": "knowledge\_block", "strict": True,  
  "schema": {"type": "object",   
    "additionalProperties": False,  
    "properties": {  
      "user\_request\_and\_constraints": {"type": "array", "items": {"type": "string"}},  
      "facts\_learned":                {"type": "array", "items": {"type": "string"}},  
      "decisions\_and\_state":          {"type": "array", "items": {"type": "string"}},  
      "unresolved":                   {"type": "array", "items": {"type": "string"}}},

    "required": \["user\_request\_and\_constraints", "facts\_learned",  
                 "decisions\_and\_state", "unresolved"\]}}}

The summarizer system prompt is assembled from SUMMARIZATION\_INSTRUCTION, the respective format scaffolding prompt, and “Length budget: {budget}” and for the JSON format, passes the schema as response\_format.

# Appendices

The following can be found in the tau2-bench repository.

A: Airline Policies

* [data/tau2/domains/airline/policy.md](https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/policy.md)

B: Tool Definitions

* [src/tau2/domains/airlines/tools.py](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/domains/airline/tools.py)  
* Passed to the LLM as native function-calling schemas (tools=\[t.openai\_schema …\] in utils/llm\_utils.py:generate())

C: Database

* [data/tau2/domains/airline/db.json](https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/db.json) – contains 300 flights, 500 users, and 2000 reservations

D: Database End State Evaluation Setup  
τ-bench’s native database-state comparison is found in [src/tau2/evaluator/evaluator\_env.py](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/evaluator/evaluator_env.py).

Two environments are built from initialization\_data:

* a predicted environment that replays the agent's full trajectory,  
* a gold environment that applies the task's evaluation\_criteria.actions (i.e. gold state WRITE action).

Their database hashes are compared.

\# compare final DB states by hash (agent trajectory vs. gold)  
agent\_db\_hash          \= gold\_environment.get\_db\_hash()  
predicted\_agent\_db\_hash \= predicted\_environment.get\_db\_hash()

db\_match  \= (agent\_db\_hash \== predicted\_agent\_db\_hash) and (user\_db\_hash \== predicted\_user\_db\_hash)

db\_reward \= 1.0 if db\_match else 0.0

# Evaluation Results

## **Task Success**

| format | Visa card number retained | used Visa card | DB success |
| ----- | ----- | ----- | ----- |
| prose | 3/5 | 3/5 | 60% |
| markdown | 3/5 | 2/5 | 40% |
| json | 5/5 | 5/5 | 100% |

## **Token Efficiency**

| format | Input tokens to Summarizer | Block tokens (out) | Total Cost of Compression Calls ($) | agent input | TOTAL tok | Cost per trial ($) |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| prose | 4,073 | 1,297 | 1.39 | 95,918 | 114,897 | 35.0 |
| markdown | 3,897 | 1,584 | 1.53 | 78,442 | 94,129 | 27.0 |
| json | 2,495 | 730 | 0.81 | 82,273 | 95,876 | 27.7 |

*\*$ in units of 10⁻³* 

| format | $/trial | DB | $ per correct task |
| ----- | ----- | ----- | ----- |
| prose | 35.0 | 60% | 58.4 |
| markdown | 27.0 | 40% | 67.5 |
| json | 27.7 | 100% | 27.7 |

*\*$ in units of 10⁻³* 

## **Token Usage to Success Curve**

| format | DB @ 250 | @ 500 | @ 900 | @ 1500 |
| ----- | ----- | ----- | ----- | ----- |
| prose | 3/5 | 2/5 | 3/5 | 3/5 |
| markdown | 1/5 | 4/5 | 2/5 | 3/5 |
| json | 4/5 | 5/5 | 5/5 | 3/5 |

As the token budget for the knowledge block tightens, the difference becomes stark. At \~250 words, json has a task success rate of 4/5, as opposed to 3/5 with prose and 1/5 with markdown. Under budget pressure, structured formats preserve exact identifiers best.

The results of these trials demonstrate that the format of the compressed context has a compounding effect:

* Task Success: The JSON structured format preserves exact identifiers best across multiple rounds of compression; prose and markdown progressively lose them.

* Token Efficiency: Block generation costs also drop with structured formats, not just for summarizer output costs, but input costs over multiple turns. 

* Structured formats also save on overall agent costs, except that markdown seems to have a slight edge over JSON here.

* In terms of token usage per successful task, the JSON format essentially halves that of the prose compression format.

