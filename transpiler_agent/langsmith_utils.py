from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Callable

from transpiler_agent.logging_utils import get_logger

logger = get_logger(__name__)

try:
    import langsmith as ls
    from langsmith import traceable as _langsmith_traceable
except ImportError:  # pragma: no cover
    ls = None
    _langsmith_traceable = None


def is_langsmith_enabled() -> bool:
    return (
        ls is not None
        and os.environ.get("LANGSMITH_TRACING", "").strip().lower() == "true"
        and bool(os.environ.get("LANGSMITH_API_KEY", "").strip())
    )


def configure_langsmith() -> None:
    if is_langsmith_enabled():
        logger.info(
            "LangSmith tracing habilitado para o projeto %s",
            os.environ.get("LANGSMITH_PROJECT", "default"),
        )


@contextmanager
def tracing_context(project_name: str | None = None, metadata: dict[str, Any] | None = None):
    if not is_langsmith_enabled():
        yield
        return

    with ls.tracing_context(
        enabled=True,
        project_name=project_name or os.environ.get("LANGSMITH_PROJECT"),
        metadata=metadata or {},
    ):
        yield


def traceable(**kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if _langsmith_traceable is None:
            return func
        return _langsmith_traceable(**kwargs)(func)

    return decorator
