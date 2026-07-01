from __future__ import annotations

from typing import Any


def review_locally(
    old_ncm: str,
    suggestion: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    suggested_ncm = suggestion.get("ncm", "")
    suggested_cfop = suggestion.get("cfop", "5102")
    confidence = suggestion.get("confianca", "baixa")
    category = suggestion.get("categoria", "")
    candidate_ncms = {candidate["ncm"] for candidate in candidates}

    requires_human = False
    reasons = ["Revisor local sem custo: validacao deterministica por regras e candidatos NCM."]

    if not suggested_ncm:
        requires_human = True
        reasons.append("Nenhum NCM sugerido pelo motor de regras.")
    elif suggested_ncm not in candidate_ncms:
        requires_human = True
        reasons.append("NCM sugerido nao apareceu entre os candidatos consolidados.")

    if confidence in {"baixa", "sem_classificacao"}:
        requires_human = True
        reasons.append(f"Confianca do motor de regras: {confidence}.")

    if old_ncm and suggested_ncm and old_ncm != suggested_ncm and confidence != "alta":
        requires_human = True
        reasons.append(f"NCM antigo ({old_ncm}) diverge do NCM sugerido ({suggested_ncm}).")

    if suggested_cfop == "5405" and "bebida" not in category and all(
        word not in category for word in ["cerveja", "vinho", "cachaca", "destilado", "agua", "refrigerante"]
    ):
        requires_human = True
        reasons.append("CFOP 5405 sugerido sem categoria claramente vinculada a bebidas.")

    if requires_human:
        reviewer_confidence = "revisar"
    elif confidence == "alta":
        reviewer_confidence = "alta"
    else:
        reviewer_confidence = "media"

    return {
        "cfop_final": suggested_cfop,
        "ncm_final": suggested_ncm,
        "confianca_revisor": reviewer_confidence,
        "motivo_revisor": " ".join(reasons),
        "revisao_humana": requires_human,
    }
