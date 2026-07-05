"""Append Task C (id 102) to airline tasks.json + register in split base."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_c_multicut import TASK_C
from tau2.data_model.tasks import Task

REPO = "/Users/rachellai/tau-bench/tau2-bench"
TASKS = f"{REPO}/data/tau2/domains/airline/tasks.json"
SPLIT = f"{REPO}/data/tau2/domains/airline/split_tasks.json"

Task.model_validate(TASK_C)
existing = json.load(open(TASKS))
assert TASK_C["id"] not in {t["id"] for t in existing}, "Task 102 already present; aborting."

s = open(TASKS).read().rstrip()
assert s.endswith("]")
s = s[:-1].rstrip()
assert s.endswith("}")
obj = "\n".join("    " + ln for ln in json.dumps(TASK_C, indent=4).split("\n"))
open(TASKS, "w").write(s + ",\n" + obj + "\n]\n")

split = json.load(open(SPLIT))
if TASK_C["id"] not in split["base"]:
    split["base"].append(TASK_C["id"])
open(SPLIT, "w").write(json.dumps(split, indent=4) + "\n")

reloaded = json.load(open(TASKS))
assert reloaded[-1]["id"] == "102"
Task.model_validate(reloaded[-1])
print("OK: tasks.json now has", len(reloaded), "tasks; 102 present:",
      "102" in {t["id"] for t in reloaded})
