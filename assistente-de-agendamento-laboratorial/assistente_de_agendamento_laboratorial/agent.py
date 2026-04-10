from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from config import Config
from .logging_utils import configure_logging, get_logger
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from mcp.client.sse import SseServerParams
from .tools import create_appointment, get_appointment, list_appointments
from .security_callbacks import after_model_callback, after_tool_callback, before_model_callback, before_tool_callback

configure_logging()
logger = get_logger(__name__)

root_agent = LlmAgent(
    name="assistente_de_agendamento_laboratorial",
    model=LiteLlm(
        model=Config.BEDROCK_CLAUDE_MODEL or "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        temperature=Config.TEMPERATURE,
        max_tokens=Config.MAX_TOKENS,
    ),
    description="Assistente de Agendamento Laboratorial",
    instruction="""Voce e um agente especializado. Objetivo: Receber a imagem de um pedido medico, extrair os exames solicitados via OCR MCP, consultar os codigos correspondentes via RAG MCP, enviar a solicitacao para uma API FastAPI de agendamento e exibir o resultado final no terminal.

THINK:
Antes de executar tools, revise mentalmente o fluxo inteiro, confirme quais dados podem ser sensiveis e propague apenas informacoes apropriadas para cada etapa. Siga os contratos declarados na spec e nao invente comportamentos de componentes.

Siga o fluxo abaixo sem inventar dados:
1. Interaja com o componente `ocr` usando as tools disponiveis: `extract_request_data`.
2. Interaja com o componente `rag` usando as tools disponiveis: `search_exam_codes`.
3. Interaja com o componente `scheduling_api` usando as tools disponiveis: `create_appointment`, `get_appointment`, `list_appointments`.
4. Responda no formato esperado pela interface `cli`.

Se alguma etapa falhar, explique o erro com clareza.
""",
    tools=[
    MCPToolset(connection_params=SseServerParams(url="http://ocr:8001/sse")),
    MCPToolset(connection_params=SseServerParams(url="http://rag:8002/sse")),
] + [create_appointment, get_appointment, list_appointments],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
)
