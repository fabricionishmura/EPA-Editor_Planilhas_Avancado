# EPA: Editor e Auditor de Planilhas Avançado

Analisador fiscal inteligente de produtos para auditoria e sugestão de CFOP e NCM a partir de planilhas Excel.

O EPA — Editor de Planilhas Avançado é uma aplicação local desenvolvida para auxiliar na análise e classificação fiscal de produtos a partir de arquivos .xlsx.

O projeto nasceu da necessidade de automatizar parte de um processo manual de conferência de produtos, mantendo as decisões **explicáveis e passíveis de revisão humana**.

O sistema lê uma planilha de produtos, identifica suas colunas, analisa as descrições e os NCMs existentes, aplica um conjunto de regras fiscais configuráveis e produz sugestões de CFOP, NCM, categoria e nível de confiança, sempre acompanhadas de justificativas para facilitar a auditoria.

Além do motor determinístico de regras, o projeto possui um revisor local sem custo e uma integração opcional com Ollama, permitindo utilizar modelos de IA localmente para revisar os casos que exigem maior atenção.

> ⚠️⚠️⚠️ O EPA é uma ferramenta de apoio à análise fiscal. As classificações sugeridas devem ser validadas por um profissional responsável antes de sua utilização definitiva. ⚠️⚠️⚠️

## O que o projeto faz

A partir de uma planilha `.xlsx`, o EPA:

* identifica as colunas de produtos;
* analisa as descrições;
* aplica regras fiscais configuráveis;
* verifica o NCM atualmente cadastrado;
* sugere CFOP e NCM;
* gera candidatos alternativos de NCM;
* atribui score e nível de confiança;
* apresenta justificativas para as sugestões;
* identifica casos que precisam de revisão humana;
* permite uma revisão adicional utilizando IA local;
* exporta os resultados para CSV.

## Como funciona

O processo combina diferentes fontes de informação:

```text
Planilha Excel
      ↓
Normalização da descrição
      ↓
Regras fiscais
      +
NCM atual
      +
Base NCM vigente
      ↓
Sugestão de CFOP/NCM
      ↓
Score e confiança
      ↓
Revisão local
      ↓
Revisão por IA (opcional)
      ↓
Auditoria final
```

A ideia principal é utilizar **automação conservadora**: quando não existem evidências suficientes, o sistema pode encaminhar o produto para revisão humana em vez de simplesmente assumir uma classificação.

## Sistema de confiança

As classificações recebem níveis de confiança:

| Confiança             | Score | Interpretação                                      |
| --------------------- | ----: | -------------------------------------------------- |
| **Alta**              |  ≥ 90 | Sugestão com forte evidência                       |
| **Média**             |  ≥ 65 | Sugestão que merece validação                      |
| **Baixa**             |   ≥ 1 | Caso com evidências insuficientes                  |
| **Sem classificação** |     0 | Não foi possível chegar a uma classificação segura |

Os próprios arquivos de regras definem os limites e as ações recomendadas para cada nível.

## IA local

O projeto possui integração opcional com **Ollama**, permitindo utilizar modelos de IA localmente para revisar casos identificados pelo sistema.

A IA funciona como uma **camada complementar de análise**, não como substituta das regras fiscais ou da validação profissional.

## Interface

A interface web é executada localmente e apresenta:

* situação da vigência da tabela NCM;
* quantidade de regras carregadas;
* upload da planilha;
* resumo da análise;
* quantidade de CFOP 5405;
* quantidade de classificações de alta confiança;
* quantidade de itens para revisão humana;
* tabela detalhada dos resultados;
* filtros;
* revisão opcional com Ollama;
* exportação CSV.

## Estrutura

```text
EPA-Editor_Planilhas_Avancado/
│
├── app.py
├── candidate_generator.py
├── local_reviewer.py
├── ollama_reviewer.py
├── regras_fiscais.json
├── Tabela_NCM_Vigente_*.json
│
└── web/
    ├── index.html
    ├── app.js
    └── styles.css
```

### Principais arquivos

**`app.py`**
Núcleo da aplicação e servidor web local.

**`regras_fiscais.json`**
Regras utilizadas para análise e classificação dos produtos.

**`candidate_generator.py`**
Geração e ranqueamento de candidatos NCM.

**`local_reviewer.py`**
Validação determinística e identificação de casos para revisão.

**`ollama_reviewer.py`**
Integração opcional com modelos de IA executados através do Ollama.

**`web/`**
Interface web da aplicação.

## Como executar

### Requisitos

* Python 3.10+
* Navegador moderno
* Planilha `.xlsx`

Clone o projeto:

```bash
git clone https://github.com/fabricionishmura/EPA-Editor_Planilhas_Avancado.git
cd EPA-Editor_Planilhas_Avancado
```

Execute:

```bash
python app.py
```

Depois acesse:

```text
http://127.0.0.1:8765
```

## Resultado

A aplicação apresenta uma visão da auditoria contendo, entre outras informações:

* descrição do produto;
* NCM atual;
* NCM sugerido;
* CFOP sugerido;
* categoria;
* score;
* nível de confiança;
* justificativa;
* candidatos NCM;
* indicação de revisão humana.

Os resultados podem ser exportados para **CSV**.

## Cuidados e limitações

### A aplicação não substitui uma análise fiscal profissional

NCM e CFOP são classificações com impacto tributário. Uma sugestão automatizada não deve ser interpretada como decisão fiscal definitiva.

### As regras precisam ser mantidas atualizadas

A base atualmente incluída no projeto está relacionada à vigência de **01/07/2026**. Alterações na legislação ou nas tabelas oficiais exigem atualização das bases e, quando necessário, das regras do sistema.

### A qualidade depende da descrição do produto

Descrições incompletas, genéricas ou inconsistentes podem produzir baixa confiança ou exigir revisão humana.

### A IA é uma camada complementar

O Ollama não deve ser tratado como fonte fiscal oficial. Seu papel no projeto é auxiliar na revisão de situações que já foram identificadas pelo sistema como potencialmente ambíguas.

## Privacidade

O processamento principal acontece localmente.

A planilha é enviada para o próprio servidor Python local da aplicação para análise. A integração com IA também foi projetada para utilizar um servidor Ollama configurado pelo usuário, inclusive podendo apontar para outro computador da rede local.

Não existe, na implementação atual, uma dependência obrigatória de uma API de IA em nuvem.

> Ao configurar um servidor Ollama em outro computador ou rede, a responsabilidade pela segurança e pelo controle de acesso desse servidor passa a ser do ambiente onde ele está hospedado.

## Tecnologias

* **Python**
* **HTML / CSS / JavaScript**
* **Excel / XLSX**
* **JSON**
* **Ollama**
* **Modelos de IA locais**

## Status

Projeto pessoal encontra-se em desenvolvimento e atualmente possui:

* [x] Leitura de arquivos `.xlsx`;
* [x] Identificação automática de colunas;
* [x] Normalização de descrições;
* [x] Motor de regras fiscais;
* [x] Sistema de pontuação;
* [x] Classificação por confiança;
* [x] Validação do NCM antigo;
* [x] Geração de candidatos NCM;
* [x] Revisor local;
* [x] Marcação para revisão humana;
* [x] Interface web;
* [x] Filtros de auditoria;
* [x] Exportação CSV;
* [x] Integração opcional com Ollama;
* [ ] Testes automatizados abrangentes;
* [ ] Empacotamento/distribuição simplificada;
* [ ] Atualização automatizada das tabelas fiscais;
* [ ] Exportação direta para Excel mantendo formatação;
* [ ] Histórico de auditorias e versões das classificações.

Algumas ideias futuras:

* atualização automática da base NCM;
* histórico de auditorias;
* testes automatizados das regras;
* melhorias na revisão por IA;
* dashboard de auditoria.

## Licença e fontes de dados

### Código-fonte

O código do Editor e Auditor de Planilhas Avançado é disponibilizado sob a **MIT License**.

Isso permite o uso, cópia, modificação e distribuição do código, inclusive em projetos comerciais, desde que o aviso de copyright e o texto da licença sejam mantidos.

Consulte o arquivo [`LICENSE`](LICENSE) para o texto completo da licença.

### Base de NCM

A base de NCM utilizada pelo projeto é obtida a partir dos dados disponibilizados pelo **Portal Único Siscomex / Receita Federal**, através do sistema Classif.

A fonte oficial utilizada é o endpoint público de download da nomenclatura em formato JSON:

`https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json`

A Receita Federal informa que esse download disponibiliza a tabela NCM vigente. A base pode mudar conforme novas versões da nomenclatura entram em vigor, portanto os arquivos incluídos no projeto representam uma versão específica da base utilizada no momento de sua geração.

**Fonte oficial:** Portal Único Siscomex / Receita Federal, Nomenclatura Comum do Mercosul (NCM).

### Dados de exemplo

As planilhas de produtos de exemplo incluídas no projeto foram **geradas automaticamente com auxílio do ChatGPT**, exclusivamente para fins de demonstração, desenvolvimento e testes.

Os dados de exemplo não representam necessariamente produtos, empresas, operações comerciais ou informações fiscais reais.

### Importante

A licença MIT aplica-se ao **código-fonte desenvolvido para este projeto**.

Bases de dados, informações oficiais, documentos ou outros conteúdos obtidos de fontes externas permanecem sujeitos às condições e regras aplicáveis às suas respectivas fontes.

O EPA é uma ferramenta de apoio à análise e auditoria. As sugestões de NCM e CFOP não constituem, por si só, uma classificação fiscal oficial ou orientação tributária.


## Autor

**Fabricio Nishmura**

Projeto pessoal desenvolvido para explorar automação, análise de dados, regras de negócio e IA aplicada a um problema real.

🔗 **GitHub:**
https://github.com/fabricionishmura/EPA-Editor_Planilhas_Avancado
