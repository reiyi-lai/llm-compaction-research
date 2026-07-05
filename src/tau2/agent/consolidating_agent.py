"""Context-consolidating agent harness for the compaction-format study.

A single gather->act consolidation: when the rendered context crosses a token
threshold (calibrated to fire at end-of-gather, after the last read result is in
context but before the agent reasons over it), the accumulated Phase-1 history is
compressed into a Knowledge block in a chosen *format* (prose / markdown / json),
the raw history is pruned, and the block is re-injected at the top of context.
Phase 2 (propose -> confirm -> write) then runs from the block alone.

Only the *output format* of the block varies across conditions; the trigger, the
shared (neutral, Anthropic-derived) summarization instruction, and everything
upstream are held constant. See "Implementation Plan.md" for the rationale.
"""

import json
import os
from typing import List, Optional

from litellm import token_counter
from loguru import logger

from tau2.agent.base_agent import ValidAgentInputMessage
from tau2.agent.llm_agent import LLMAgent, LLMAgentState
from tau2.data_model.message import (
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    UserMessage,
)
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate, to_litellm_messages

# --- constant across all three formats: neutral, domain- and needle-agnostic ---
# Adapted directly from Anthropic's default compaction prompt so the shared
# instruction mirrors real production compaction: no format prescription and no
# mention of the specific categories (identifiers/numbers) we later audit.
SUMMARIZATION_INSTRUCTION = """
You are given a partial transcript of a task an assistant is working on. Please write a
summary of the transcript. The purpose of this summary is to provide continuity so the
assistant can continue to make progress towards completing the task in a future context,
where the raw history will not be accessible and will be replaced with this summary.
Write down anything that would be helpful, including the state, decisions made, next steps, learnings, etc.
Pay attention to specific quotes/snippets, variable names, identifiers, and exact values where applicable.
""".strip()

# --- format scaffolding: the experimental variable -----------------------------
PROSE_FORMAT = (
    "Write the Knowledge block as a concise natural-language narrative, in plain "
    "prose paragraphs."
)
MARKDOWN_FORMAT = (
    "Write the Knowledge block as hierarchical Markdown. Organize it under explicit "
    "section headers — at least: '## User Request & Constraints', '## Facts Gathered', "
    "'## Active Constraints (with source)', '## Decisions / Current State', "
    "'## Unresolved' — with free-text content under each heading."
)
JSON_FORMAT = (
    "Return ONLY a JSON object conforming to the provided schema: the user's request "
    "and constraints, the facts learned, the decisions made and current state, and "
    "any unresolved items."
)

# Lean base schema: each field is a flat array of strings. The per-item metadata
# (constraint `source`, fact `type` enum) and the `attempted_actions` log were
# dropped — they added JSON-specific overhead with no prose/markdown analog and no
# decision-relevant content, which crowded out the actual data at low budgets.
JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "knowledge_block",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "user_request_and_constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "facts_learned": {"type": "array", "items": {"type": "string"}},
                "decisions_and_state": {"type": "array", "items": {"type": "string"}},
                "unresolved": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "user_request_and_constraints",
                "facts_learned",
                "decisions_and_state",
                "unresolved",
            ],
        },
    },
}

# --- json_struct: naive JSON schema + a generic, domain-agnostic records
# container that forces data-level granularity. Every compulsory field is
# identical to JSON_SCHEMA; the ONLY difference is the added `structured_records`
# array (each discrete item -> its own object, each attribute -> its own
# key/value pair). This isolates "structure at the data granularity" as the
# variable, without hardcoding any domain terms. Contrast: naive `json` crams
# lists into a free-text observation string; `json_struct` atomizes them.
JSON_STRUCT_FORMAT = (
    "Return ONLY a JSON object conforming to the provided schema: the user's request "
    "and constraints, the facts learned, the decisions made and current state, any "
    "unresolved items, AND `structured_records`. In "
    "`structured_records`, represent each discrete item, record, option, or entity "
    "that is RELEVANT TO THE USER'S TASK (e.g. each candidate option returned by a "
    "lookup the user must choose among) as its OWN object, with each of its attributes "
    "as a separate key/value pair. Do NOT summarize such lists into prose or collapse "
    "them into a single field — give each relevant item its own record. Omit records "
    "that are not pertinent to completing the task."
)

import copy as _copy

JSON_STRUCT_SCHEMA = _copy.deepcopy(JSON_SCHEMA)
JSON_STRUCT_SCHEMA["json_schema"]["name"] = "knowledge_block_struct"
_s = JSON_STRUCT_SCHEMA["json_schema"]["schema"]
_s["properties"]["structured_records"] = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entity_type": {"type": "string"},
            "attributes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            },
        },
        "required": ["entity_type", "attributes"],
    },
}
_s["required"].append("structured_records")

# format -> (scaffolding text, optional response_format for structured output)
CONSOLIDATION_FORMATS = {
    "prose": (PROSE_FORMAT, None),
    "markdown": (MARKDOWN_FORMAT, None),
    "json": (JSON_FORMAT, JSON_SCHEMA),
    "json_struct": (JSON_STRUCT_FORMAT, JSON_STRUCT_SCHEMA),
}

KNOWLEDGE_BLOCK_WRAPPER = """
[CONTEXT COMPACTED] The earlier conversation and tool outputs have been removed to
save context. The Knowledge block below is your persistent memory of everything
gathered so far. Treat it as authoritative and continue assisting the user based on
it and the policy. Do not rely on any information beyond this block and the policy.

<knowledge_block>
{block}
</knowledge_block>
""".strip()

DEFAULT_WRITE_TOOLS = {
    "book_reservation",
    "cancel_reservation",
    "update_reservation_flights",
    "update_reservation_baggages",
    "update_reservation_passengers",
    "send_certificate",
}


class ConsolidatingAgentState(LLMAgentState):
    """LLM agent state plus consolidation bookkeeping (single- or multi-cut)."""

    consolidated: bool = False
    knowledge_block: Optional[str] = None
    pre_consolidation_tokens: Optional[int] = None
    block_tokens: Optional[int] = None
    raw_gather_transcript: Optional[str] = None
    # set True on the turn the agent issues a gather (search) call; the NEXT turn —
    # once that call's result has landed in context — fires the end-of-gather cut.
    pending_gather: bool = False
    # multi-cut: number of cuts taken so far, and the ordered chain of blocks.
    # At cut N the summarizer re-compresses [block N-1] + new activity, so the
    # chain captures the compounding-fidelity signal across re-compressions.
    n_cuts: int = 0
    knowledge_blocks: list = []


def _derive_write_tools(tools: List[Tool]) -> set:
    names = set()
    for t in tools:
        try:
            if getattr(t._func, "__mutates_state__", False):
                names.add(t.name)
        except Exception:
            pass
    return names or set(DEFAULT_WRITE_TOOLS)


class ConsolidatingLLMAgent(LLMAgent[ConsolidatingAgentState]):
    """LLMAgent that performs one format-controlled context consolidation."""

    def __init__(
        self,
        tools: List[Tool],
        domain_policy: str,
        llm: str,
        llm_args: Optional[dict] = None,
        consolidation_format: str = "prose",
        trigger_mode: str = "gather",
        trigger_tokens: int = 7000,
        gather_trigger_tools: Optional[set] = None,
        max_cuts: int = 1,
        summary_budget: str = "at most 250 words",
        summary_max_tokens: int = 1200,
        summarizer_llm: Optional[str] = None,
        write_tool_names: Optional[set] = None,
        phase2_read_access: bool = False,
    ):
        super().__init__(
            tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args
        )
        # The summarizer (compression) model is decoupled from the agent (consumer)
        # model so we can, e.g., hold compression constant while upgrading the agent's
        # reasoning. Defaults to the agent LLM when unset.
        self.summarizer_llm = summarizer_llm or llm
        if consolidation_format not in CONSOLIDATION_FORMATS:
            raise ValueError(
                f"Unknown consolidation_format {consolidation_format!r}; "
                f"expected one of {list(CONSOLIDATION_FORMATS)}"
            )
        self.consolidation_format = consolidation_format
        # Trigger mode:
        #   "gather" (default) -> ONE controlled cut fired the moment a gather (search)
        #      tool result lands, i.e. deterministically at end-of-gather. The token
        #      threshold is NOT used, so it can never pre-empt the cut mid-gather.
        #   "tokens" -> legacy: cut when rendered context crosses trigger_tokens.
        # In both modes the write-backstop remains as a pure safety net.
        self.trigger_mode = trigger_mode
        self.trigger_tokens = trigger_tokens
        # max_cuts=1 -> single-cut (original behavior). >1 -> multi-cut: a new cut
        # fires at each gather boundary until this many have been taken, and each cut
        # re-compresses the previous block plus new activity (a block chain).
        self.max_cuts = max_cuts
        self.gather_trigger_tools = (
            gather_trigger_tools
            if gather_trigger_tools is not None
            else {"search_direct_flight", "search_onestop_flight"}
        )
        self.summary_budget = summary_budget
        self.summary_max_tokens = summary_max_tokens
        self.write_tool_names = (
            write_tool_names if write_tool_names is not None else _derive_write_tools(tools)
        )
        # Phase-2 tool access. Block-only (default): after consolidation the agent
        # keeps WRITE/GENERIC tools but loses READ tools, so it can't re-explore to
        # recover what compression dropped — task success then reflects the block.
        # Set phase2_read_access=True to allow re-exploration (measured as a variable).
        self.phase2_read_access = phase2_read_access
        if phase2_read_access:
            self.act_tools = list(tools)
        else:
            self.act_tools = [
                t
                for t in tools
                if str(getattr(getattr(t, "_func", None), "__tool_type__", "read"))
                not in ("read", "ToolType.READ")
            ]
        # one-off estimate of the tool-schema token cost so our threshold aligns
        # with the provider's reported prompt_tokens (which includes the schemas).
        try:
            schema_text = json.dumps([t.openai_schema for t in tools])
            self._tools_token_estimate = token_counter(model=self.llm, text=schema_text)
        except Exception:
            self._tools_token_estimate = 0

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> ConsolidatingAgentState:
        base = super().get_init_state(message_history)
        return ConsolidatingAgentState(
            system_messages=base.system_messages, messages=base.messages
        )

    # -- token accounting -------------------------------------------------------
    def _context_tokens(self, state: ConsolidatingAgentState) -> int:
        lm = to_litellm_messages(state.system_messages + state.messages)
        return token_counter(model=self.llm, messages=lm) + self._tools_token_estimate

    # -- consolidation ----------------------------------------------------------
    @staticmethod
    def _render_transcript(messages: list) -> str:
        return "\n".join(str(m) for m in messages)

    def _consolidate(self, state: ConsolidatingAgentState) -> None:
        transcript = self._render_transcript(state.messages)
        pre_tokens = self._context_tokens(state)
        scaffold, response_format = CONSOLIDATION_FORMATS[self.consolidation_format]
        system = (
            f"{SUMMARIZATION_INSTRUCTION}\n\n{scaffold}\n\nLength budget: {self.summary_budget}."
        )
        summ_messages = [
            SystemMessage(role="system", content=system),
            UserMessage(
                role="user",
                content=f"Transcript to consolidate:\n\n{transcript}",
            ),
        ]
        kwargs = {"temperature": 0.0, "max_tokens": self.summary_max_tokens}
        if response_format is not None:
            kwargs["response_format"] = response_format
        block_msg = generate(
            model=self.summarizer_llm,
            messages=summ_messages,
            tools=None,
            call_name="consolidation_summary",
            **kwargs,
        )
        block = block_msg.content or ""

        state.raw_gather_transcript = transcript
        state.pre_consolidation_tokens = pre_tokens
        state.knowledge_block = block
        state.block_tokens = token_counter(model=self.llm, text=block)
        state.messages = [
            UserMessage(role="user", content=KNOWLEDGE_BLOCK_WRAPPER.format(block=block))
        ]
        state.consolidated = True
        state.n_cuts += 1
        state.knowledge_blocks = list(state.knowledge_blocks) + [block]
        ratio = state.block_tokens / max(pre_tokens, 1)
        logger.info(
            f"[consolidate:{self.consolidation_format}] cut={state.n_cuts}/{self.max_cuts} "
            f"pre={pre_tokens}tok block={state.block_tokens}tok ratio={ratio:.3f}"
        )
        logger.debug(
            f"[consolidate:{self.consolidation_format}] KNOWLEDGE BLOCK:\n{block}"
        )

    def _has_write_call(self, msg: AssistantMessage) -> bool:
        return any(
            tc.name in self.write_tool_names for tc in (msg.tool_calls or [])
        )

    def _has_gather_call(self, msg: AssistantMessage) -> bool:
        return any(
            tc.name in self.gather_trigger_tools for tc in (msg.tool_calls or [])
        )

    def _call_llm(self, state: ConsolidatingAgentState) -> AssistantMessage:
        # Once consolidated, use act_tools. With reads-on (default) that is the full
        # tool set (ecological: the agent may re-read to recover). Block-only (the
        # contrast arm) drops READ tools so the block alone determines the outcome.
        tools = self.act_tools if state.consolidated else self.tools
        messages = state.system_messages + state.messages
        return generate(
            model=self.llm,
            tools=tools,
            messages=messages,
            call_name="agent_response",
            **self.llm_args,
        )

    def _generate_next_message(
        self, message: ValidAgentInputMessage, state: ConsolidatingAgentState
    ) -> AssistantMessage:
        if isinstance(message, UserMessage) and message.is_audio:
            raise ValueError("User message cannot be audio. Use VoiceLLMAgent instead.")
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)

        # PRIMARY trigger. The incoming `message` has just been appended, so the
        # gather (search) result is now in-scope for the transcript being compacted.
        # Fires up to max_cuts times; each cut re-compresses the prior block + new
        # activity (the block chain lives in state.messages, so it is carried in).
        if state.n_cuts < self.max_cuts:
            if self.trigger_mode == "gather":
                # End-of-gather cut: fire once the result of a gather call has landed.
                if state.pending_gather:
                    self._consolidate(state)
            elif self._context_tokens(state) >= self.trigger_tokens:  # "tokens" mode
                self._consolidate(state)
        state.pending_gather = False  # consumed this turn

        assistant_message = self._call_llm(state)

        # Re-arm the end-of-gather cut for next turn if this turn issued a gather call
        # and we still have cuts remaining.
        if (
            state.n_cuts < self.max_cuts
            and self.trigger_mode == "gather"
            and self._has_gather_call(assistant_message)
        ):
            state.pending_gather = True

        # BACKSTOP (safety net only): a consequential write must never execute on
        # fully un-consolidated history. Fires solely if a write is attempted before
        # ANY cut has happened (e.g. the agent writes without ever gathering).
        if state.n_cuts == 0 and self._has_write_call(assistant_message):
            logger.info(
                "[consolidate] write attempted pre-consolidation; consolidating (backstop)."
            )
            self._consolidate(state)
            assistant_message = self._call_llm(state)

        return assistant_message


# =============================================================================
# FACTORIES
# =============================================================================
def _make_factory(consolidation_format: str):
    def factory(tools, domain_policy, **kwargs):
        # Default trigger mode is the deterministic end-of-gather cut; set
        # TAU2_TRIGGER_MODE=tokens for the legacy token-threshold behavior.
        trigger_mode = os.environ.get("TAU2_TRIGGER_MODE", "gather")
        trigger = int(os.environ.get("TAU2_TRIGGER_TOKENS", 7000))
        gather_env = os.environ.get(
            "TAU2_GATHER_TOOLS", "search_direct_flight,search_onestop_flight"
        )
        gather_tools = {t.strip() for t in gather_env.split(",") if t.strip()}
        # max_cuts=1 -> single-cut; >1 -> multi-cut (compounding-fidelity setup).
        max_cuts = int(os.environ.get("TAU2_MAX_CUTS", 1))
        budget = os.environ.get("TAU2_SUMMARY_BUDGET", "at most 250 words")
        max_toks = int(os.environ.get("TAU2_SUMMARY_MAX_TOKENS", 1200))
        # Hold the summarizer model fixed while varying the agent model, if desired.
        summarizer_llm = os.environ.get("TAU2_SUMMARIZER_LLM") or None
        # Reads-on (ecological) is the default; set TAU2_PHASE2_READS=0 for the
        # block-only contrast arm.
        phase2_reads = os.environ.get("TAU2_PHASE2_READS", "1") in ("1", "true", "True")
        return ConsolidatingLLMAgent(
            tools=tools,
            domain_policy=domain_policy,
            llm=kwargs.get("llm"),
            llm_args=kwargs.get("llm_args"),
            consolidation_format=consolidation_format,
            trigger_mode=trigger_mode,
            trigger_tokens=trigger,
            gather_trigger_tools=gather_tools,
            max_cuts=max_cuts,
            summary_budget=budget,
            summary_max_tokens=max_toks,
            summarizer_llm=summarizer_llm,
            phase2_read_access=phase2_reads,
        )

    return factory


create_consolidate_prose = _make_factory("prose")
create_consolidate_md = _make_factory("markdown")
create_consolidate_json = _make_factory("json")
create_consolidate_json_struct = _make_factory("json_struct")
