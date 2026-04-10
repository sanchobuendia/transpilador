from __future__ import annotations

from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool

from transpiler_agent.security_callbacks import (
    require_allowed_tool,
    sanitize_or_raise,
    validate_tool_result,
)


ALLOWED_TOOL_NAMES = {"analyze_spec_tool"}


def before_model_callback(
    model_request: Any = None,
    callback_context: CallbackContext | None = None,
    llm_request: Any = None,
    **_: Any,
) -> Any:
    sanitize_or_raise(
        llm_request if llm_request is not None else model_request,
        "Prompt injection detectado antes da chamada ao modelo.",
        "Conteudo suspeito bloqueado antes da chamada ao modelo do spec_analyst",
    )
    return None


def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    callback_context: CallbackContext | None = None,
    tool_context: CallbackContext | None = None,
    **_: Any,
) -> dict[str, Any] | None:
    sanitized_args = sanitize_or_raise(
        args,
        f"Prompt injection detectado antes da execucao da tool {tool.name}.",
        f"Conteudo suspeito bloqueado antes da execucao da tool {tool.name} no spec_analyst",
    )
    require_allowed_tool(tool.name, ALLOWED_TOOL_NAMES)
    spec_json = sanitized_args.get("spec_json")
    if not isinstance(spec_json, str) or not spec_json.strip():
        raise ValueError("analyze_spec_tool exige spec_json nao vazio.")
    return sanitized_args


def after_tool_callback(
    tool: BaseTool,
    result: Any = None,
    args: dict[str, Any] | None = None,
    callback_context: CallbackContext | None = None,
    tool_context: CallbackContext | None = None,
    tool_response: Any = None,
    **_: Any,
) -> Any:
    response = tool_response if tool_response is not None else result
    validated = validate_tool_result(tool.name, sanitize_or_raise(
        response,
        f"Saida suspeita detectada na tool {tool.name}.",
        f"Saida suspeita bloqueada apos tool {tool.name} no spec_analyst",
    ))
    if isinstance(validated, dict) and validated.get("status") == "success" and "blueprint" not in validated:
        raise ValueError("analyze_spec_tool deveria retornar blueprint no resultado de sucesso.")
    return validated


def after_model_callback(
    model_response: Any = None,
    callback_context: CallbackContext | None = None,
    llm_response: Any = None,
    **_: Any,
) -> Any:
    return sanitize_or_raise(
        llm_response if llm_response is not None else model_response,
        "Saida suspeita do modelo bloqueada pela camada de seguranca.",
        "Saida suspeita bloqueada apos resposta do modelo do spec_analyst",
    )
