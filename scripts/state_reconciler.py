# @module: STATE_RECONCILER
# @deps: PROJECT_STATE.yaml, TASK_QUEUE.md
# @status: INITIALIZED
# @last_update: 2026-04-06
# @summary: Reconstrutor de estado - varre headers e reconstrui PROJECT_STATE.yaml se corrompido

import yaml
import os
import re
from pathlib import Path
from datetime import datetime


def scan_headers(base_dir: str) -> dict:
    """Scan all files for @module headers and reconstruct state."""
    state = {
        "metadata": {
            "project": "AEVRA",
            "reconstructed": True,
            "reconstruction_time": datetime.now().isoformat(),
        },
        "modules": {},
    }

    for root, dirs, files in os.walk(base_dir):
        for fname in files:
            if fname.endswith((".py", ".yaml", ".yml", ".md")):
                fpath = os.path.join(root, fname)
                module_name = None
                module_status = None

                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read(2000)

                    # Extract @module
                    mod_match = re.search(r"#\s*@module:\s*(.+)", content)
                    if mod_match:
                        module_name = mod_match.group(1).strip()

                    # Extract @status
                    status_match = re.search(r"#\s*@status:\s*(.+)", content)
                    if status_match:
                        module_status = status_match.group(1).strip()

                    if module_name:
                        state["modules"][module_name] = {
                            "file": fpath,
                            "status": module_status or "UNKNOWN",
                        }
                except Exception:
                    continue

        return state


def rebuild_state_yaml(base_dir: str, output_path: str):
    """Rebuild PROJECT_STATE.yaml from scanned headers."""
    state = scan_headers(base_dir)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(state, f, default_flow_style=False, allow_unicode=True)
    print(f"[STATE_RECONCILER] State rebuilt from headers: {output_path}")


if __name__ == "__main__":
    import sys

    base = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output = os.path.join(base, "docs", "PROJECT_STATE.yaml")
    rebuild_state_yaml(base, output)
