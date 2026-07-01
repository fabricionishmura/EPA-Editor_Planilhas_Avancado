const state = {
  file: null,
  result: null,
  failed: new Set(),
};

const els = {
  vigenciaStatus: document.querySelector("#vigenciaStatus"),
  atoStatus: document.querySelector("#atoStatus"),
  fileInput: document.querySelector("#fileInput"),
  fileName: document.querySelector("#fileName"),
  analyzeButton: document.querySelector("#analyzeButton"),
  statusPanel: document.querySelector("#statusPanel"),
  statusText: document.querySelector("#statusText"),
  summary: document.querySelector("#summary"),
  totalRows: document.querySelector("#totalRows"),
  cfop5405: document.querySelector("#cfop5405"),
  highConfidence: document.querySelector("#highConfidence"),
  humanReview: document.querySelector("#humanReview"),
  failedCount: document.querySelector("#failedCount"),
  tableSection: document.querySelector("#tableSection"),
  ollamaPanel: document.querySelector("#ollamaPanel"),
  ollamaUrl: document.querySelector("#ollamaUrl"),
  ollamaModel: document.querySelector("#ollamaModel"),
  ollamaBatch: document.querySelector("#ollamaBatch"),
  testOllamaButton: document.querySelector("#testOllamaButton"),
  reviewOllamaButton: document.querySelector("#reviewOllamaButton"),
  ollamaStatus: document.querySelector("#ollamaStatus"),
  tableTitle: document.querySelector("#tableTitle"),
  detectedColumns: document.querySelector("#detectedColumns"),
  resultBody: document.querySelector("#resultBody"),
  searchInput: document.querySelector("#searchInput"),
  confidenceFilter: document.querySelector("#confidenceFilter"),
  failedOnly: document.querySelector("#failedOnly"),
  exportButton: document.querySelector("#exportButton"),
};

function show(element) {
  element.classList.remove("hidden");
}

function hide(element) {
  element.classList.add("hidden");
}

function setStatus(text, active = true) {
  els.statusText.textContent = text;
  active ? show(els.statusPanel) : hide(els.statusPanel);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function normalize(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toUpperCase();
}

async function loadMeta() {
  const response = await fetch("/api/meta");
  if (!response.ok) throw new Error("Nao foi possivel carregar a tabela NCM.");
  const meta = await response.json();
  els.vigenciaStatus.textContent = meta.vigencia.data_ultima_atualizacao || "Vigencia nao informada";
  els.atoStatus.textContent = `${meta.vigencia.ato || "Ato nao informado"} | ${meta.total_regras} regras`;
}

function currentRows() {
  if (!state.result) return [];
  const query = normalize(els.searchInput.value);
  const confidence = els.confidenceFilter.value;
  const failedOnly = els.failedOnly.checked;
  return state.result.linhas.filter((row) => {
    const searchable = normalize(
      `${row.descricao} ${row.ncm_sugerido} ${row.ncm_final} ${row.categoria} ${row.justificativa} ${row.motivo_revisor}`,
    );
    if (query && !searchable.includes(query)) return false;
    if (confidence && row.confianca !== confidence) return false;
    if (failedOnly && !state.failed.has(row.linha)) return false;
    return true;
  });
}

function ollamaBadge(row) {
  if (!row.ollama_review) return '<span class="badge pendente">pendente</span>';
  const confidence = row.ollama_review.confianca_ia || "baixa";
  const review = row.ollama_review.revisao_humana ? '<div class="review-note">Revisao humana</div>' : "";
  return `<span class="badge ${escapeHtml(confidence)}">${escapeHtml(confidence)}</span>${review}<div class="ai-final">${escapeHtml(row.ollama_review.cfop_ia)} / ${escapeHtml(row.ollama_review.ncm_ia)}</div>`;
}

function updateSummary() {
  if (!state.result) return;
  const confidence = state.result.resumo.confianca || {};
  const cfop = state.result.resumo.cfop || {};
  els.totalRows.textContent = state.result.total_linhas.toLocaleString("pt-BR");
  els.cfop5405.textContent = (cfop["5405"] || 0).toLocaleString("pt-BR");
  els.highConfidence.textContent = (confidence.alta || 0).toLocaleString("pt-BR");
  els.humanReview.textContent = (state.result.resumo.revisao_humana || 0).toLocaleString("pt-BR");
  els.failedCount.textContent = state.failed.size.toLocaleString("pt-BR");
}

function renderCandidates(candidates) {
  if (!Array.isArray(candidates) || candidates.length === 0) return "-";
  return candidates
    .slice(0, 3)
    .map((candidate) => `${candidate.ncm} - ${candidate.descricao_oficial}`)
    .join(" | ");
}

function renderTable() {
  const rows = currentRows();
  const fragment = document.createDocumentFragment();
  els.resultBody.innerHTML = "";

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.linha}</td>
      <td class="description">${escapeHtml(row.descricao)}</td>
      <td><strong>${escapeHtml(row.cfop_sugerido)}</strong></td>
      <td>${escapeHtml(row.ncm_sugerido)}</td>
      <td>${escapeHtml(row.categoria)}</td>
      <td><span class="badge ${escapeHtml(row.confianca)}">${escapeHtml(row.confianca)}</span></td>
      <td><strong>${escapeHtml(row.ncm_final)}</strong></td>
      <td>
        <span class="badge ${escapeHtml(row.confianca_revisor)}">${escapeHtml(row.confianca_revisor)}</span>
        ${row.revisao_humana ? '<div class="review-note">Revisao humana</div>' : ""}
      </td>
      <td class="ollama-result">${ollamaBadge(row)}</td>
      <td class="candidates">${escapeHtml(renderCandidates(row.candidatos_ncm))}</td>
      <td class="justification">${escapeHtml(row.justificativa)} ${escapeHtml(row.motivo_revisor)} ${escapeHtml(row.ollama_review?.motivo_ia || "")}</td>
      <td class="fail-cell">
        <input type="checkbox" data-line="${row.linha}" ${state.failed.has(row.linha) ? "checked" : ""} />
      </td>
    `;
    fragment.appendChild(tr);
  }

  els.resultBody.appendChild(fragment);
  els.tableTitle.textContent = `Resultado da analise (${rows.length.toLocaleString("pt-BR")} linhas visiveis)`;
  updateSummary();
}

async function analyzeFile() {
  if (!state.file) return;
  state.failed.clear();
  show(els.summary);
  hide(els.tableSection);
  setStatus("Analisando planilha e aplicando regras...");
  els.analyzeButton.disabled = true;

  try {
    const url = `/api/analyze?filename=${encodeURIComponent(state.file.name)}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
      body: state.file,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.erro || "Falha ao analisar arquivo.");
    state.result = payload;
    els.detectedColumns.textContent = `Arquivo: ${payload.arquivo} | Aba: ${payload.aba} | Descricao: ${
      payload.colunas_detectadas.descricao || "-"
    } | CFOP: ${payload.colunas_detectadas.cfop || "-"} | NCM: ${payload.colunas_detectadas.ncm || "-"}`;
    renderTable();
    show(els.tableSection);
    show(els.ollamaPanel);
    setStatus("Analise concluida.", false);
  } catch (error) {
    setStatus(error.message || "Erro inesperado ao analisar.", true);
  } finally {
    els.analyzeButton.disabled = !state.file;
  }
}

async function testOllama() {
  els.ollamaStatus.textContent = "Testando conexao com Ollama...";
  const params = new URLSearchParams({
    base_url: els.ollamaUrl.value,
    model: els.ollamaModel.value,
  });
  try {
    const response = await fetch(`/api/ollama/status?${params.toString()}`);
    const payload = await response.json();
    if (!payload.ok) {
      els.ollamaStatus.textContent = `${payload.erro} Modelos encontrados: ${(payload.modelos_disponiveis || []).join(", ") || "nenhum"}`;
      return;
    }
    els.ollamaStatus.textContent = `Ollama conectado em ${payload.base_url}. Modelo ${payload.model} disponivel.`;
  } catch (error) {
    els.ollamaStatus.textContent = error.message || "Falha ao testar Ollama.";
  }
}

async function reviewWithOllama() {
  if (!state.result) return;
  const batchSize = Math.max(1, Math.min(25, Number(els.ollamaBatch.value) || 10));
  const rows = state.result.linhas
    .filter((row) => row.revisao_humana && !row.ollama_review)
    .slice(0, batchSize);
  if (rows.length === 0) {
    els.ollamaStatus.textContent = "Nao ha linhas pendentes de revisao Ollama neste filtro.";
    return;
  }

  els.reviewOllamaButton.disabled = true;
  els.ollamaStatus.textContent = `Revisando ${rows.length} linhas com ${els.ollamaModel.value}...`;
  try {
    const response = await fetch("/api/ollama/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url: els.ollamaUrl.value,
        model: els.ollamaModel.value,
        linhas: rows,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.erro || "Falha na revisao Ollama.");
    const byLine = new Map(payload.resultados.map((item) => [Number(item.linha), item]));
    for (const row of state.result.linhas) {
      const review = byLine.get(Number(row.linha));
      if (review) row.ollama_review = review;
    }
    els.ollamaStatus.textContent = `Ollama revisou ${payload.total} linhas. Rode o proximo lote quando quiser.`;
    renderTable();
  } catch (error) {
    els.ollamaStatus.textContent = error.message || "Erro inesperado na revisao Ollama.";
  } finally {
    els.reviewOllamaButton.disabled = false;
  }
}

function exportCsv() {
  if (!state.result) return;
  const headers = [
    "linha",
    "descricao",
    "cfop_sugerido",
    "ncm_sugerido",
    "categoria",
    "confianca",
    "cfop_final",
    "ncm_final",
    "confianca_revisor",
    "revisao_humana",
    "motivo_revisor",
    "ollama_cfop",
    "ollama_ncm",
    "ollama_confianca",
    "ollama_revisao_humana",
    "ollama_motivo",
    "justificativa",
    "falha_marcada",
  ];
  const lines = [headers.join(";")];
  for (const row of currentRows()) {
    const values = headers.map((header) => {
      let value = row[header];
      if (header === "falha_marcada") value = state.failed.has(row.linha);
      if (header === "ollama_cfop") value = row.ollama_review?.cfop_ia || "";
      if (header === "ollama_ncm") value = row.ollama_review?.ncm_ia || "";
      if (header === "ollama_confianca") value = row.ollama_review?.confianca_ia || "";
      if (header === "ollama_revisao_humana") value = row.ollama_review?.revisao_humana ?? "";
      if (header === "ollama_motivo") value = row.ollama_review?.motivo_ia || "";
      return `"${String(value ?? "").replaceAll('"', '""')}"`;
    });
    lines.push(values.join(";"));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "auditoria_cfop_ncm.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

els.fileInput.addEventListener("change", () => {
  state.file = els.fileInput.files[0] || null;
  els.fileName.textContent = state.file ? state.file.name : "Escolher arquivo .xlsx";
  els.analyzeButton.disabled = !state.file;
});

els.analyzeButton.addEventListener("click", analyzeFile);
els.searchInput.addEventListener("input", renderTable);
els.confidenceFilter.addEventListener("change", renderTable);
els.failedOnly.addEventListener("change", renderTable);
els.exportButton.addEventListener("click", exportCsv);
els.testOllamaButton.addEventListener("click", testOllama);
els.reviewOllamaButton.addEventListener("click", reviewWithOllama);

els.resultBody.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  const line = Number(target.dataset.line);
  if (!line) return;
  if (target.checked) {
    state.failed.add(line);
  } else {
    state.failed.delete(line);
  }
  updateSummary();
});

loadMeta().catch((error) => {
  els.vigenciaStatus.textContent = "Nao foi possivel carregar a vigencia";
  els.atoStatus.textContent = error.message;
});
