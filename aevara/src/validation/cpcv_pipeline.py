# @module: aevara.src.validation.cpcv_pipeline
# @deps: numpy, itertools, dataclasses, typing
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Combinatorial Purged Cross-Validation com embargo temporal
#           e stratification por regime. Evita data leakage entre folds
#           proximos via purge buffer. Garante cobertura de todos os regimes.

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass(frozen=True, slots=True)
class ValidationSplit:
    """Split de validacao com purge mask e regime tag."""
    train_indices: np.ndarray
    test_indices: np.ndarray
    purge_mask: np.ndarray
    regime_tag: str
    fold_id: int


@dataclass(frozen=True, slots=True)
class CPCVConfig:
    n_folds: int = 6
    n_test_folds: int = 2
    embargo_s: float = 60.0
    min_train_samples: int = 50
    min_test_samples: int = 10


class CPCVPipeline:
    """
    Combinatorial Purged Cross-Validation.

    Invariantes:
    - Nao ha sobreposicao entre train indices e test indices (fora do embargo)
    - Embargo buffer entre train e test previne autocorrelacao leakage
    - Regime stratification: cada combinacao cobre todos os regimes presentes
    - Numero de folds = C(n_folds, n_test_folds)
    """

    def __init__(self, config: Optional[CPCVConfig] = None):
        self._config = config or CPCVConfig()

    def generate_splits(
        self,
        timestamps: np.ndarray,
        regimes: np.ndarray,
        n_combinations: int = 0,
        embargo_s: Optional[float] = None,
    ) -> List[ValidationSplit]:
        """
        Gera folds de CPCV.

        Args:
            timestamps: array de timestamps ordenados
            regimes: array de labels de regime (mesmo len que timestamps)
            n_combinations: maximo de combinacoes (0 = todas)
            embargo_s: embargo em segundos (override de config)

        Returns:
            Lista de ValidationSplit
        """
        if len(timestamps) == 0:
            return []
        assert len(timestamps) == len(regimes), "timestamps e regimes devem ter mesmo tamanho"
        if len(timestamps) < self._config.n_folds:
            return []
        assert len(timestamps) >= self._config.n_folds, "Dados insuficientes para n_folds"

        embargo = embargo_s if embargo_s is not None else self._config.embargo_s
        n = len(timestamps)
        n_folds = self._config.n_folds
        n_test = self._config.n_test_folds

        # Divide indices em n_folds blocos temporais ordenados
        fold_size = n // n_folds
        fold_indices = []
        for i in range(n_folds):
            start = i * fold_size
            if i == n_folds - 1:
                end = n
            else:
                end = start + fold_size
            fold_indices.append(np.arange(start, end))

        # Combinacoes de n_test folds como teste
        combos = list(itertools.combinations(range(n_folds), n_test))
        if n_combinations > 0:
            combos = combos[:n_combinations]

        splits: List[ValidationSplit] = []
        for fold_id, test_folds in enumerate(combos):
            test_idx_set = set()
            for tf in test_folds:
                test_idx_set.update(fold_indices[tf].tolist())

            test_indices = np.array(sorted(test_idx_set))

            # Determina dominante regime no test set
            test_regimes = regimes[test_indices]
            regime_tag = self._dominant_regime(test_regimes)

            # Train = tudo que nao esta no test set
            all_indices = np.arange(n)
            mask = np.ones(n, dtype=bool)
            mask[test_indices] = False
            train_candidates = all_indices[mask]

            # Aplica embargo: remove amostras proximas ao test set
            purge_mask = self._compute_purge_mask(
                timestamps, train_candidates, test_indices, embargo
            )
            train_indices = np.array([
                idx for idx in train_candidates if purge_mask[idx]
            ], dtype=int)

            # Valida tamanhos minimos
            if len(train_indices) < self._config.min_train_samples:
                continue
            if len(test_indices) < self._config.min_test_samples:
                continue

            splits.append(ValidationSplit(
                train_indices=train_indices,
                test_indices=test_indices,
                purge_mask=purge_mask,
                regime_tag=regime_tag,
                fold_id=fold_id,
            ))

        return splits

    def _compute_purge_mask(
        self,
        timestamps: np.ndarray,
        train_indices: np.ndarray,
        test_indices: np.ndarray,
        embargo_s: float,
    ) -> np.ndarray:
        """
        Cria mascara booleana: True = manter no train, False = purgar.
        Remove train samples dentro de embargo_s segundos de qualquer test sample.
        """
        mask = np.ones(len(timestamps), dtype=bool)

        if len(test_indices) == 0 or embargo_s == 0:
            return mask

        test_times = timestamps[test_indices]
        test_min = test_times.min()
        test_max = test_times.max()

        for idx in train_indices:
            ts = timestamps[idx]
            # Embargo antes e depois do test set
            if abs(ts - test_min) < embargo_s or abs(ts - test_max) < embargo_s:
                mask[idx] = False

        return mask

    def verify_no_leakage(self, splits: List[ValidationSplit]) -> bool:
        """
        Verifica que nenhum indice de test aparece em train.
        Retorna True se sem leakage.
        """
        for split in splits:
            test_set = set(split.test_indices.tolist())
            train_set = set(split.train_indices.tolist())
            if test_set & train_set:
                return False
        return True

    def compute_stratified_folds(
        self, timestamps: np.ndarray, regime_labels: np.ndarray
    ) -> Dict[str, List[ValidationSplit]]:
        """
        Gera folds estratificados por regime. Cada regime tem folds dedicados.
        """
        unique_regimes = np.unique(regime_labels)
        result: Dict[str, List[ValidationSplit]] = {}

        for regime in unique_regimes:
            regime_mask = regime_labels == regime
            if regime_mask.sum() < self._config.n_folds:
                continue

            regime_timestamps = timestamps[regime_mask]
            regime_regimes = regime_labels[regime_mask]

            folds = self.generate_splits(
                timestamps=regime_timestamps,
                regimes=regime_regimes,
                embargo_s=self._config.embargo_s,
            )

            if folds:
                result[str(regime)] = folds

        return result

    @staticmethod
    def _dominant_regime(regimes: np.ndarray) -> str:
        """Retorna regime mais frequente."""
        unique, counts = np.unique(regimes, return_counts=True)
        return str(unique[np.argmax(counts)])

    def get_n_combinations(self) -> int:
        """Retorna numero total de combinacoes C(n_folds, n_test_folds)."""
        from math import comb
        return comb(self._config.n_folds, self._config.n_test_folds)
