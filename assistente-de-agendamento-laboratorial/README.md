# Assistente de Agendamento Laboratorial

Projeto gerado automaticamente pelo transpilador ADK.

## Objetivo
Receber a imagem de um pedido medico, extrair os exames solicitados via OCR MCP, consultar os codigos correspondentes via RAG MCP, enviar a solicitacao para uma API FastAPI de agendamento e exibir o resultado final no terminal.

## Modelo
`us.anthropic.claude-haiku-4-5-20251001-v1:0` - tarefa envolve processamento de imagem — necessita modelo multimodal; 5 ferramentas requerem orquestração moderada; inclui recuperacao de contexto externo ou busca semantica

## Componentes gerados
- `ocr`: `mcp` via `sse`
- `rag`: `mcp` via `sse`
- `scheduling_api`: `fastapi` via `http`

## Como subir o ambiente

```bash
cp .env.example .env
docker compose up --build
```

## Como executar o agente localmente

```bash
pip install -r requirements.txt
adk run .
```
