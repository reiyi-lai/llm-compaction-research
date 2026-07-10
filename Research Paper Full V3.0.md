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

# **Evaluation**

1. ## **Overview**

We vary only the knowledge block format as the experimental variable. This change will be applied via the format-specific system prompt that determines the output when a consolidation cut is made.

* **Free-text Prose**: the agent writes a natural language summary of what it attempted, learned, and concluded. This is Focus’s existing representational format.

* **Hierarchical Markdown**: the agent organizes its summary under explicit section headers, with free text content under each heading. This tests whether lightweight structural cues function as attention anchors that help the model locate information.

* **Pure JSON Schema**: the agent’s output must conform to a typed JSON structure with explicit fields stated. This tests whether structural rigidity helps the model’s attention mechanism locate information better.

2. ## **Benchmark Reference**

Our specific evaluation design follows [τ-bench](https://github.com/sierra-research/tau2-bench) (Yao et al., 2024), where it tests customer service agents handling actionable tasks from a user in multi-turn conversations with relevant tool calls while following a domain-specific policy document.

We adopt τ-bench’s policies, API tool calls, and database-state evaluation, but replace its emergent multi-turn episodes with our own controlled, phase-structured tasks.

We use the τ-airline domain as the primary setting, because airline rules require multi-turn reasoning over gathered information, which would lead to real, measurable failure in the event that critical information is lost during compression.

3. ## **Task Design**

We designed the core task to have sufficient user preferences to warrant a heavy read from the database of flight reservations and a consequent write to the database.

The task is for the agent to change the flight for an existing reservation in Economy Class, subject to the following user constraints:

* **Categorical**: The replacement flight must depart after 11:00 EST on the original flight date, and be the cheapest qualifying option.

* **Exact Identifier**: Pay any fare difference with the Visa card ending 7447, not the Mastercard that is the current reservation’s default.

The expected agent action is an *update\_reservation\_flights* write action, with the correct flight\_number, date, and payment\_id identifiers.

4. ## **Agent Interaction Flow**

Each run involves three agents:

* Customer Service Agent, that talks to the user and can read and write to the database containing flight reservation details

* User Simulator Agent, that plays the customer and delivers the staged multi-turn script

* Summarizer Agent Harness, that compresses the agent’s context into a knowledge block at each cut via a separate summarizer model

The Customer Service Agent has access to the following as its base context:

* Agent’s operating instructions  
* Airline policies (in Appendices)  
* Tool definitions (in Appendices)

The flow alternates **gather** phases with **consolidation** cuts.

**Gather phase**

The customer service agent gathers information from and responds to the user, calling relevant tool calls when necessary.

**Consolidation phase**

The customer service agent calls a separate consolidation agent, which then compresses the conversation’s existing history into a Knowledge block based on a system prompt for the consolidation, and the context is replaced by only this knowledge block.

Every Consolidation phase is triggered at the end of every Gather phase i.e. the moment the customer service agent’s search/read tool result lands in the conversation history, till the set maximum number of Gather turns is reached.

**Act / Write phase**

The customer service agent ends with a Write/Act phase (i.e. commits a database action), based on the Knowledge block and read tool calls.

**Multi-Turn Flow**:

Two conditions, defined in §3 Task Design, are stated by the user in their first turn and never repeated.

The user requests for two more flight searches (PHX→LAS, DFW→SEA) that serve as distraction and trigger a consolidation cut each, so the initial context is re-compressed twice before it is acted on.

The actual trip (CLT→MCO) that requires a write is searched at the end and the read of the flight table is never compacted. 

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

**i. Task Success**

Task success is achieved when the final database state reached by the agent’s trajectory matches the gold database state (Appendix D).

Success requires the final *write* action to i) update the reservation to the correct flight number and ii) charge the fare difference to the correct payment card. A mismatch on either field will return a reward of 0 instead of 1\.

**ii. Identifier Retention in Knowledge Block**

We also record whether the exact payment identifier (the Visa card credit\_card\_3092185, ending 7447\) survives in the final knowledge block, i.e. after both consolidation cuts. 

This identifies what context each format preserves which determines the final *write* action, besides Task Success which is binary and based primarily on the end outcome.

TO DO: Include GOLD\_STATE

**iii. Token Efficiency**

Finally, we measure the token cost of each format, including the summarizer’s block generation cost at every consolidation, and the agent’s execution cost across multiple turns, since the block is re-sent on every subsequent turn.

# 

# Agent Implementation

1. ## **Customer Service Agent** 

The customer-service agent is gpt-5-mini at temperature 0.0. We upgraded to it from gpt-4o-mini, which kept failing the *cheapest-flight* condition — selecting the first flight after 11:00 rather than the cheapest — a reasoning limitation that would have confounded the format comparison. Reads are always enabled: although the consolidated block becomes the agent's only conversational memory, the database remains queryable, matching the compaction behaviour of frontier models. We run k = 12 trials per format at the 900-word block budget, and k = 5 per format at each budget when sweeping the block budget.

2. ## **User Simulation Agent**

The user is simulated by an LLM rather than a hand-scripted sequence ([user\_simulator.py](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/user/user_simulator.py)), also gpt-5-mini at temperature 0.0. As with the agent, gpt-4o-mini proved inadequate — it could not reliably follow the multi-step, deferral-based script, scrambling the turn order or skipping the intermediate flight lookups — so we upgraded to gpt-5-mini to stage the conversation faithfully. The user's instructions are specified in [user\_scenario.instructions](https://github.com/reiyi-lai/llm-compaction-research/blob/main/scratch/task_c_multicut.py).

The following is added as a new task to [data/…/domains/airline/tasks.json](https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/tasks.json) to initialize.

TASK\_C \= {  
    "id": "102",

    "user\_scenario": USER\_SCENARIO,   \# phased multi-step instructions (see Agent Interaction Flow)  
    "initial\_state": {  
        "initialization\_data": {"agent\_data": AGENT\_DATA, "user\_data": None},  
        "initialization\_actions": None, "message\_history": None,  
    },

    "evaluation\_criteria": {  
    "actions": \[...  
    {"action\_id": "A\_3", "name": "update\_reservation\_flights",  
     "arguments": {  
         "reservation\_id": "VAAOXJ", "cabin": "economy",  
         "flights": \[{"flight\_number": "HAT909", "date": DATE}\],  
         "payment\_id": "credit\_card\_3092185",  
     }},  
\],  
    "communicate\_info": \["HAT909"\],  
    "reward\_basis": \["DB", "COMMUNICATE"\],  
    }  
}

3. ## **Summarizer Agent** 

All agent parameters, including the below, are defined in [src/tau2/agent/consolidating\_agent.py](https://github.com/reiyi-lai/llm-compaction-research/blob/main/src/tau2/agent/consolidating_agent.py).

1. **Model**

The summarizer is a separate model from the customer-service agent — gpt-4o-mini at temperature 0.0. Decoupling compression from the consuming agent lets us hold the summarizer (the object of study) fixed while varying the agent's reasoning.

2. **Agent Harness**

The consolidating harness wraps the customer-service agent; its behaviour is set by a few parameters in `consolidating_agent.py`, configured as follows for our experiments. The single experimental variable is `consolidation_format` — `prose`, `markdown`, or `json`; everything else is held fixed. Cuts are scoped to the flight-search calls (`gather_trigger_tools` = {`search_direct_flight`, `search_onestop_flight`}) and run in the default `gather` trigger mode. `max_cuts` is set to 2, so up to two cuts fire — one per distractor search — and each re-compresses the previous block plus the new activity into the next, forming the block chain that the compounding-fidelity design depends on. `phase2_read_access` is enabled (reads-on): after a cut the agent keeps its read tools and may re-query the database, matching production compaction (the block-only contrast arm disables it). The exact cut trigger and the block-length budget (`summary_budget` / `summary_max_tokens`) are detailed in *Consolidation Trigger* and *Length Budget per Block* below.

3. **Consolidation Trigger (to find correct wording: trigger for the summarizer model’s generation of next message i.e. next block?)**

Fires the moment the agent’s search/read tool result lands in context. 

def \_generate\_next\_message(self, message: ValidAgentInputMessage, state: ConsolidatingAgentState) \-\> AssistantMessage:  
	\# PRIMARY trigger. The incoming \`message\` has just been appended, so the  
      \# gather (search) result is now in-scope for the transcript being compacted.  
	if state.n\_cuts \< self.max\_cuts:  
            if self.trigger\_mode \== "gather":  
                \# End-of-gather cut: fire once the result of a gather call has landed.  
                if state.pending\_gather:  
                    self.\_consolidate(state)  
            elif self.\_context\_tokens(state) \>= self.trigger\_tokens:  \# "tokens" mode  
                self.\_consolidate(state)  
        state.pending\_gather \= False  \# consumed this turn

4. ### **Summary Prompt**

A single domain and format-agnostic summarization instruction is defined first, adapted from Anthropic's default compaction prompt:

SUMMARIZATION\_INSTRUCTION \= """  
You are given a partial transcript of a task an assistant is working on. Please write a summary ... Write down anything that would be helpful, including the state, decisions made, next steps, learnings, etc. Pay attention to specific quotes/snippets, variable names, identifiers, and exact values where applicable.  
""".strip()

5. ### **Format-Specific Prompt**

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

6. ### **Length Budget per Block**

Length budget: {budget\_words} is specified at the end of the summarizer system prompt, and combined with SUMMARIZATION\_INSTRUCTION and the respective format-specific prompt above.

# Evaluation Results

## **Table 1: Task Success**

| Format | Visa card number retained in final block | DB success |
| ----- | ----- | ----- |
| prose | 45%  (9/20) | 45%  (9/20) |
| markdown | 85%  (17/20) | 50%  (10/20) |
| json | 95%  (19/20) | 90%  (18/20) |

At 20 trials per format (i.e. k=20) with a 900-word budget set per block generated, the choice of consolidation format produces significant variation in task success.

JSON preserves the identifier in 19 of 20 blocks and leads to the highest success rate in terms of database end state. Prose loses the identifier in more than half of trials. Markdown retains the identifier in 85% of blocks, but achieves only 50% in correct writes. It is observed that Markdown fails more in retaining the categorical identifiers for the correct flight than exact identifiers.

The results unambiguously show that the JSON format achieves the highest success rate in retaining the identifier within the knowledge block, as well as in reasoning over its identifiers to take the correct action.

These results align with our hypothesis: the JSON structured format preserves exact identifiers (i.e. Visa …7447) best across multiple rounds of compression while prose and markdown progressively lose them, while the effect on categorical information (i.e. “cheapest flight after 11:00”) remains similar across formats.

## 

## **Table 2: Token Efficiency**

| Format | Summarizer    in / out | Summarizer $ | Agent in / out | Agent $ | TOTAL tok | TOTAL $ |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| prose | 3,589 / 1,230  | 1.28 | 96,162 / 12,074  | 30.90 | 113,055 | 32.18 |
| mark- down | 3,775 / 1,441 | 1.43 | 101,367 / 13,318 | 33.54 | 119,901 | 34.97 |
| json | 3,012 / 635 | 0.83 | 84,383 / 11,571 | 28.73 | 99,601 | 29.56 |

*\*$ in units of 10⁻³* 

On every metric, JSON emerges as the format with the lowest token cost. This is true not just for summarizer output costs, but agent input costs and summarizer input costs over multiple turns.

Markdown is the most expensive, with its generated blocks being the largest – 1,441 output tokens as compared to JSON’s 635 on average – and are re-sent each turn, pushing agent input to above 101,000 tokens.

| format | $/trial | DB Success | $ per correct task |
| ----- | ----- | ----- | ----- |
| prose | 32.18 | 45% | 71.5 |
| markdown | 34.97 | 50% | 69.9 |
| json | 29.56 | 90% | 32.8 |

*\*$ in units of 10⁻³* 

## In terms of token usage cost per successful task, the JSON format essentially halves that of the prose or markdown format on average.

## **Table 3: Task Success against Token Budget** 

![][image1]

First, JSON’s task success rate rivals the two other formats at every budget and only converges in DB-success rate at a high length budget at 1,500 words.

Second, as the token budget for the knowledge block tightens, JSON’s structured format preserves exact identifiers best. At \~250 words, json has a task success rate of 80%, as opposed to 60% with prose and 20% with markdown. 

# Discussion

In summary, the results of these trials demonstrate that the format of the compressed context has a compounding effect:

* Task Success: The JSON structured format preserves exact identifiers best across multiple rounds of compression; prose and markdown progressively lose them.

* Token Efficiency: Block generation costs also drop with structured formats, not just for summarizer output costs, but input costs over multiple turns. 

* In terms of token usage per successful task, the JSON format essentially halves that of the prose compression format.

# Appendices

**Appendix I: Side by Side Conversation Log by Format**  
**Appendix II: Benchmark References**

The following can be found in the tau2-bench repository.

A: Airline Policies

* [data/tau2/domains/airline/policy.md](https://github.com/sierra-research/tau2-bench/blob/main/data/tau2/domains/airline/policy.md)

B: Tool Definitions

* [src/tau2/domains/airlines/tools.py](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/domains/airline/tools.py)

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

[image1]: <data:image/png;base64,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>