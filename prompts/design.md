# DESIGN PHASE — Architect
## Context
- Task: {{TASK_ID}}
- Contract: docs/CONTRACT_{{TASK_ID}}.md (if exists)
- State: docs/PROJECT_STATE.yaml
- Budget: 3/5 files

## Instructions
1. Read selected task + dependencies (max 3 files)
2. Design contract with explicit I/O schema
3. Map dependency graph (DAG)
4. Identify invariant constraints (Phi0-Phi12)
5. Generate gate checklist for G1-G4
6. DO NOT hardcode thresholds — all params mutaveis via DNA
7. Output: contract.md, deps_graph.yaml, gate_checklist.md

## Output Format
- docs/CONTRACT_{{TASK_ID}}.md
- deps_graph.yaml
- gate_checklist.md
- Ready for EXECUTION phase
