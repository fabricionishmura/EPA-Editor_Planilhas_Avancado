from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


STOPWORDS = {
    "COM",
    "SEM",
    "PARA",
    "POR",
    "DOS",
    "DAS",
    "UMA",
    "UM",
    "UN",
    "UND",
    "PCT",
    "KG",
    "LT",
    "ML",
    "G",
    "DE",
    "DA",
    "DO",
    "E",
    "A",
    "O",
}


class CandidateGenerator:
    def __init__(self, ncm_descriptions: dict[str, str], normalizer):
        self.ncm_descriptions = ncm_descriptions
        self.normalizer = normalizer
        self.index: dict[str, set[str]] = defaultdict(set)
        for ncm, description in ncm_descriptions.items():
            for token in self._tokens(description):
                self.index[token].add(ncm)

    def _tokens(self, value: str) -> list[str]:
        normalized = self.normalizer(value)
        tokens = []
        for token in normalized.split():
            if len(token) < 4:
                continue
            if token in STOPWORDS:
                continue
            if token.isdigit():
                continue
            tokens.append(token)
        return tokens

    def build(
        self,
        description: str,
        old_ncm: str,
        suggestion: dict[str, Any],
        matched_rule: dict[str, Any] | None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        scores: Counter[str] = Counter()
        reasons: dict[str, list[str]] = defaultdict(list)

        def add(ncm: str, points: int, reason: str) -> None:
            if not ncm or ncm not in self.ncm_descriptions:
                return
            scores[ncm] += points
            reasons[ncm].append(reason)

        add(suggestion.get("ncm", ""), 80, "NCM sugerido pelo motor de regras.")
        add(old_ncm, 60, "NCM antigo vigente na tabela atual.")

        if matched_rule:
            for ncm in matched_rule.get("ncm_aceitos", []):
                add(ncm, 45, f"NCM aceito pela regra {matched_rule.get('id')}.")
            add(matched_rule.get("ncm_preferencial", ""), 65, "NCM preferencial da regra aplicada.")

        for token in self._tokens(description):
            for ncm in self.index.get(token, set()):
                scores[ncm] += 3
                if len(reasons[ncm]) < 4:
                    reasons[ncm].append(f"Termo da descricao oficial encontrado: {token}.")

        ranked = []
        for ncm, score in scores.most_common(limit):
            ranked.append(
                {
                    "ncm": ncm,
                    "descricao_oficial": self.ncm_descriptions.get(ncm, ""),
                    "score": score,
                    "motivos": reasons[ncm][:5],
                }
            )
        return ranked
