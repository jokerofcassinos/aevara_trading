# EXECUTION PHASE — Coder + PhantomEngineer
## Context
- Task: {{TASK_ID}}
- Contract: docs/CONTRACT_{{TASK_ID}}.md
- State: docs/PROJECT_STATE.yaml
- Budget: 3/5 files

## Instructions
1. Read contract + dependencies (max 3 files)
2. Implement code + tests + headers + MODULE_SUMMARY.md
3. Run PhantomEngineer simulation (async, non-blocking)
4. Output: code, tests, phantom_gradients, state_patch
5. DO NOT exceed context budget. DO NOT hardcode thresholds.
6. Validate against G1 (Schema) & G3 (Coherence) before handoff.

## Output Format
- Code file with @module header
- tests/ directory with 3+ test types
- phantom_gradients.yaml
- state_patch.yaml
- Handoff ready for Auditor
