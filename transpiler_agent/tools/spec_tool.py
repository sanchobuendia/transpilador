"""Tool ADK: analisa a spec e produz um blueprint de geracao."""
from __future__ import annotations

import json
import re
from copy import deepcopy

from transpiler_agent.langsmith_utils import traceable
from transpiler_agent.logging_utils import get_logger


logger = get_logger(__name__)

DEFAULT_PLATFORM = {
    "cloud": "gcp",
    "architecture_preference": "google_managed_services_first",
}

DEFAULT_INTERFACE = "cli"
DEFAULT_COMPONENT_KIND = "service"
DEFAULT_TRANSPORT = "unspecified"


@traceable(name="analyze_spec_tool", run_type="tool")
def analyze_spec_tool(spec_json: str) -> dict:
    """Valida a spec e deriva um blueprint do runtime a ser gerado."""
    try:
        spec = json.loads(spec_json)
    except Exception as e:
        logger.exception("JSON invalido recebido em analyze_spec_tool")
        return {"status": "error", "error": f"JSON invalido: {e}"}

    missing = [field for field in ("name", "goal") if not spec.get(field)]
    if missing:
        return {
            "status": "error",
            "error": f"Campos obrigatorios ausentes na spec: {missing}",
        }

    components = _derive_components(spec)
    if not components:
        return {
            "status": "error",
            "error": (
                "Nao foi possivel derivar componentes para o runtime. "
                "Informe `components`/`services` na spec ou descreva a arquitetura de forma mais explicita."
            ),
        }

    blueprint = {
        "agent_name": spec["name"],
        "goal": spec["goal"],
        "platform": _extract_platform(spec),
        "interface": _extract_interface_type(spec),
        "components": components,
        "flow": _extract_flow(spec, components),
        "estimated_tool_count": sum(len(component.get("generated_tools", [])) for component in components),
        "pii_enabled": bool(spec.get("guardrails", {}).get("pii", {}).get("enabled")),
        "pii_entities": spec.get("guardrails", {}).get("pii", {}).get("entities", []),
    }
    logger.info("Blueprint derivado para agente '%s'", spec["name"])
    logger.debug("Blueprint completo: %s", blueprint)

    return {
        "status": "success",
        "blueprint": blueprint,
        "summary": _summarize_blueprint(blueprint),
    }


def _derive_components(spec: dict) -> list[dict]:
    raw_components = spec.get("components") or spec.get("services") or []
    if raw_components:
        return _normalize_explicit_components(raw_components)

    inferred = _infer_components_from_spec(spec)
    return _normalize_explicit_components(inferred)


def _normalize_explicit_components(raw_components: list) -> list[dict]:
    normalized: list[dict] = []
    seen_ids: set[str] = set()

    for index, item in enumerate(raw_components, start=1):
        component = _normalize_component(item, index=index)
        if not component:
            continue
        component_id = component["id"]
        if component_id in seen_ids:
            continue
        normalized.append(component)
        seen_ids.add(component_id)

    return normalized


def _normalize_component(item: object, *, index: int) -> dict | None:
    if isinstance(item, str):
        component_id = _slugify(item) or f"component_{index}"
        return {
            "id": component_id,
            "kind": _infer_kind_from_text(item),
            "transport": _infer_transport_from_text(item),
            "purpose": item.strip(),
            "generated_tools": [],
        }

    if not isinstance(item, dict):
        return None

    component = deepcopy(item)
    hints = " ".join(
        str(part)
        for part in (
            item.get("id", ""),
            item.get("name", ""),
            item.get("type", ""),
            item.get("kind", ""),
            item.get("purpose", ""),
            item.get("description", ""),
            item.get("backend", ""),
        )
    )

    component_id = component.get("id") or component.get("name") or component.get("type")
    component["id"] = _slugify(str(component_id)) or f"component_{index}"
    component["kind"] = component.get("kind") or _infer_kind_from_text(hints)
    component["transport"] = component.get("transport") or _infer_transport_from_text(hints)

    if "path" not in component:
        component["path"] = ""
    if "port" in component and isinstance(component["port"], str) and component["port"].isdigit():
        component["port"] = int(component["port"])
    if "generated_tools" not in component or component["generated_tools"] is None:
        component["generated_tools"] = []

    purpose = component.get("purpose") or component.get("description")
    if purpose:
        component["purpose"] = purpose

    return component


def _infer_components_from_spec(spec: dict) -> list[dict]:
    goal = str(spec.get("goal", ""))
    inferred: list[dict] = []
    lowered_goal = goal.lower()

    if any(keyword in lowered_goal for keyword in ("ocr", "imagem", "image", "scan", "documento")):
        inferred.append(
            {
                "id": "ocr",
                "kind": "mcp",
                "transport": "sse",
                "purpose": "Extrair dados de arquivos ou imagens.",
                "generated_tools": [],
            }
        )
    if any(
        keyword in lowered_goal
        for keyword in (
            "rag",
            "retrieval",
            "busca",
            "buscar",
            "search",
            "knowledge base",
            "base de conhecimento",
            "codigo",
            "codigos",
        )
    ):
        inferred.append(
            {
                "id": "retrieval",
                "kind": "mcp",
                "transport": "sse",
                "purpose": "Consultar conhecimento externo ou base indexada.",
                "generated_tools": [],
            }
        )
    if any(
        keyword in lowered_goal
        for keyword in ("api", "http", "webhook", "endpoint", "fastapi", "agendamento", "appointment")
    ):
        inferred.append(
            {
                "id": "api_service",
                "kind": "http_api",
                "transport": "http",
                "purpose": "Expor operacoes HTTP consumidas pelo agente.",
                "generated_tools": [],
            }
        )

    return inferred


def _extract_platform(spec: dict) -> dict:
    platform = spec.get("platform", {})
    if not isinstance(platform, dict):
        return deepcopy(DEFAULT_PLATFORM)

    merged = deepcopy(DEFAULT_PLATFORM)
    if platform.get("cloud"):
        merged["cloud"] = platform["cloud"]
    if platform.get("architecture_preference"):
        merged["architecture_preference"] = platform["architecture_preference"]
    elif platform.get("preference"):
        merged["architecture_preference"] = platform["preference"]

    for key, value in platform.items():
        if key not in merged:
            merged[key] = value
    return merged


def _extract_interface_type(spec: dict) -> str:
    interface = spec.get("interface", {})
    if isinstance(interface, dict):
        return interface.get("type", DEFAULT_INTERFACE)
    if isinstance(interface, str) and interface.strip():
        return interface
    return DEFAULT_INTERFACE


def _extract_flow(spec: dict, components: list[dict]) -> list[str]:
    raw_flow = spec.get("flow")
    if isinstance(raw_flow, list) and raw_flow:
        normalized_flow: list[str] = []
        known_ids = {component["id"] for component in components}
        for item in raw_flow:
            if isinstance(item, str):
                candidate = _slugify(item)
            elif isinstance(item, dict):
                candidate = _slugify(str(item.get("component") or item.get("id") or ""))
            else:
                candidate = None
            if candidate and candidate in known_ids and candidate not in normalized_flow:
                normalized_flow.append(candidate)
        if normalized_flow:
            return normalized_flow
    return [component["id"] for component in components]


def _infer_kind_from_text(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in ("mcp", "tool server", "tool-server")):
        return "mcp"
    if any(keyword in lowered for keyword in ("fastapi", "http api", "rest api", "endpoint", "webhook")):
        return "http_api"
    if any(keyword in lowered for keyword in ("queue", "consumer", "worker", "job")):
        return "worker"
    if any(keyword in lowered for keyword in ("postgres", "mysql", "sqlite", "database", "db")):
        return "database"
    return DEFAULT_COMPONENT_KIND


def _infer_transport_from_text(text: str) -> str:
    lowered = text.lower()
    if "sse" in lowered:
        return "sse"
    if "stdio" in lowered:
        return "stdio"
    if "grpc" in lowered:
        return "grpc"
    if any(keyword in lowered for keyword in ("http", "https", "rest", "fastapi", "webhook")):
        return "http"
    return DEFAULT_TRANSPORT


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug


def _summarize_blueprint(blueprint: dict) -> str:
    parts = []
    for component in blueprint["components"]:
        parts.append(
            f"{component['id']} ({component.get('kind', 'unknown')}:{component.get('transport', 'unknown')})"
        )
    return (
        f"Interface: {blueprint['interface']}. "
        f"Fluxo: {' -> '.join(blueprint['flow'])}. "
        f"Componentes gerados: {', '.join(parts)}."
    )
