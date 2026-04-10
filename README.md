# Transpilador de Agentes ADK

Transpilador em Python que recebe uma especificação JSON de um agente e gera um projeto executável baseado exclusivamente no Google ADK. O foco do caso de uso é um assistente CLI para agendamento laboratorial com OCR via MCP SSE, consulta de exames via RAG MCP SSE, API FastAPI de agendamento e camada de mascaramento de PII. O LLM padrão do transpilador e do runtime gerado usa Anthropic Claude via AWS Bedrock.

## Escopo do repositório

Este repositório versiona o transpilador, não o runtime final pronto.

O que existe aqui:

- CLI do transpilador em [`transpiler.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler.py)
- pacote ADK do transpilador em [`transpiler_agent`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent)
- catálogo de modelos Bedrock em [`catalog/models_catalog.json`](/Users/aurelianosancho/Documents/GitHub/transpilador/catalog/models_catalog.json)
- spec de exemplo em [`agent_spec.json`](/Users/aurelianosancho/Documents/GitHub/transpilador/agent_spec.json)
- imagem fictícia de teste em [`sample_medical_request.png`](/Users/aurelianosancho/Documents/GitHub/transpilador/sample_medical_request.png)
- testes unitários em [`tests/test_transpiler.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/tests/test_transpiler.py)

O que o transpilador gera no diretório de saída:

- pacote ADK do agente final
- `services/ocr` com servidor MCP via SSE
- `services/rag` com servidor MCP via SSE
- `services/scheduling_api` com FastAPI
- `docker-compose.yml` do runtime final
- dataset fictício com 100 exames
- README do projeto gerado

## Relação com o desafio

O desenho do projeto segue o enunciado do desafio:

- o input é uma spec JSON
- o código gerado usa Google ADK
- o runtime final gerado contém OCR MCP SSE, RAG MCP SSE, FastAPI e Docker Compose
- há camada de sanitização de PII e validação básica contra prompt injection
- o fluxo-alvo é CLI -> OCR -> PII -> RAG -> agendamento -> saída terminal

Ponto importante: o `docker-compose.yml` da raiz não representa o ambiente do transpilador e sim o padrão de compose que deve existir no projeto gerado. O compose relevante para a entrega do desafio é o que o transpilador escreve no diretório de saída.

## Arquitetura do transpilador

O orquestrador principal está em [`transpiler_agent/agent.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/agent.py) e usa um `SequentialAgent` com seis subagentes:

1. `spec_analyst`: valida a spec e deriva o blueprint
2. `project_planner`: monta o plano por domínios
3. `model_selector`: escolhe o modelo do catálogo
4. `project_generator`: gera o repositório final
5. `project_reviewer`: revisa a estrutura e sintaxe do projeto gerado
6. `publisher`: publica no GitHub via GitHub MCP quando habilitado

As tools centrais são:

- [`transpiler_agent/tools/spec_tool.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/tools/spec_tool.py): valida spec e produz blueprint
- [`transpiler_agent/tools/plan_tool.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/tools/plan_tool.py): cria workstreams por domínio
- [`transpiler_agent/tools/model_selector_tool.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/tools/model_selector_tool.py): escolhe modelo por complexidade
- [`transpiler_agent/tools/codegen_tool.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/tools/codegen_tool.py): gera arquivos do runtime
- [`transpiler_agent/tools/review_tool.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/tools/review_tool.py): revisa estrutura e sintaxe
- [`transpiler_agent/tools/git_tool.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/tools/git_tool.py): entrega opcional via GitHub MCP

## Fluxo do caso de uso gerado

Quando a spec solicita o cenário laboratorial, o runtime gerado segue este fluxo:

1. recebe o caminho da imagem no CLI
2. chama `extract_request_data` no servidor MCP de OCR via SSE
3. mascara PII antes de encaminhar conteúdo ao modelo ou às tools
4. chama `search_exam_codes` no servidor MCP de RAG via SSE
5. envia os exames normalizados para a FastAPI de agendamento
6. retorna no terminal os exames, códigos e status da solicitação

## Estrutura do repositório

```text
transpilador/
├── transpiler.py
├── agent_spec.json
├── sample_medical_request.png
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
├── catalog/
│   └── models_catalog.json
├── transpiler_agent/
│   ├── agent.py
│   ├── root_prompt.md
│   ├── logging_utils.py
│   ├── security_callbacks.py
│   ├── tools/
│   │   ├── spec_tool.py
│   │   ├── plan_tool.py
│   │   ├── model_selector_tool.py
│   │   ├── codegen_tool.py
│   │   ├── review_tool.py
│   │   ├── pipeline_tool.py
│   │   └── git_tool.py
│   └── subagents/
│       ├── spec_analyst/
│       ├── project_planner/
│       ├── model_selector/
│       ├── project_generator/
│       ├── project_reviewer/
│       └── publisher/
└── tests/
    └── test_transpiler.py
```

## Como executar o transpilador

### 1. Pré-requisitos

- Python 3.11+
- `pip`
- acesso às bibliotecas listadas em [`requirements.txt`](/Users/aurelianosancho/Documents/GitHub/transpilador/requirements.txt)
- credenciais AWS com permissão para invocar modelos no Bedrock
- Docker instalado se você quiser usar a entrega opcional via GitHub MCP ou testar o runtime gerado em containers

### 2. Configurar ambiente

```bash
cp .env.example .env
pip install -r requirements.txt
```

Além das variáveis já presentes em [`.env.example`](/Users/aurelianosancho/Documents/GitHub/transpilador/.env.example), o transpilador exige `DATABASE_URL` no ambiente porque usa `DatabaseSessionService` do Google ADK em [`transpiler.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler.py). O modelo default é `us.anthropic.claude-haiku-4-5-20251001-v1:0`.

Para PostgreSQL, o transpilador aceita tanto `postgresql://...` quanto `postgresql+asyncpg://...`. Internamente, URLs PostgreSQL sem driver explícito são normalizadas para `asyncpg`.

Exemplo mínimo do `.env`:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
MODEL_TEMPERATURE=0.1
MODEL_MAX_TOKENS=4096
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=transpilador
GITHUB_PERSONAL_ACCESS_TOKEN=
GITHUB_REPO=owner/
GITHUB_BASE_BRANCH=main
GITHUB_MCP_DOCKER_IMAGE=ghcr.io/github/github-mcp-server
DATABASE_URL=...
```

### 3. Rodar o transpilador

```bash
python transpiler.py --spec agent_spec.json
```

Opções disponíveis:

```text
--spec   <path>   Caminho para o JSON de especificação
--output <path>   Diretório de saída. Default: derivado do nome do agente na spec
--dry-run         Analisa a spec sem gerar arquivos
```

Exemplos:

```bash
python transpiler.py --spec agent_spec.json
python transpiler.py --spec agent_spec.json --output ./out/agente-lab
python transpiler.py --spec agent_spec.json --dry-run
```

## O que é gerado

Para a spec de exemplo, o transpilador gera um projeto em um diretório derivado do nome do agente. Neste caso, algo como `./assistente-de-agendamento-laboratorial/`, com esta forma:

```text
assistente-de-agendamento-laboratorial/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
├── assistente_de_agendamento_laboratorial/
│   ├── __init__.py
│   ├── agent.py
│   ├── tools.py
│   ├── logging_utils.py
│   └── security_callbacks.py
└── services/
    ├── ocr/
    │   ├── server.py
    │   ├── requirements.txt
    │   └── Dockerfile
    ├── rag/
    │   ├── server.py
    │   ├── exam_seed.json
    │   ├── requirements.txt
    │   └── Dockerfile
    └── scheduling_api/
        ├── main.py
        ├── requirements.txt
        └── Dockerfile
```

## Como executar o runtime gerado

Depois da geração:

```bash
cd assistente-de-agendamento-laboratorial
cp .env.example .env
docker compose up --build
```

Serviços esperados:

- OCR MCP SSE em `http://localhost:8001/sse`
- RAG MCP SSE em `http://localhost:8002/sse`
- FastAPI em `http://localhost:8000`
- Swagger da API em `http://localhost:8000/docs`

O agente gerado se conecta aos MCPs usando `MCPToolset` com `SseServerParams`, apontando para os serviços internos definidos no `docker-compose.yml` gerado. O runtime gerado também usa Anthropic Claude via AWS Bedrock com `LiteLlm`.

Também é possível executar o agente gerado localmente, sem Compose, desde que as dependências e serviços estejam disponíveis:

```bash
cd assistente-de-agendamento-laboratorial
pip install -r requirements.txt
adk run .
```

## Tracing com LangSmith

O transpilador suporta tracing opcional com LangSmith quando estas variaveis estiverem definidas:

- `LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`

Quando habilitado, a execucao principal do transpilador e as tools centrais do pipeline sao registradas no projeto configurado.

## OCR, RAG e dados fictícios

### OCR

O servidor de OCR gerado usa Google Document AI quando as variáveis necessárias estão presentes. Se a configuração de GCP estiver ausente ou falhar, o código gerado cai em um fallback mock para demonstrar o pipeline.

### RAG

O servidor de RAG gerado foi desenhado para consultar Vertex AI Search / Discovery Engine. O projeto gerado também inclui [`exam_seed.json`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/tools/codegen_tool.py#L764) com 100 exames fictícios, mas o carregamento desse dataset para um datastore gerenciado não é automatizado pelo transpilador atual.

### FastAPI

A API de agendamento é gerada com endpoints:

- `GET /health`
- `POST /appointments`
- `GET /appointments`
- `GET /appointments/{appointment_id}`

O contrato fica automaticamente documentado em `/docs`.

## Segurança

Há duas camadas de segurança no projeto:

- no transpilador: [`transpiler_agent/security_callbacks.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler_agent/security_callbacks.py) sanitiza entradas e bloqueia padrões simples de prompt injection
- no runtime gerado: `security_callbacks.py` mascara entidades como `PERSON_NAME`, `CPF`, `PHONE`, `EMAIL` e `ADDRESS` antes de chamadas ao modelo e após respostas de tools

O OCR gerado também já devolve `sanitized_text` além do texto bruto.

## Testes

Os testes unitários estão em [`tests/test_transpiler.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/tests/test_transpiler.py) e cobrem:

- derivação do blueprint
- planejamento
- seleção de modelo
- geração de arquivos
- validação sintática do código gerado
- revisão estrutural do projeto gerado
- composição do agente raiz

Execução:

```bash
python -m pytest tests/ -v
```

## Análise de aderência ao desafio

### Atendido no código atual

- transpilador que recebe JSON e gera projeto ADK
- caso de uso laboratorial refletido na spec de exemplo
- geração de MCP OCR via SSE
- geração de MCP RAG via SSE
- geração de API FastAPI com Swagger
- geração de `docker-compose.yml` no runtime final
- dataset fictício com 100 exames
- mascaramento de PII no runtime gerado
- testes unitários de geração e revisão

### Parcial ou dependente de configuração externa

- OCR real depende de Google Document AI configurado
- RAG real depende de Vertex AI Search / Discovery Engine configurado
- execução end-to-end real depende de provisionar serviços GCP e popular o datastore do RAG
- publicação GitHub depende de token e Docker disponíveis

### Gaps atuais do repositório

- o `docker-compose.yml` versionado na raiz não é o ambiente correto do transpilador e hoje referencia diretórios `services/` que não existem na raiz
- [`.env.example`](/Users/aurelianosancho/Documents/GitHub/transpilador/.env.example) não documenta `DATABASE_URL`, embora [`transpiler.py`](/Users/aurelianosancho/Documents/GitHub/transpilador/transpiler.py) exija essa variável
- o README do projeto gerado não substitui a necessidade de evidências versionadas, como logs, capturas da CLI e screenshots do Swagger
- o seed de exames é gerado, mas a carga automatizada desse conteúdo em um backend real de RAG não está implementada

## Evidências esperadas para submissão

Para fechar a entrega do desafio, este repositório ainda deve incluir ou anexar evidências como:

- log de execução do transpilador
- log de `docker compose up` do projeto gerado
- captura da execução CLI do agente final
- captura de `http://localhost:8000/docs`
- exemplo do payload de agendamento confirmado

## Transparência e uso de IA

### Abordagem adotada

A solução foi estruturada com IA como assistente de programação e apoio à iteração de arquitetura, mantendo validação manual do código gerado, testes unitários e revisão de consistência estrutural do projeto final.

### Estratégia de orquestração

O transpilador usa orquestração sequencial por subagentes especializados. Cada etapa produz contexto estruturado para a etapa seguinte: spec -> blueprint -> plano -> seleção de modelo -> geração -> revisão -> publicação opcional.

O runtime gerado para o caso laboratorial também segue fluxo sequencial: OCR -> sanitização de PII -> RAG -> agendamento -> resposta em terminal.

### Referências consultadas

- Google ADK
- MCP Python SDK
- FastAPI
- Google Cloud Document AI
- Google Cloud Vertex AI Search / Discovery Engine
