# @module: aevara.src.memory.checkpoint_serializer
# @deps: json, os, hashlib, pathlib, typing
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Atomic checkpoint serialization engine with SHA256 integrity and schema versioning (Ψ-0).

from __future__ import annotations
import json
import os
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

class CheckpointSerializer:
    """
    Serializador de Checkpoints (Ψ-0).
    Garante persistência atômica, integridade via checksum e suporte a versionamento.
    """
    VERSION = "0.1.0"

    @staticmethod
    def _calculate_checksum(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def serialize_state(cls, state: Dict[str, Any], path: str) -> bool:
        """
        Serializa o estado em JSON de forma atômica (temp + rename).
        Inclui metadata de versão e checksum.
        """
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        envelope = {
            "version": cls.VERSION,
            "timestamp": datetime.now().isoformat(),
            "payload": state
        }
        
        data_str = json.dumps(envelope, indent=2)
        checksum = cls._calculate_checksum(data_str)
        envelope["checksum"] = checksum
        
        final_data = json.dumps(envelope, indent=2)
        
        fd, temp_path = tempfile.mkstemp(dir=str(target_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(final_data)
            os.replace(temp_path, path)
            return True
        except Exception as e:
            if os.path.exists(temp_path): os.remove(temp_path)
            raise e

    @classmethod
    def deserialize_state(cls, path: str) -> Optional[Dict[str, Any]]:
        """
        Carrega e valida o estado do arquivo. Retorna payload se íntegro.
        """
        if not os.path.exists(path): return None
        
        try:
            with open(path, 'r') as f:
                envelope = json.load(f)
            
            # 1. Verificar Checksum
            expected_checksum = envelope.pop("checksum", "")
            data_str = json.dumps(envelope, indent=2)
            if cls._calculate_checksum(data_str) != expected_checksum:
                # Log Critical Integrity Failure (handled by caller)
                return None
                
            return envelope.get("payload")
        except Exception:
            return None
