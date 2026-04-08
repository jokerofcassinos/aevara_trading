# AUDIT PHASE — Auditor
## Context
- Task: {{TASK_ID}}
- Files: code.py, test_report.json, PROJECT_STATE.yaml
- KG: docs/KNOWLEDGE_GRAPH.md
- Budget: 4/5 files

## Instructions
1. Read code + test report + current state (max 4 files)
2. Validate state consistency
3. Check knowledge graph for duplicates
4. Generate drift report
5. Output: state_patch.yaml, drift_report.md, kg_update.yaml
6. DO NOT approve if state inconsistent or KG has conflicts

## Output Format
- docs/PROJECT_STATE.yaml (updated)
- docs/KNOWLEDGE_GRAPH.md (updated)
- drift_report.md
- Handoff ready for EVOLUTION phase
