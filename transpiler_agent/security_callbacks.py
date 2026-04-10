from __future__ import annotations

import json
import re
from typing import Any

from transpiler_agent.logging_utils import get_logger


logger = get_logger(__name__)

SUSPICIOUS_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"call\s+this\s+tool", re.IGNORECASE),
    re.compile(r"execute\s+tool", re.IGNORECASE),
    re.compile(r"<\s*tool", re.IGNORECASE),
]


def contains_injection(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in SUSPICIOUS_PATTERNS)
    if isinstance(value, dict):
        return any(contains_injection(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_injection(item) for item in value)
    return False


def sanitize_strings(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {key: sanitize_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_strings(item) for item in value]
    return value


def sanitize_or_raise(value: Any, error_message: str, log_message: str) -> Any:
    sanitized = sanitize_strings(value)
    if contains_injection(sanitized):
        logger.warning(log_message)
        raise ValueError(error_message)
    return sanitized


def require_fields(tool_name: str, args: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in args or args[field] in ("", None)]
    if missing:
        raise ValueError(f"{tool_name} exige campos obrigatorios: {missing}")


def require_allowed_tool(tool_name: str, allowed_tool_names: set[str]) -> None:
    if tool_name not in allowed_tool_names:
        raise ValueError(f"Tool nao permitida no transpilador: {tool_name}")


def validate_tool_result(tool_name: str, result: Any) -> Any:
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    if contains_injection(text):
        raise ValueError(f"Possivel prompt injection detectado na saida da tool {tool_name}")
    return result


def hydrate_args_from_context(
    args: dict[str, Any],
    context: Any,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(args, dict) or context is None:
        return args

    state = getattr(context, "state", None)
    if not state:
        return args

    hydrated = dict(args)
    for field in fields:
        if hydrated.get(field) not in ("", None):
            continue
        value = state.get(field)
        if value not in ("", None):
            hydrated[field] = value
    return hydrated
