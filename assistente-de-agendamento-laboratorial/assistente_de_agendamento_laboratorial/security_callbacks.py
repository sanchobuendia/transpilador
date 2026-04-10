"""Callbacks de seguranca e validacao para o runtime gerado."""
from __future__ import annotations

import json
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool

ENTITIES: list[str] = ['PERSON_NAME', 'CPF', 'PHONE', 'EMAIL', 'ADDRESS']
SUSPICIOUS_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"call\s+this\s+tool", re.IGNORECASE),
    re.compile(r"execute\s+tool", re.IGNORECASE),
    re.compile(r"<\s*tool", re.IGNORECASE),
]
ALLOWED_TOOL_NAMES = set(["create_appointment", "extract_request_data", "get_appointment", "list_appointments", "search_exam_codes"])

PATTERNS = {
    "CPF": re.compile(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b"),
    "PHONE": re.compile(r"\b(\+?55[\s-]?)?(\(?\d{2}\)?[\s-]?)?9?\d{4}[-\s]?\d{4}\b"),
    "EMAIL": re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    "ADDRESS": re.compile(r"\b(rua|avenida|av|alameda|praca)[.,]?\s+[\w\s]{3,50}\b", re.IGNORECASE),
    "PERSON_NAME": re.compile(r"\b([A-Z][a-z]{2,})(\s+[A-Z][a-z]{2,}){1,4}\b"),
}


def _mask_pii(value: Any) -> Any:
    if isinstance(value, str):
        masked = value
        for entity in ENTITIES:
            pattern = PATTERNS.get(entity)
            if pattern:
                masked = pattern.sub(f"[{entity}_REDACTED]", masked)
        return masked
    if isinstance(value, dict):
        return {key: _mask_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_pii(item) for item in value]
    return value


def _contains_injection(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in SUSPICIOUS_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_injection(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_injection(item) for item in value)
    return False


def _validate_tool_args(tool_name: str, args: dict[str, Any]) -> None:
    if ALLOWED_TOOL_NAMES and tool_name not in ALLOWED_TOOL_NAMES:
        raise ValueError(f"Tool nao permitida pelo runtime: {tool_name}")
    if not isinstance(args, dict):
        raise ValueError("Args da tool devem ser um objeto JSON.")


def _validate_tool_result(tool_name: str, result: Any) -> Any:
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    if _contains_injection(text):
        raise ValueError(f"Possivel prompt injection detectado na saida da tool {tool_name}")
    return result


def _sanitize_model_payload(payload: Any) -> Any:
    if _contains_injection(payload):
        raise ValueError("Prompt injection detectado antes de chamar o modelo.")
    return _mask_pii(payload)


def before_model_callback(
    model_request: Any = None,
    callback_context: CallbackContext | None = None,
    llm_request: Any = None,
    **_: Any,
) -> Any:
    _sanitize_model_payload(llm_request if llm_request is not None else model_request)
    return None


def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    callback_context: CallbackContext | None = None,
    tool_context: CallbackContext | None = None,
    **_: Any,
) -> dict[str, Any] | None:
    sanitized_args = _sanitize_model_payload(args)
    _validate_tool_args(tool.name, sanitized_args)
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
    sanitized_result = _mask_pii(response)
    return _validate_tool_result(tool.name, sanitized_result)


def after_model_callback(
    model_response: Any = None,
    callback_context: CallbackContext | None = None,
    llm_response: Any = None,
    **_: Any,
) -> Any:
    response = llm_response if llm_response is not None else model_response
    if _contains_injection(response):
        raise ValueError("Saida suspeita do modelo bloqueada pela camada de seguranca.")
    return _mask_pii(response)
