from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"


def _request_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
    data = None
    method = "GET"
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def normalize_base_url(base_url: str | None) -> str:
    cleaned = (base_url or DEFAULT_OLLAMA_URL).strip().rstrip("/")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "http://" + cleaned
    return cleaned


def check_ollama(base_url: str | None = None, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    url = normalize_base_url(base_url)
    try:
        tags = _request_json(f"{url}/api/tags", timeout=8)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "ok": False,
            "base_url": url,
            "model": model,
            "erro": f"Nao foi possivel conectar ao Ollama: {exc}",
        }

    models = [item.get("name", "") for item in tags.get("models", [])]
    return {
        "ok": model in models,
        "base_url": url,
        "model": model,
        "modelos_disponiveis": models,
        "erro": "" if model in models else f"Modelo {model} nao encontrado no Ollama.",
    }


def build_prompt(rows: list[dict[str, Any]]) -> str:
    compact_rows = []
    for row in rows:
        compact_rows.append(
            {
                "linha": row.get("linha"),
                "descricao": row.get("descricao"),
                "codigo_barras": row.get("codigo_barras"),
                "cfop_antigo": row.get("cfop_antigo"),
                "ncm_antigo": row.get("ncm_antigo"),
                "sugestao_algoritmo": {
                    "cfop": row.get("cfop_sugerido"),
                    "ncm": row.get("ncm_sugerido"),
                    "categoria": row.get("categoria"),
                    "confianca": row.get("confianca"),
                    "justificativa": row.get("justificativa"),
                },
                "candidatos_ncm": [
                    {
                        "ncm": candidate.get("ncm"),
                        "descricao": candidate.get("descricao_oficial"),
                    }
                    for candidate in row.get("candidatos_ncm", [])[:6]
                ],
            }
        )

    return (
        "Voce e um revisor fiscal auxiliar para auditoria interna de produtos no Brasil.\n"
        "Regras obrigatorias:\n"
        "- Use somente os NCMs listados em candidatos_ncm de cada linha.\n"
        "- Nao invente NCM fora da lista.\n"
        "- CFOP permitido: 5102 para produtos gerais; 5405 para bebidas em geral.\n"
        "- Vinagre, alcool de limpeza e gelo nao devem receber CFOP 5405.\n"
        "- Se a descricao for insuficiente ou houver duvida, marque revisao_humana true.\n"
        "- Retorne somente JSON valido, sem markdown, sem explicacao fora do JSON.\n"
        "Formato obrigatorio:\n"
        "{ \"resultados\": [ { \"linha\": 2, \"cfop_ia\": \"5102\", \"ncm_ia\": \"10063021\", "
        "\"confianca_ia\": \"alta|media|baixa\", \"motivo_ia\": \"texto curto\", "
        "\"revisao_humana\": false } ] }\n"
        "Produtos para revisar:\n"
        f"{json.dumps(compact_rows, ensure_ascii=False)}"
    )


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def review_with_ollama(
    rows: list[dict[str, Any]],
    base_url: str | None = None,
    model: str = DEFAULT_MODEL,
    timeout: int = 240,
) -> dict[str, Any]:
    url = normalize_base_url(base_url)
    prompt = build_prompt(rows)
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "options": {
            "temperature": 0,
            "top_p": 0.2,
            "num_ctx": 8192,
        },
    }
    raw = _request_json(f"{url}/api/chat", payload=payload, timeout=timeout)
    content = raw.get("message", {}).get("content", "")
    parsed = _extract_json(content)
    results = parsed.get("resultados", [])
    if not isinstance(results, list):
        raise ValueError("Resposta do Ollama nao contem a lista 'resultados'.")
    return {
        "ok": True,
        "base_url": url,
        "model": model,
        "total": len(results),
        "resultados": results,
    }
