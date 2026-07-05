"""Replace task 102 in airline tasks.json with the current TASK_C (idempotent)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_c_multicut import TASK_C
from tau2.data_model.tasks import Task

TASKS = "/Users/rachellai/tau-bench/tau2-bench/data/tau2/domains/airline/tasks.json"
Task.model_validate(TASK_C)

tasks = json.load(open(TASKS))
idx = next((i for i, t in enumerate(tasks) if t["id"] == "102"), None)
assert idx is not None, "task 102 not found; run install_task_c.py first"
tasks[idx] = TASK_C
json.dump(tasks, open(TASKS, "w"), indent=4)
open(TASKS, "a").write("\n")

reloaded = json.load(open(TASKS))
t102 = next(t for t in reloaded if t["id"] == "102")
Task.model_validate(t102)
# quick sanity: STEP 4 (not 5) is the payoff, and only 2 distractor steps
instr = t102["user_scenario"]["instructions"]["task_instructions"]
print("OK: task 102 updated |", len(reloaded), "tasks")
print("   STEP 4 present:", "STEP 4" in instr, "| STEP 5 present:", "STEP 5" in instr,
      "| STEP 6 present:", "STEP 6" in instr)
print("   distractor routes mentioned:", [r for r in ("PHX", "DFW", "EWR") if r in instr])
