# @module: QROE_ROUTER
# @deps: PROJECT_STATE.yaml, TASK_QUEUE.md, profiles/*.yaml
# @status: INITIALIZED
# @last_update: 2026-04-06
# @summary: Motor de colapso de decisao e roteamento de tarefas do QROE
# Priority(task) = (Impact*0.35) + (Feasibility*0.25) + (PhaseCompliance*0.20) + (ContextAvail*0.15) + (RegimeAlign*0.05)

import yaml
import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Task:
    task_id: str
    status: str
    priority: float
    phase: str
    dependencies: List[str]
    deliverables: str
    assigned: str


@dataclass
class PriorityResult:
    task_id: str
    phase: str
    profile: str
    priority_score: float


PHASE_PROFILE_MAP = {
    "DISCOVERY": ["Director", "Strategist"],
    "DESIGN": ["Architect"],
    "VALIDATION": ["Tester", "RiskOfficer"],
    "EXECUTION": ["Coder", "PhantomEngineer"],
    "AUDIT": ["Auditor"],
    "EVOLUTION": ["Strategist", "Director"],
}

PHASE_SEQUENCE = ["DISCOVERY", "DESIGN", "VALIDATION", "EXECUTION", "AUDIT", "EVOLUTION"]


def parse_task_queue(queue_path: str) -> List[Task]:
    """Parse TASK_QUEUE.md and return list of pending tasks with deps."""
    tasks = []
    current_task = {}
    in_task = False

    with open(queue_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("### T-"):
                if current_task and current_task.get("task_id"):
                    tasks.append(Task(**{k: current_task.get(k, "") for k in Task.__dataclass_fields__}))
                current_task = {
                    "task_id": line.split(":")[0].replace("### ", ""),
                    "status": "PENDING",
                    "priority": 0.0,
                    "phase": "DISCOVERY",
                    "dependencies": [],
                    "deliverables": "",
                    "assigned": "",
                }
                in_task = True
            elif in_task and "- **" in line and ":" in line:
                key_val = line.split(":", 1)
                if len(key_val) == 2:
                    key = key_val[0].replace("- **", "").replace("**", "").strip().lower()
                    val = key_val[1].strip()
                    if key == "status":
                        current_task["status"] = val.strip("[] ")
                    elif key == "priority":
                        try:
                            current_task["priority"] = float(val)
                        except ValueError:
                            current_task["priority"] = 0.0
                    elif key == "phase":
                        current_task["phase"] = val
                    elif key == "dependencies":
                        if val.lower() == "none":
                            current_task["dependencies"] = []
                        else:
                            current_task["dependencies"] = [d.strip().split("(")[0].strip() for d in val.split(",")]
                    elif key == "assigned":
                        current_task["assigned"] = val
        if current_task and current_task.get("task_id"):
            tasks.append(Task(**{k: current_task.get(k, "") for k in Task.__dataclass_fields__}))

    return tasks


def calculate_priority_score(task: Task, context_budget: int = 5, completed_tasks: set = None) -> float:
    """
    Priority(task) = (Impact*0.35) + (Feasibility*0.25) + (PhaseCompliance*0.20) +
                     (ContextAvail*0.15) + (RegimeAlign*0.05)
    """
    completed = completed_tasks or set()

    # Impact: based on priority level from queue
    impact = task.priority

    # Feasibility: all deps resolved?
    deps_resolved = all(dep in completed for dep in task.dependencies) if task.dependencies else True
    feasibility = 1.0 if deps_resolved else 0.0

    # Phase compliance: task is in active phase
    phase_compliance = 1.0 if task.phase == "DISCOVERY" else 0.8

    # Context availability: simplified (assume budget available at boot)
    context_availability = min(1.0, context_budget / 5)

    # Regime alignment: default 1.0 (no regime data at boot)
    regime_alignment = 1.0

    return (
        impact * 0.35
        + feasibility * 0.25
        + phase_compliance * 0.20
        + context_availability * 0.15
        + regime_alignment * 0.05
    )


def get_active_profiles(phase: str) -> List[str]:
    """Return active profiles for given phase."""
    return PHASE_PROFILE_MAP.get(phase, ["Director"])


def get_next_phase(current_phase: str) -> str:
    """Return next phase in sequence."""
    idx = PHASE_SEQUENCE.index(current_phase) if current_phase in PHASE_SEQUENCE else 0
    return PHASE_SEQUENCE[(idx + 1) % len(PHASE_SEQUENCE)]


def select_next_task(state_path: str, queue_path: str) -> Optional[PriorityResult]:
    """Select highest priority task that has all dependencies resolved."""
    tasks = parse_task_queue(queue_path)

    with open(state_path, "r", encoding="utf-8") as f:
        state = yaml.safe_load(f)

    # Get completed tasks from state
    completed = set()
    for module_name, module_data in state.get("modules", {}).items():
        if module_data.get("status") == "IMPLEMENTED":
            completed.add(module_name.upper().replace("_", "-"))

    # Filter pending tasks
    pending = [t for t in tasks if t.status in ("PENDING", "IN_PROGRESS")]

    if not pending:
        return None

    # Calculate scores and sort
    scored = []
    for task in pending:
        score = calculate_priority_score(task, completed_tasks=completed)
        scored.append((task, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    best_task, best_score = scored[0]

    # Get active profiles for this task's phase
    profiles = get_active_profiles(best_task.phase)
    active_profile = profiles[0] if profiles else "Director"

    return PriorityResult(
        task_id=best_task.task_id,
        phase=best_task.phase,
        profile=active_profile,
        priority_score=best_score,
    )


if __name__ == "__main__":
    import sys

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_path = os.path.join(base_dir, "docs", "PROJECT_STATE.yaml")
    queue_path = os.path.join(base_dir, "docs", "TASK_QUEUE.md")

    if "--read-state" in sys.argv:
        result = select_next_task(state_path, queue_path)
        if result:
            print(f"NEXT_TASK={result.task_id}")
            print(f"PHASE={result.phase}")
            print(f"PROFILE={result.profile}")
            print(f"SCORE={result.priority_score:.4f}")
