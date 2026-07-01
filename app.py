from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

from candidate_generator import CandidateGenerator
from local_reviewer import review_locally
from ollama_reviewer import check_ollama, review_with_ollama


ROOT = Path(__file__).resolve().parent
RULES_PATH = ROOT / "regras_fiscais.json"
NCM_PATH = ROOT / "Tabela_NCM_Vigente_20260701.json"
WEB_DIR = ROOT / "web"

XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def only_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize(value: Any) -> str:
    text = str(value or "").upper()
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(text_norm: str, phrase: str) -> bool:
    phrase_norm = normalize(phrase)
    if not phrase_norm:
        return False
    return re.search(rf"(?<![A-Z0-9]){re.escape(phrase_norm)}(?![A-Z0-9])", text_norm) is not None


def first_match(text_norm: str, phrases: list[str]) -> str | None:
    for phrase in phrases:
        if contains_phrase(text_norm, phrase):
            return phrase
    return None


def confidence_from_score(score: int, rules: dict[str, Any]) -> str:
    if score >= rules["confianca"]["alta"]["min_score"]:
        return "alta"
    if score >= rules["confianca"]["media"]["min_score"]:
        return "media"
    if score >= rules["confianca"]["baixa"]["min_score"]:
        return "baixa"
    return "sem_classificacao"


def load_rules() -> dict[str, Any]:
    with RULES_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_ncm_index() -> tuple[dict[str, Any], dict[str, str]]:
    with NCM_PATH.open("r", encoding="utf-8-sig") as file:
        payload = json.load(file)

    descriptions: dict[str, str] = {}
    for item in payload.get("Nomenclaturas", []):
        code = only_digits(item.get("Codigo"))
        if len(code) == 8:
            descriptions[code] = item.get("Descricao", "")
    meta = {
        "data_ultima_atualizacao": payload.get("Data_Ultima_Atualizacao_NCM", ""),
        "ato": payload.get("Ato", ""),
        "total_ncms_finais": len(descriptions),
    }
    return meta, descriptions


@dataclass
class SheetData:
    sheet_name: str
    headers: list[str]
    rows: list[list[str]]


def column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref)
    if not letters:
        return 0
    index = 0
    for char in letters.group(0):
        index = index * 26 + ord(char) - 64
    return index - 1


def read_xlsx(data: bytes) -> SheetData:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        names = set(archive.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", XLSX_NS):
                shared_strings.append("".join(t.text or "" for t in item.findall(".//a:t", XLSX_NS)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        first_sheet = workbook.find("a:sheets/a:sheet", REL_NS)
        if first_sheet is None:
            raise ValueError("Nenhuma aba encontrada no arquivo XLSX.")
        sheet_name = first_sheet.attrib.get("name", "Sheet1")
        rel_id = first_sheet.attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ]
        target = rel_map[rel_id]
        if not target.startswith("xl/"):
            target = "xl/" + target

        def cell_value(cell: ET.Element) -> str:
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                return "".join(t.text or "" for t in cell.findall(".//a:t", XLSX_NS))
            value = cell.find("a:v", XLSX_NS)
            if value is None:
                return ""
            raw = value.text or ""
            if cell_type == "s":
                try:
                    return shared_strings[int(raw)]
                except (ValueError, IndexError):
                    return raw
            return raw

        sheet_root = ET.fromstring(archive.read(target))
        rows: list[list[str]] = []
        for row in sheet_root.findall("a:sheetData/a:row", XLSX_NS):
            values: dict[int, str] = {}
            for cell in row.findall("a:c", XLSX_NS):
                values[column_index(cell.attrib.get("r", "A1"))] = cell_value(cell)
            if values:
                rows.append([values.get(index, "") for index in range(max(values) + 1)])

    if not rows:
        raise ValueError("A aba selecionada esta vazia.")
    return SheetData(sheet_name=sheet_name, headers=rows[0], rows=rows[1:])


def find_header(headers: list[str], candidates: list[str]) -> int | None:
    normalized = [normalize(header) for header in headers]
    candidate_norms = [normalize(candidate) for candidate in candidates]
    for candidate in candidate_norms:
        if candidate in normalized:
            return normalized.index(candidate)
    for index, header in enumerate(normalized):
        if any(candidate in header for candidate in candidate_norms):
            return index
    return None


def cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def analyze_row(
    description: str,
    barcode: str,
    old_cfop: str,
    old_ncm: str,
    rules: dict[str, Any],
    ncm_descriptions: dict[str, str],
) -> dict[str, Any]:
    desc_norm = normalize(description)
    old_ncm_digits = only_digits(old_ncm)
    old_ncm_valid = old_ncm_digits in ncm_descriptions
    beverage_block = first_match(desc_norm, rules.get("bloqueios_globais_para_bebida", []))

    candidates: list[dict[str, Any]] = []
    matched_rules: list[dict[str, Any]] = []
    for rule in rules.get("regras", []):
        required = rule.get("frases_obrigatorias_qualquer", [])
        required_match = first_match(desc_norm, required)
        if required and not required_match:
            continue

        blocked_match = first_match(desc_norm, rule.get("palavras_proibidas", []))
        if blocked_match:
            continue
        if rule.get("cfop") == rules["cfop"]["bebidas_em_geral"] and beverage_block:
            continue

        strong_matches = [
            phrase for phrase in rule.get("palavras_fortes", []) if contains_phrase(desc_norm, phrase)
        ]
        accepted_ncms = rule.get("ncm_aceitos", [])
        score = int(rule.get("score_base", 0))
        if old_ncm_digits in accepted_ncms:
            score += int(rule.get("bonus_ncm_antigo_aceito", 0))
        elif old_ncm_digits and old_ncm_valid:
            score -= 10
        score += min(15, len(strong_matches) * 5)

        suggested_ncm = (
            old_ncm_digits
            if old_ncm_digits in accepted_ncms and old_ncm_valid
            else rule.get("ncm_preferencial", "")
        )
        reasons = [rule.get("justificativa", "Regra aplicada.")]
        reasons.append(f"Regra: {rule.get('id')}.")
        if required_match:
            reasons.append(f"Termo decisivo: {required_match}.")
        if strong_matches:
            reasons.append("Reforcos: " + ", ".join(strong_matches[:4]) + ".")
        if old_ncm_digits:
            if old_ncm_digits in accepted_ncms and old_ncm_valid:
                reasons.append(f"NCM antigo vigente: {old_ncm_digits}.")
            elif old_ncm_valid:
                reasons.append(
                    f"NCM antigo vigente, mas fora dos NCMs aceitos pela regra: {old_ncm_digits}."
                )
            else:
                reasons.append(f"NCM antigo nao vigente na tabela atual: {old_ncm_digits}.")

        candidates.append(
            {
                "score": score,
                "priority": int(rule.get("prioridade", 0)),
                "cfop": rule.get("cfop", rules["fallback"]["cfop"]),
                "ncm": suggested_ncm,
                "categoria": rule.get("categoria", ""),
                "justificativa": " ".join(reasons),
            }
        )
        matched_rules.append(rule)

    if candidates:
        ranked = sorted(
            zip(candidates, matched_rules),
            key=lambda item: (item[0]["score"], item[0]["priority"]),
            reverse=True,
        )
        best, best_rule = ranked[0]
        best["confianca"] = confidence_from_score(best["score"], rules)
        best["matched_rule"] = best_rule
        return best

    fallback_ncm = old_ncm_digits if old_ncm_valid else ""
    justification = rules["fallback"]["justificativa"]
    if beverage_block:
        justification += f" Bloqueio global encontrado: {beverage_block}."
    if old_ncm_digits and not old_ncm_valid:
        justification += f" NCM antigo nao vigente: {old_ncm_digits}."
    return {
        "score": 0,
        "priority": 0,
        "cfop": rules["fallback"]["cfop"],
        "ncm": fallback_ncm,
        "categoria": rules["fallback"]["categoria"],
        "confianca": rules["fallback"]["confianca"],
        "justificativa": justification,
        "matched_rule": None,
    }


def analyze_xlsx(data: bytes, filename: str) -> dict[str, Any]:
    rules = load_rules()
    ncm_meta, ncm_descriptions = load_ncm_index()
    candidate_generator = CandidateGenerator(ncm_descriptions, normalize)
    sheet = read_xlsx(data)

    idx_barcode = find_header(sheet.headers, ["Codigo de Barras", "Código de Barras", "CODIGO DE BARRAS"])
    idx_description = find_header(sheet.headers, ["Descricao", "Descrição", "DESCRICAO", "DESCRIÇÃO"])
    idx_cfop = find_header(sheet.headers, ["CFOP", "CFOP antigo", "CFOP(antigo)"])
    idx_ncm = find_header(sheet.headers, ["NCM", "NCM antigo", "NCM(antigo)"])
    if idx_description is None:
        raise ValueError("Nao encontrei a coluna DESCRICAO/DESCRIÇÃO na planilha.")

    analyzed_rows = []
    for row_number, row in enumerate(sheet.rows, start=2):
        description = cell(row, idx_description)
        if not str(description).strip():
            continue
        barcode = cell(row, idx_barcode)
        old_cfop = cell(row, idx_cfop)
        old_ncm = cell(row, idx_ncm)
        suggestion = analyze_row(description, barcode, old_cfop, old_ncm, rules, ncm_descriptions)
        old_ncm_digits = only_digits(old_ncm)
        candidates = candidate_generator.build(
            description=description,
            old_ncm=old_ncm_digits,
            suggestion=suggestion,
            matched_rule=suggestion.get("matched_rule"),
        )
        review = review_locally(old_ncm_digits, suggestion, candidates)
        analyzed_rows.append(
            {
                "linha": row_number,
                "codigo_barras": barcode,
                "descricao": description,
                "cfop_antigo": old_cfop,
                "ncm_antigo": old_ncm_digits,
                "cfop_sugerido": suggestion["cfop"],
                "ncm_sugerido": suggestion["ncm"],
                "categoria": suggestion["categoria"],
                "confianca": suggestion["confianca"],
                "score": suggestion["score"],
                "justificativa": suggestion["justificativa"],
                "candidatos_ncm": candidates,
                "cfop_final": review["cfop_final"],
                "ncm_final": review["ncm_final"],
                "confianca_revisor": review["confianca_revisor"],
                "motivo_revisor": review["motivo_revisor"],
                "revisao_humana": review["revisao_humana"],
                "marcar_falha": False,
            }
        )

    confidence_counts: dict[str, int] = {}
    cfop_counts: dict[str, int] = {}
    review_counts: dict[str, int] = {}
    for row in analyzed_rows:
        confidence_counts[row["confianca"]] = confidence_counts.get(row["confianca"], 0) + 1
        cfop_counts[row["cfop_sugerido"]] = cfop_counts.get(row["cfop_sugerido"], 0) + 1
        review_key = row["confianca_revisor"]
        review_counts[review_key] = review_counts.get(review_key, 0) + 1

    return {
        "arquivo": filename,
        "aba": sheet.sheet_name,
        "total_linhas": len(analyzed_rows),
        "vigencia": ncm_meta,
        "colunas_detectadas": {
            "codigo_barras": sheet.headers[idx_barcode] if idx_barcode is not None else None,
            "descricao": sheet.headers[idx_description],
            "cfop": sheet.headers[idx_cfop] if idx_cfop is not None else None,
            "ncm": sheet.headers[idx_ncm] if idx_ncm is not None else None,
        },
        "resumo": {
            "confianca": confidence_counts,
            "cfop": cfop_counts,
            "revisor_local": review_counts,
            "revisao_humana": sum(1 for row in analyzed_rows if row["revisao_humana"]),
        },
        "modo_revisor": "local_sem_custo",
        "linhas": analyzed_rows,
    }


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/meta":
            rules = load_rules()
            ncm_meta, _ = load_ncm_index()
            self.send_json(
                {
                    "vigencia": ncm_meta,
                    "colunas_saida": rules.get("colunas_saida", []),
                    "total_regras": len(rules.get("regras", [])),
                }
            )
            return
        if parsed.path == "/api/ollama/status":
            query = parse_qs(parsed.query)
            base_url = query.get("base_url", [""])[0]
            model = query.get("model", ["qwen3:8b"])[0]
            self.send_json(check_ollama(base_url=base_url, model=model))
            return

        relative = "index.html" if parsed.path in {"/", ""} else parsed.path.lstrip("/")
        target = (WEB_DIR / relative).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.exists():
            self.send_error(404)
            return
        content_type = "text/html; charset=utf-8"
        if target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        if parsed.path == "/api/ollama/review":
            try:
                payload = json.loads(data.decode("utf-8"))
                result = review_with_ollama(
                    rows=payload.get("linhas", []),
                    base_url=payload.get("base_url"),
                    model=payload.get("model", "qwen3:8b"),
                    timeout=int(payload.get("timeout", 240)),
                )
            except Exception as exc:  # noqa: BLE001 - local app friendly error.
                self.send_json({"ok": False, "erro": str(exc)}, status=400)
                return
            self.send_json(result)
            return
        if parsed.path != "/api/analyze":
            self.send_error(404)
            return
        filename = parse_qs(parsed.query).get("filename", ["planilha.xlsx"])[0]
        try:
            result = analyze_xlsx(data, filename)
        except Exception as exc:  # noqa: BLE001 - expose friendly local-app errors.
            self.send_json({"erro": str(exc)}, status=400)
            return
        self.send_json(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analisador fiscal de produtos.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
