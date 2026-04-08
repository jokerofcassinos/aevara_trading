# DISCOVERY PHASE — Director + Strategist
## Context
- Queue: docs/TASK_QUEUE.md
- State: docs/PROJECT_STATE.yaml
- Budget: 3/5 files

## Instructions
1. Read task queue and identify highest-priority pending task
2. Verify all dependencies are resolved
3. Calculate priority score: (Impact*0.35)+(Feasibility*0.25)+(PhaseCompliance*0.20)+(ContextAvail*0.15)+(RegimeAlign*0.05)
4. Assign phase and active profile
5. Generate handoff prompt for next phase
6. DO NOT exceed context budget
7. Output: task_id, phase_assignment, active_profile, handoff_prompt

## Output Format
- task_selection.yaml
- handoff_prompt.md
- state_patch.yaml (advance phase)
- Ready for Architect (DESIGN phase)
