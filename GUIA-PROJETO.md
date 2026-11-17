# Guia do Projeto — Resume Matcher (fork local)

> **Para quem lê este arquivo:** ele é autossuficiente. Contém o contexto, as decisões já
> tomadas, o estado do ambiente, os comandos exatos e o plano de execução.
> Não é preciso consultar conversas anteriores.

---

## 1. Objetivo

Rodar o **Resume-Matcher** (`srbhr/Resume-Matcher`) a partir de um fork próprio, **exclusivamente
na máquina local** — sem hospedagem, sem deploy, sem acesso externo — e aplicar melhorias
direcionadas ao perfil profissional do dono do projeto (desenvolvimento full stack com foco em
**WordPress, PHP, WooCommerce, Astro e front-end**).

**Uso pretendido:** enviar o currículo (PDF/DOCX), informar a vaga, e receber um currículo
adaptado, validado e exportável.

**Princípio inegociável do produto:** o sistema **não inventa experiência**. Ele reorganiza,
reescreve e prioriza o que existe, e quando uma exigência da vaga não está coberta, ele
**pergunta ao usuário** — só depois de uma confirmação humana o conteúdo novo entra no currículo.
Esse é o mecanismo que já existe no projeto (`keyword forcing` + `attested`) e é a base da
melhoria de "entrevista de lacunas".

---

## 2. Decisões já tomadas (não reabrir)

| Decisão | Escolha | Motivo |
|---|---|---|
| Base do projeto | **Fork do Resume-Matcher** | Já resolve parsing, tailoring com validação, ATS score e PDF |
| Hospedagem | **Nenhuma — apenas local** | Elimina as restrições de Cloudflare Free (CPU de 10 ms, Chromium, SQLite) |
| Repositório | **Fork público** `gabrielgpacheco/Resume-Matcher` | Sincronização com o upstream em um clique |
| Provedor de IA | **OpenCode Go** via provider `openai_compatible` | Assinatura já paga, cota mensal alta, endpoint compatível com OpenAI |
| Modelo padrão | `glm-5.3-flash` | É servido em `/chat/completions` e tem US$ 60/mês de limite no plano Go |
| Layout de saída | Templates existentes (coluna única, ATS-friendly) | Não é objetivo replicar o design do PDF original |
| Modo "agent" (MCP) | Documentado como plano B, não é o fluxo principal | Mantém o fluxo pela interface web |

**Melhorias priorizadas** (todas aprovadas): leitura da vaga por URL, entrevista de lacunas,
exportação DOCX, prompt pack WordPress/PHP, revisão pt-BR, e Edit Mode com sugestões no idioma
do currículo (pt-BR).

---

## 3. Ambiente verificado (em 16/11/2026)

| Ferramenta | Versão instalada | Situação |
|---|---|---|
| Windows | 11 (build 26200) | ok |
| PowerShell | 5.1 | ok |
| git | 2.52.0 | ok |
| gh CLI | 2.103.0, logado como `gabrielgpacheco` (escopos `repo`, `workflow`) | ok |
| Python | 3.14.4 (backend exige >= 3.14) | ok |
| uv | 0.13.6 | ok |
| Node | v24.15.0 (repo fixa 26.13.1 no `.nvmrc`; Next 16 exige >= 20.9) | ok, gera aviso de `engines` |
| npm | 11.12.1 | ok |
| Google Chrome | instalado em `C:\Program Files\Google\Chrome\Application\chrome.exe` | ok — PDF sem baixar Chromium |
| Microsoft Edge | instalado | fallback de PDF |
| Docker | instalado, **daemon parado** | não é necessário |
| Disco livre em C: | ~34 GB (necessário ~2 GB) | ok |
| Fork `gabrielgpacheco/Resume-Matcher` | **não existe ainda** | criar na Fase 0 |

**Diretório do projeto:** `C:\Users\dayan\Downloads\gerador-curriculo`
Ele contém apenas este arquivo; o clone entra ao redor dele (ver 4.2).

---

## 4. Fase 0 — Setup do fork local

### 4.1 Criar o fork

```powershell
gh repo fork srbhr/Resume-Matcher --clone=false
```

Idempotente: se o fork já existir, o gh apenas informa.

### 4.2 Clonar preservando este guia

`git clone <url> .` **falha**, porque a pasta não está vazia (este arquivo está aqui).
Clonar em um diretório temporário e mover o conteúdo resolve sem apagar o guia:

```powershell
Set-Location C:\Users\dayan\Downloads\gerador-curriculo
$tmp = Join-Path $env:TEMP "resume-matcher-clone"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
git clone https://github.com/gabrielgpacheco/Resume-Matcher.git $tmp
Get-ChildItem -Force $tmp | Move-Item -Destination . -Force
Remove-Item $tmp -Recurse -Force
```

Conferir e registrar o upstream:

```powershell
git remote -v
# se "upstream" não existir:
git remote add upstream https://github.com/srbhr/Resume-Matcher.git
git fetch upstream
```

- `origin` → `gabrielgpacheco/Resume-Matcher` (seu fork)
- `upstream` → `srbhr/Resume-Matcher` (original, somente leitura)

### 4.3 Dependências

```powershell
# Backend
Set-Location .\apps\backend
Copy-Item .env.example .env -ErrorAction SilentlyContinue
uv sync

# Frontend
Set-Location ..\frontend
npm install
```

Notas:
- `uv` encontra o Python 3.14.4 já instalado; não é preciso instalar Python.
- `npm install` emite `EBADENGINE` por causa do Node 24 vs 26 do `.nvmrc`. É **cosmético**;
  o Next 16 aceita Node >= 20.9. Só instalar Node 26 (via `fnm`) se algo falhar de fato.
- Não é preciso `uv run playwright install chromium`: o Chrome instalado é usado no PDF.

### 4.4 Configurar o provedor (OpenCode Go)

Editar `apps/backend/.env` e **substituir** o bloco de LLM. Não copiar o `LLM_PROVIDER=openai`
do exemplo — o `.env` tem precedência sobre a tela de Settings.

```env
LLM_PROVIDER=openai_compatible
LLM_MODEL=glm-5.3-flash
LLM_API_BASE=https://opencode.ai/inference/go/openai/v1
LLM_API_KEY=cole-a-chave-do-console-opencode
HOST=127.0.0.1
PORT=8000
FRONTEND_BASE_URL=http://localhost:3000
```

Como isso chega no provedor (verificado no código):
`get_model_name()` converte para `openai/glm-5.3-flash`; `_build_router()` passa
`api_base` preservando `/v1`. Resultado: `POST https://opencode.ai/inference/go/openai/v1/chat/completions`.
É exatamente o endpoint documentado pelo Go.

Modelos do plano Go que funcionam nesse caminho (`/chat/completions`):
`glm-5.3-flash`, `glm-5.3`, `glm-5.2`, `kimi-k2.7-code`, `deepseek-v4.1-flash`,
`minimax-m3.1-flash`, `longcat-2.0`.

**Não** funcionam nesse provider: `gpt-6-luna`, `claude-haiku-5-5`, `gemini-4-argon`
(usam `/responses` ou `/v1/messages`).

Alternativa sem `.env`: configurar na tela **Settings** do app (chave criptografada no SQLite).
Nesse caso as linhas `LLM_*` do `.env` devem ficar vazias.

### 4.5 Rodar

Dois terminais:

```powershell
# Terminal 1 — backend
Set-Location C:\Users\dayan\Downloads\gerador-curriculo\apps\backend
uv run app                      # http://127.0.0.1:8000  (docs em /docs)

# Terminal 2 — frontend
Set-Location C:\Users\dayan\Downloads\gerador-curriculo\apps\frontend
npm run dev                     # http://localhost:3000
```

Abrir `http://localhost:3000`.

### 4.6 Scripts de conveniência (criar na raiz do repo)

| Arquivo | Função |
|---|---|
| `start.ps1` | Sobe backend e frontend em janelas separadas, aguarda as portas e abre o navegador |
| `sync-upstream.ps1` | `git fetch upstream` + merge de `upstream/main` preservando as melhorias locais |
| `setup.ps1` | Refaz 4.2–4.5 de forma idempotente em uma máquina nova |

`sync-upstream.ps1` não é luxo: o upstream lança versões com frequência (a atual é 1.4.0) e sem
ele o fork fica congelado.

---

## 5. Fase 1 — Correções de base (fazer antes das features)

Estas correções evitam falhas silenciosas no fluxo principal.

### 5.1 Corte de tokens em 4096 (prioridade máxima)

**Problema:** `apps/backend/app/llm.py` → `get_safe_max_tokens()` consulta o registro do LiteLLM.
Modelos fora do registro (caso de `glm-5.3-flash`) caem em `FALLBACK_MAX_TOKENS = 4096`.
O parse do currículo pede `DEFAULT_JSON_MAX_TOKENS = 8192`. Currículos longos podem voltar
**JSON truncado**, e o erro aparece como falha de validação, não como erro de token.

**Correção:** registrar o modelo em `litellm.model_cost` (com `max_output_tokens` e
`supported_openai_params`) **ou** elevar o fallback para `openai_compatible`. Se alterar o
fallback, manter o clamp real quando o modelo estiver no registro.

**Aceite:** currículo de 2 páginas com muitas seções é parseado sem truncamento; log mostra
`max_tokens` acima de 4096.

### 5.2 JSON mode

**Problema:** `JSON_MODE_VERIFIED_HOSTS` contém apenas `api.stepfun.com`. Para `opencode.ai`,
`_supports_json_mode()` retorna `False` e o app usa JSON por prompt.

**Tarefa:** testar se o gateway aceita `response_format={"type":"json_object"}`. Se aceitar,
adicionar `opencode.ai` à allowlist, com o mesmo critério documentado no código
("verificado com requisição real", não documentação de fornecedor).

**Aceite:** `complete_json()` recebe `response_format` quando habilitado; fallback continua
funcionando se o provedor devolver 400.

### 5.3 Validação ponta a ponta

1. Criar currículo mestre a partir do PDF real do usuário.
2. Colar uma vaga real em português.
3. Rodar tailoring na estratégia `full`.
4. Conferir: nenhum fato inventado, datas preservadas, ATS score calculado, PDF gerado.
5. Rodar o **ATS parse check** e confirmar que o texto extraído do PDF está legível.

**Aceite:** o ciclo completo funciona sem `response_warnings` críticos.

### 5.4 Descobertas da execução (fixes extras aplicados)

Durante a execução da Fase 1, dois problemas **fora do plano original** foram encontrados
e corrigidos (branch `fix/llm-token-budget`):

1. **O gateway Go exige o header `x-opencode-session`** — devolve `400 MissingSessionID`
   sem ele. Não é "detalhe menor". Correção: `_route_acompletion` injeta
   `extra_headers` (`x-opencode-session` + `User-Agent` próprio) apenas para o caminho
   `opencode.ai/inference/go` (helper `_opencode_go_headers`).

2. **A chave do `.env` era ignorada para `openai_compatible`** — `resolve_api_key` pula o
   fallback de env para `openai_compatible`/`ollama` (proteção contra vazar chave paga para
   servidor local). Correção: exceção escopada permite a chave de env quando o `api_base`
   aponta para o gateway Go (`_is_opencode_go_endpoint`).

3. `response_format={"type":"json_object"}` foi **verificado com requisição real** no gateway
   e habilitado (`_openai_compatible_supports_json_mode` retorna `True` para o gateway Go).

Validação real concluída: parse do CV (5 experiências, sem truncamento), tailoring `full`
(ATS score 43.1, 9 mudanças rejeitadas pelo contrato anti-invenção — correto), PDF gerado
e ATS parse check legível.

---

## 6. Fase 2 — Melhorias (uma branch por item)

Ordem recomendada: 6.1 → 6.2 → 6.3 → 6.4 → 6.5.
Cada item tem branch, critério de aceite e teste.

### 6.1 `feat/job-url` — ler a vaga pela URL

**Objetivo:** colar a URL da vaga em vez do texto inteiro.

**Onde mexer:**
- Novo router `apps/backend/app/routers/job_url.py` (registrar em `app/main.py`), ou endpoint
  em `routers/jobs.py`.
- `POST /api/v1/jobs/from-url` com `{ "url": "..." }` → `{ "content": "...", "title", "company", "source" }`.
- Extração em cascata:
  1. `httpx` com timeout curto e `User-Agent` identificável;
  2. buscar `<script type="application/ld+json">` e localizar o nó `JobPosting`
     (aceitar `@graph` e arrays); `description` vem em HTML;
  3. fallback: converter o HTML em Markdown com o `markitdown` já instalado, descartando
     `script/style/nav/footer`;
  4. falhou tudo → HTTP 422 com mensagem clara pedindo para colar o texto.
- Segurança: aceitar apenas `http`/`https`, bloquear IPs privados e `localhost` (SSRF),
  limitar o corpo baixado (ex.: 3 MB) e o tempo (ex.: 15 s).
- Frontend: campo "URL da vaga" na página `app/(default)/tailor/page.tsx`, que preenche a
  textarea com o texto retornado e permite edição.

**Limitação conhecida e aceitável:** LinkedIn e Indeed bloqueiam acesso automatizado
(robots.txt / ToS). O fallback para texto colado é o caminho esperado nesses casos, não um bug.

**Aceite:** uma vaga do Gupy (`portal.gupy.io`) e uma de site de empresa (Greenhouse/Lever ou
página com `JobPosting`) importam corretamente; URL do LinkedIn retorna a mensagem amigável.

### 6.2 `feat/gap-interview` — entrevista de lacunas

**Objetivo:** transformar o painel de keywords faltantes em uma entrevista em texto. A IA pergunta,
o usuário responde, e só o que ele confirmar entra no currículo mestre.

**Base existente:** `apps/backend/app/services/keyword_forcing.py`
(`keyword_placements`, `force_keywords`) já implementa o conceito de `attested` — uma keyword só
entra no currículo se o usuário declarar que a possui. A melhoria adiciona a etapa de perguntas.

**Fluxo:**
1. Calcular lacunas: `analyze_keyword_gaps()` / `calculate_keyword_match()` em `services/refiner.py`.
   A entrevista usa `missing_keywords()` (mesma regra de `keyword_in_text`, mas em ordem da vaga
   e determinística).
2. `POST /api/v1/resumes/{resume_id}/gap-interview` (body: `job_id`) →
   gera até 8 perguntas via `complete_json` (`schema_type="gap_interview"`) com schema:
   `[{ "keyword", "question", "context" }]`. Uma pergunta por lacuna relevante, curta, no idioma
   de conteúdo (`get_content_language()`), nunca sugerindo a resposta.
3. UI: `components/tailor/gap-interview-dialog.tsx`, aberto pelo painel de keywords. Cada pergunta
   tem "já usei" e "não tenho essa experiência" como opções explícitas; salvar exige resposta
   para todas.
4. `POST /api/v1/resumes/{resume_id}/gap-answers` (body: respostas) registra as respostas e devolve
   `attested` (as keywords confirmadas). O frontend então chama o fluxo existente de
   `apply-keywords` com `attested: true`, que coloca a keyword em skills e em até 2 linhas.
   Decisão: a entrevista **não** reescreve o currículo mestre sozinha — o mestre só recebe skills
   confirmadas no "confirm" do preview, como já acontece hoje (menos surpresa e sem preview obsoleto).
5. Persistir as respostas em `jobs.metadata_json` (`gap_answers`, por `resume_id`) para não
   perguntar de novo.

**Regra dura:** nenhuma keyword entra sem resposta afirmativa do usuário. Resposta "não tenho"
gera uma recomendação de estudo (texto i18n no frontend), nunca conteúdo no currículo.

**Aceite:** vaga com requisito ausente gera pergunta; "não tenho" não altera o currículo;
"tenho" adiciona a keyword em skills e em até 2 linhas, sem inventar métrica ou empregador.

**Implementada:** `services/gap_interview.py`, `prompts/gap_interview.py`, schemas em
`schemas/writing.py`, dois endpoints em `routers/resumes.py`, `truncation` própria em `llm.py`,
dialog e integração no painel de keywords, 17 chaves i18n nos 7 locales, testes unitários e de
integração.

### 6.3 `feat/docx-export` — exportar DOCX

**Objetivo:** gerar `.docx` além do PDF.

**Onde mexer:**
- `python-docx` **já é dependência** do backend (`pyproject.toml`).
- Novo serviço `apps/backend/app/services/docx_export.py`: recebe o mesmo `ResumeData`
  (de `app/schemas/models.py`) e monta um documento de coluna única com estilos de heading
  reais (não caixas de texto nem tabelas) para preservar a leitura por ATS.
- Endpoint `GET /api/v1/resumes/{resume_id}/docx` ao lado do `GET /{resume_id}/pdf`
  em `routers/resumes.py`, com `Content-Disposition` correto.
- Frontend: botão de download na barra de ações do currículo.

**Aceite:** o arquivo abre no Word/LibreOffice, o texto é extraível, a ordem das seções está
correta e nenhum caractere é perdido.

**Implementada:** `services/docx_export.py` (`build_resume_docx`, `has_renderable_content`,
`format_date_range`, `group_skills`), endpoint `GET /api/v1/resumes/{resume_id}/docx` (404 sem
currículo, 409 sem dados renderizáveis), botões no visualizador de currículo e no construtor,
`downloadResumeDocx`/`getResumeDocxUrl` no cliente, testes unitários e de integração (25).
Decisões: A4 fixo, sem parâmetros de template; ordem e visibilidade vêm de `sectionMeta`;
`descriptionStyles` decide entre marcador e linha simples; formatação inline
(negrito/itálico/sublinhado) vira runs reais do Word.

### 6.4 `feat/wp-prompt-pack` — vocabulário WordPress/PHP

**Objetivo:** melhorar aderência a vagas de WordPress/PHP no mercado brasileiro.

**Onde mexer:**
- `apps/backend/app/prompts/templates.py` (`IMPROVE_RESUME_PROMPTS`,
  `CRITICAL_TRUTHFULNESS_RULES`) e `prompts/writing.py` (`WRITING_RUBRIC`).
- Adicionar um "pack" de domínio ativável nas configurações, cobrindo termos como:
  temas e plugins próprios, WooCommerce, ACF/CPT, REST API, Gutenberg/blocos,
  headless (WP + Next/Astro), performance e Core Web Vitals, segurança e hardening,
  deploy, PHP 8.x, Composer, hooks/filters.
- O pack **só orienta vocabulário**: continua proibido afirmar tecnologia que o mestre não contém.
  Toda introdução de termo novo deve passar pela atestação de 6.2.

**Aceite:** com o pack ativo, os bullets usam o vocabulário da vaga; o teste de "fact violations"
(`services/writing_quality.py`) continua limpo.

**Implementada:** `prompts/domain_packs.py` (registro `DomainPack`, `detect_domain_pack`,
`resolve_domain_pack`, `domain_pack_prompt`, `domain_pack_options`) e
`services/domain_pack.py` (lê `domain_pack` do config). Novo placeholder
`{domain_pack_section}` em `DIFF_IMPROVE_PROMPT` e nos quatro `IMPROVE_RESUME_PROMPT_*`, preenchido
em `generate_resume_diffs`/`improve_resume` (preview e pipeline do agente).
`GET/PUT /api/v1/config/prompts` passam a expor `domain_pack` (`auto` padrão, `off`, ou id de pack)
e `domain_pack_options`; tela de Configurações ganhou o seletor "Vocabulário de domínio" com i18n
nos 7 locales. Detecção: um termo forte (`wordpress`, `woocommerce`, `gutenberg`, ...) ou três termos
genéricos (`php`, `composer`, `mysql`, ...). Decisões: o pack não altera contagem/estrutura de
bullets e o bloco de prompt proíbe explicitamente afirmar ferramenta, plugin, métrica ou
responsabilidade ausente; lacunas continuam sendo tratadas pela entrevista de 6.2.

### 6.5 `feat/pt-br-review` — revisão de português do Brasil

**Objetivo:** garantir pt-BR nativo, não português de Portugal.

**Onde mexer:**
- `apps/frontend/i18n/config.ts`, `apps/frontend/lib/i18n/translations.ts` e
  `apps/frontend/i18n/*` — revisar strings e completar o que faltar.
- `apps/backend/app/prompts/templates.py` → `LANGUAGE_NAMES` mapeia `pt` para
  "Brazilian Portuguese"; confirmar que o idioma de conteúdo padrão é `pt`.
- Datas: conferir o formato exibido (`apps/frontend/lib/format-date.ts`).
- Textos gerados: carta de apresentação e mensagem de outreach em pt-BR.

**Aceite:** interface sem termos de pt-PT ("ficheiro", "ecrã", "utilizador") e sem strings
não traduzidas; PDF e DOCX com datas no formato brasileiro.

**Implementada:** varredura do `pt-BR.json` sem termos de pt-PT ("Template" virou "Modelo");
`LANGUAGE_NAMES["pt"]` confirmado como "Brazilian Portuguese" e `pt` presente em
`SUPPORTED_LANGUAGES`; nova linha nos prompts de personalização, carta, outreach e follow-up
proibindo português de Portugal; datas em pt-BR: `format_date_range(..., language)` no DOCX
(router passa `get_content_language()`) e `lib/utils/date-range.ts` no PDF (aplica aos `years` do
currículo antes dos templates), com meses em português e "Atual". O idioma de conteúdo padrão
continua `en` (comportamento upstream); o pt-BR é escolhido em Configurações.

### 6.6 `feat/edit-mode-pt-br` — Edit Mode detecta o idioma do currículo e sugere em pt-BR

**Objetivo:** no **Resume Builder (Modo Edição)**, as sugestões de texto geradas por IA
(enriquecimento, reescrita de bullets, regeneração) saem no idioma principal do currículo
carregado. Currículo em pt-BR → sugestões em pt-BR; currículo em inglês → sugestões em inglês.

**Contexto (já existe):** o backend já tem a infra de idioma pronta — `LANGUAGE_NAMES` e
`get_language_name()` em `prompts/templates.py`, e `output_language` em todos os serviços de
sugestão (`routers/enrichment.py`, `services/writing_loop.py`, `keyword_forcing.py`,
`improver.py`, `cover_letter.py`, `interview_prep.py`, `resume_wizard.py`). O schema de
enriquecimento usa `output_language: str = "en"` como padrão.

**Onde mexer:**
- Detecção de idioma (novo): `services/language_detection.py`. Como não há lib de detecção
  instalada, usar heurística sobre o texto real do currículo (summary + bullets): caracteres
  acentuados específicos do português (`ç`, `ã`, `õ`, `á/é/í/ó/ú`) + stopwords pt-BR
  ("desenvolvimento", "e", "com", "para", "em", "que", "não") vs. padrões de inglês. Evitar
  confundir com o campo `additional.languages` (idiomas falados do candidato), que não é o
  idioma do conteúdo.
- Backend: `routers/enrichment.py` e `services/writing_loop.py` passam a usar o idioma
  detectado como **fallback** quando `output_language` não foi definido explicitamente
  (ex.: usuário não configurou em Settings ou não enviou o parâmetro).
- Frontend: o modal de enriquecimento (`components/enrichment/`), o painel de escrita
  (`components/builder/writing-panel.tsx`) e o wizard de regeneração (`components/builder/regenerate-*`)
  enviam o idioma detectado (ou deixam o backend detectar).
- "Modo Edição" é o `t('builder.editMode')` usado em `components/builder/resume-builder.tsx`
  (~linha 1725) quando há um `resumeId`.

**Regra:** a configuração explícita de idioma (Settings / `LanguageConfig`) continua
prevalecendo sobre a detecção automática; a detecção só entra quando não há escolha explícita.

**Aceite:** carregar o CV em pt-BR e usar as sugestões de IA do Edit Mode gera texto em
pt-BR; carregar o CV em inglês gera em inglês; escolha explícita de idioma em Settings segue
respeitada; o teste de "fact violations" continua limpo.

---

## 7. Mapa do código (o que importa)

### Backend (`apps/backend/app/`)

| Arquivo | Papel |
|---|---|
| `main.py` | FastAPI, registro dos routers, prefixo `/api/v1` |
| `config.py` | Settings (env + `config.json`), chaves criptografadas |
| `llm.py` | LiteLLM Router, `get_model_name`, `get_safe_max_tokens`, `complete_json` |
| `models.py` | Tabelas: `resumes`, `jobs`, `improvements`, `tailoring_previews`, `applications`, `api_keys`, `queue_items` |
| `pdf.py` | Render do PDF via Playwright/Chrome |
| `prompts/templates.py` | Parse do currículo, extração de keywords, 4 estratégias, carta, entrevista |
| `prompts/writing.py` | Rubrica de escrita, reescrita de bullets, posicionamento de keywords |
| `services/parser.py` | PDF/DOCX → Markdown → JSON estruturado |
| `services/improver.py` | `extract_job_keywords`, `generate_resume_diffs`, `apply_diffs`, `verify_diff_result` |
| `services/refiner.py` | `refine_resume` (3 passes), `analyze_keyword_gaps`, `inject_keywords`, `validate_master_alignment` |
| `services/resume_preservation.py` | Contrato anti-invenção: `finalize_ai_resume`, campos protegidos, números novos |
| `services/writing_quality.py` | Fact checking determinístico, `fact_violations` |
| `services/keyword_forcing.py` | Atestação de keywords (base da entrevista de lacunas) |
| `services/ats.py` | Score ATS: keyword 40%, skills 20%, título 15%, seções 15%, datas 10% |
| `services/ats_parse/` | O que um ATS extrai do PDF gerado (pdfminer) |
| `services/tailor_selection.py` | Seleção de bullets + ajuste ao limite de páginas |
| `routers/resumes.py` | `execute_tailoring_pipeline` e todos os endpoints de currículo |

### Frontend (`apps/frontend/`)

| Caminho | Papel |
|---|---|
| `app/(default)/tailor/page.tsx` | Tela de tailoring (upload + vaga + revisão) |
| `app/(default)/builder/page.tsx` | Editor e preview ao vivo |
| `app/(default)/resumes/[id]/page.tsx` | Visualização do currículo |
| `app/(default)/settings/page.tsx` | Provedor de IA |
| `components/tailor/*` | `ats-score-card`, `keyword-forcing-panel`, `diff-preview-modal`, `tailor-progress` |
| `lib/api/*` | Clientes de API por domínio |
| `i18n/`, `lib/i18n/` | Traduções |

Estilo do projeto: formulários e textos em **português do Brasil**, código e identificadores
em inglês, seguindo o padrão do upstream.

---

## 8. Convenções

- **Branch por melhoria:** `feat/job-url`, `feat/gap-interview`, `feat/docx-export`,
  `feat/wp-prompt-pack`, `feat/pt-br-review`, `feat/edit-mode-pt-br`. Correções de base em `fix/llm-token-budget`.
- **Commit:** mensagem em inglês, imperativo, curta; corpo explicando o "por quê" quando não
  for óbvio.
- **Antes de commitar:** rodar os testes e o lint (seção 9).
- **Sincronização:** `git fetch upstream && git merge upstream/main` na `main` do fork, e
  rebase das branches de feature por cima. Nunca reescrever histórico já enviado.
- **Não modificar** arquivos do upstream sem necessidade real; melhorias ficam em arquivos
  novos ou em trechos pequenos e justificados — isso reduz conflito no merge futuro.
- **Não alterar** `HOST` para `0.0.0.0`: o uso é local e a API não tem autenticação.

---

## 9. Comandos úteis

```powershell
# Backend — dentro de apps/backend
uv run app                          # servidor de desenvolvimento
uv run pytest -m "not eval"         # suíte (evals de LLM ficam de fora)
uv run pytest -m eval               # evals de prompt (consomem tokens)
uv run ruff check .                 # lint
uv run ruff format .                # formatação

# Frontend — dentro de apps/frontend
npm run dev                         # servidor de desenvolvimento
npm run build                       # build de produção
npm run typecheck                   # tsc --noEmit
npm run lint                        # oxlint + oxfmt check
npm run test                        # vitest

# Git
git fetch upstream && git merge upstream/main
git switch -c feat/nome-da-melhoria
```

---

## 10. Troubleshooting

| Sintoma | Causa provável | Solução |
|---|---|---|
| `EBADENGINE` no `npm install` | Node 24 vs 26 do `.nvmrc` | Ignorar. Se quebrar, instalar Node 26 via `fnm` |
| Upload do PDF falha sem mensagem clara | Sem provedor de IA configurado | Conferir `LLM_*` no `.env` e `/api/v1/health` |
| Erro de validação ao parsear currículo longo | Corte de 4096 tokens (seção 5.1) | Aplicar a correção de 5.1 |
| PDF não gera | Chrome/Edge não encontrado | Conferir seção 4.5 e `pdf.py` (`_find_chromium_executable`) |
| `ERR_CONNECTION_REFUSED` em :3000 | Backend não está rodando | Subir `uv run app` no terminal 1 |
| Porta ocupada | Outra instância | `PORT=4000` no `.env` / `npm run dev -- -p 3001` |
| Chave inválida após trocar de modelo | `config.json` com provider antigo | Limpar as `LLM_*` do `.env` ou reconfigurar em Settings |

---

## 11. Privacidade, dados e licença

**Dados pessoais (nunca commitar):**
- `apps/backend/data/` → SQLite, currículos, `config.json`, `.secret_key`
- `jobs/` → descrições de vaga salvas
- `.env`

Todos já estão no `.gitignore` do upstream. **Faça backup de `data/`**: se `data/.secret_key`
for perdida, as chaves de API salvas não podem ser descriptografadas.

**Licença:** o upstream é **Apache-2.0**. O fork pode ser usado, modificado e redistribuído
desde que: (a) o `LICENSE` seja mantido, (b) os avisos de copyright sejam preservados e
(c) alterações sejam indicadas. Se o fork for publicado com distribuição de binário,
adicionar um `NOTICE` com a atribuição ao projeto original.

**Provedor:** o OpenCode Go declara-se destinado a agentes de código. O uso aqui é pessoal e de
baixo volume, mas não é o caso de uso documentado. O plano B dentro das regras é o modo `agent`
com MCP (`resume-matcher-mcp`), em que o app não faz chamadas de modelo.

---

## 12. Critérios de conclusão

Considere a entrega concluída quando:

- [ ] Fork criado, clone local funcionando, `origin` e `upstream` configurados
- [ ] `uv sync` e `npm install` sem erro bloqueante
- [ ] Aplicação abre em `http://localhost:3000` e o backend responde em `/api/v1/health`
- [ ] Provedor Go responde a uma chamada real de teste
- [ ] Correção de 4096 tokens aplicada e validada com currículo longo
- [ ] Ciclo completo validado: upload → vaga → tailoring → revisão → PDF
- [x] `feat/job-url` concluída
- [x] `feat/gap-interview` concluída
- [x] `feat/docx-export` concluída
- [x] `feat/wp-prompt-pack` concluída
- [x] `feat/pt-br-review` concluída
- [ ] `feat/edit-mode-pt-br` concluída
- [ ] `start.ps1`, `sync-upstream.ps1` e `setup.ps1` funcionando
- [ ] README do fork com instruções próprias e atribuição ao projeto original

---

## 13. O que NÃO fazer

- Não adicionar hospedagem, deploy, Docker Compose de produção ou qualquer exposição pública.
- Não remover nem contornar o contrato anti-invenção (`resume_preservation`, `writing_quality`,
  atestação de keywords).
- Não commitar `data/`, `jobs/` ou `.env`.
- Não reescrever o backend em outra linguagem nem trocar o banco: o objetivo é evoluir o fork,
  não reescrevê-lo.
- Não usar `git push --force` na `main` do fork — quebra a sincronização com o upstream.
- Não alterar as 4 estratégias de escrita existentes (`nudge`, `keywords`, `full`, `heavy`)
  sem justificativa; elas são a base do comportamento atual.
