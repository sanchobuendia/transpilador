from __future__ import annotations

from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool

from transpiler_agent.security_callbacks import (
    hydrate_args_from_context,
    require_allowed_tool,
    require_fields,
    sanitize_or_raise,
    validate_tool_result,
)


ALLOWED_TOOL_NAMES = {"deliver_via_github_mcp_tool"}


def before_model_callback(
    model_request: Any = None,
    callback_context: CallbackContext | None = None,
    llm_request: Any = None,
    **_: Any,
) -> Any:
    sanitize_or_raise(
        llm_request if llm_request is not None else model_request,
        "Prompt injection detectado antes da chamada ao modelo.",
        "Conteudo suspeito bloqueado antes da chamada ao modelo do publisher",
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
        f"Conteudo suspeito bloqueado antes da execucao da tool {tool.name} no publisher",
    )
    sanitized_args = hydrate_args_from_context(
        sanitized_args,
        tool_context or callback_context,
        ("spec_json", "blueprint_json", "model_selection_json", "generation_json"),
    )
    require_allowed_tool(tool.name, ALLOWED_TOOL_NAMES)
    require_fields(
        tool.name,
        sanitized_args,
        ("spec_json", "blueprint_json", "model_selection_json", "generation_json"),
    )
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
        f"Saida suspeita bloqueada apos tool {tool.name} no publisher",
    ))
    if isinstance(validated, dict) and "status" not in validated:
        raise ValueError("deliver_via_github_mcp_tool deveria retornar status.")
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
        "Saida suspeita bloqueada apos resposta do modelo do publisher",
    )
