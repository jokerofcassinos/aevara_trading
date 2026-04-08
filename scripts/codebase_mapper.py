# @module: scripts.codebase_mapper
# @deps: os, json, re, datetime, pathlib
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Automated project state discovery tool. Scans headers and code to map implementation progress.

import os
import json
import re
from datetime import datetime
from pathlib import Path

class CodebaseMapper:
    """
    AEVRA Codebase Mapper (v1.0.0).
    Varre o projeto para identificar o estado real dos módulos Ω e Ψ.
    """
    def __init__(self, root_dir: str = "aevara/src"):
        self.root = Path(root_dir)
        self.map_data = {}

    def analyze_file(self, file_path: Path):
        """Analisa um arquivo Python em busca de status e integridade."""
        rel_path = file_path.as_posix()
        module_name = rel_path.replace("/", ".").replace(".py", "")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.map_data[module_name] = {"path": rel_path, "status": "FILE_ERROR", "error": str(e)}
            return

        # 1. Extração de Status via Header
        status_match = re.search(r"# @status:\s*([A-Z0-9_]+)", content)
        declared_status = status_match.group(1) if status_match else "UNDECLARED"

        # 2. Heurística de Skeleton
        is_skeleton = "NotImplementedError" in content or 'pass' in content.replace("#", "")
        # Checagem rude de densidade: se declared IMPLEMENTED mas tem NotImplementedError -> MARK SKELETON
        real_status = declared_status
        if "SKELETON" in declared_status or "CONTRACT" in declared_status:
            real_status = "SKELETON"
        elif declared_status == "IMPLEMENTED" and is_skeleton:
            real_status = "DETACHED_SKELETON"

        self.map_data[module_name] = {
            "path": rel_path,
            "declared_status": declared_status,
            "real_status": real_status,
            "has_doc_placeholder": is_skeleton,
            "last_checked": datetime.now().isoformat()
        }

    def scan(self):
        """Varre recursivamente o diretório raiz."""
        for file_path in self.root.rglob("*.py"):
            if "__init__.py" in file_path.name or "__pycache__" in str(file_path):
                continue
            self.analyze_file(file_path)

    def save(self, output_path: str = "docs/CODEBASE_MAP.json"):
        """Salva o mapa em JSON."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.map_data, f, indent=2)

    def print_report(self):
        """Imprime relatório ASCII."""
        print("\n" + "="*60)
        print(" 🏛️  AEVRA CODEBASE STATUS MAP ")
        print("="*60)
        
        stats = {"IMPLEMENTED": 0, "SKELETON": 0, "UNDECLARED": 0, "BROKEN": 0}
        
        for mod, data in sorted(self.map_data.items()):
            status = data["real_status"]
            icon = "✅" if "IMPLEMENTED" in status else "⚙️" if "SKELETON" in status else "❌"
            print(f"{icon} {mod:<40} | {status}")
            
            if "IMPLEMENTED" in status: stats["IMPLEMENTED"] += 1
            elif "SKELETON" in status or "CONTRACT" in status or "DETACHED" in status: stats["SKELETON"] += 1
            else: stats["UNDECLARED"] += 1

        total = sum(stats.values())
        print("="*60)
        print(f" TOTAL: {total} módulos detectados.")
        print(f" COMPLETO: {stats['IMPLEMENTED']} | SKELETON: {stats['SKELETON']} | OUTROS: {stats['UNDECLARED']}")
        print("="*60 + "\n")

if __name__ == "__main__":
    mapper = CodebaseMapper()
    mapper.scan()
    mapper.save()
    mapper.print_report()
