"""Task C: multi-cut compounding-fidelity task (Design B).

Two needles stated ONCE in phase 0 and never repeated:
  - exact-id : pay with Visa credit_card_3092185 (7447), NOT the Mastercard 1052991
               (the Mastercard is VAAOXJ's payment_history default -> a live distractor)
  - categorical: new flight must depart AFTER 11:00 and be the CHEAPEST such option

Two distractor searches (steps 2-3) each trigger a consolidation cut, so the needles are
re-compressed 2x before the payoff. Trip-1 (CLT->MCO) is NOT searched until step 4 -> the
flight table is fetched FRESH, so payoff correctness depends purely on whether the needles
survived the block chain. Run with TAU2_MAX_CUTS=2 (== # distractor searches, so the
payoff search does NOT trigger a 3rd cut that would compress the fresh table), reads-on.

Overlay = Task A's (HAT900-914 on 2024-05-24, VAAOXJ single economy segment). lei_rossi
already carries both cards in the base DB.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_a_overlay import AGENT_DATA, GOLD_ACTIONS  # reuse trip-1 overlay + gold shape

USER_SCENARIO = {
    "persona": None,
    "instructions": {
        "domain": "airline",
        "reason_for_call": (
            "You are reorganizing several of your trips. Your main goal is to move your "
            "one-way Charlotte (CLT) to Orlando (MCO) reservation on 2024-05-24 to a later "
            "flight, but first you want the agent to look up options for a few other trips."
        ),
        "known_info": (
            "Your user id is 'lei_rossi_3206'.\n"
            "Your reservations include: CLT->MCO on 2024-05-24 (id VAAOXJ), a PHX->LAS trip "
            "(id J7M7UY, 2024-05-20), a DFW->SEA trip (id QF32KM, 2024-05-21), and an "
            "EWR->CLT trip (id ZKTY6N, 2024-05-20)."
        ),
        "unknown_info": (
            "You do not know flight numbers, times, or prices for any trip — the agent must "
            "look them up."
        ),
        "task_instructions": (
            "Follow this conversation order EXACTLY. State your requirements only ONCE, in "
            "step 1, and do NOT restate them afterward.\n\n"
            "STEP 1 (say all of this up front, once, in a single message):\n"
            "'I'm reorganizing a few trips today. Later on I'll want to change my Charlotte (CLT) "
            "to Orlando (MCO) reservation (VAAOXJ) to the cheapest flight that departs after "
            "11:00 AM that same day, and pay any fare difference with my Visa card ending 7447 "
            "— but please do NOT look that one up or change it yet. First, help me with some "
            "other trips. To start, what are the available flights for my PHX to LAS trip "
            "(J7M7UY) on May 20?'\n"
            "Give your user id if asked. Do NOT let the agent look up or touch the CLT->MCO "
            "reservation yet — if it tries, say 'not yet, let's do the other trips first.' Let "
            "the agent search PHX->LAS and list options; then say 'thanks, noted.'\n\n"
            "STEP 2: 'Next, show me options for my DFW to SEA trip (QF32KM) on May 21.' Let the "
            "agent search and list options; say 'got it, thanks.'\n\n"
            "STEP 3: 'Great, now let's do the main one — change my Charlotte to Orlando "
            "reservation based on the requirements I gave you at the start.' Let the agent "
            "search CLT->MCO and PROPOSE a specific flight. When it proposes one and tells you "
            "the fare difference, confirm you want that flight. Do NOT restate your rules — the "
            "agent should remember them.\n\n"
            "STEP 4: When the agent asks how to pay / confirms the payment method, say 'yes, go "
            "ahead' and let the agent ACTUALLY MAKE the change. WAIT for the agent to confirm "
            "the reservation has been updated before you end the conversation — do NOT end on "
            "the same turn as your confirmation. Do NOT re-specify the card unless the agent "
            "proposes the WRONG card, in which case briefly correct it.\n\n"
            "Throughout: be concise; never re-explain your requirements after step 1."
        ),
    },
}

EVALUATION_CRITERIA = {
    "actions": GOLD_ACTIONS,  # VAAOXJ -> [HAT909] economy, pay credit_card_3092185
    "communicate_info": ["HAT909"],
    "nl_assertions": [
        "Agent changes reservation VAAOXJ to flight HAT909 (the cheapest flight departing after 11:00 EST on 2024-05-24).",
        "Agent pays the fare difference with the Visa card ending 7447 (credit_card_3092185), not the Mastercard.",
    ],
    "reward_basis": ["DB", "COMMUNICATE"],
}

TASK_C = {
    "id": "102",
    "description": {
        "purpose": "Multi-cut compounding-fidelity task: two needles (exact-id payment card + "
        "categorical after-11/cheapest) stated once, survive 2 consolidation cuts, applied on "
        "fresh trip-1 data at payoff. Tests whether structured consolidation retains exact "
        "identifiers through repeated re-compression better than prose.",
        "relevant_policies": "List action details and obtain confirmation before update; single card for flight change.",
        "notes": "Run with TAU2_MAX_CUTS=2, reads-on. Distractor searches (steps 2-3) trigger cuts 1-2.",
    },
    "user_scenario": USER_SCENARIO,
    "initial_state": {
        "initialization_data": {"agent_data": AGENT_DATA, "user_data": None},
        "initialization_actions": None,
        "message_history": None,
    },
    "evaluation_criteria": EVALUATION_CRITERIA,
    "annotations": None,
}

if __name__ == "__main__":
    from tau2.data_model.tasks import Task
    t = Task.model_validate(TASK_C)
    print("VALID Task id=%s" % t.id)
    print("communicate_info:", t.evaluation_criteria.communicate_info)
    print("n gold actions:", len(t.evaluation_criteria.actions))
    print("gold payment_id:", t.evaluation_criteria.actions[0].arguments.get("payment_id"))
