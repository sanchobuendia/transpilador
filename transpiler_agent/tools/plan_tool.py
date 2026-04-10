"""Tool ADK: cria um plano de geracao por dominios."""
from __future__ import annotations

import json

from transpiler_agent.langsmith_utils import traceable
from transpiler_agent.logging_utils import get_logger


logger = get_logger(__name__)


@traceable(name="plan_project_tool", run_type="tool")
def plan_project_tool(spec_json: str, blueprint_json: str) -> dict:
    try:
        spec = json.loads(spec_json)
        blueprint = json.loads(blueprint_json) if isinstance(blueprint_json, str) else blueprint_json
    except Exception as e:
        logger.exception("Falha ao parsear payload do planner")
        return {"status": "error", "error": f"Falha ao parsear inputs do planner: {e}"}

    components = blueprint.get("components", [])
    workstreams = [
        {
            "id": "runtime_agent",
            "role": "agent_runtime_designer",
            "description": "Gerar o pacote ADK principal, prompts, callbacks de seguranca e integracoes do agente.",
            "targets": ["agent package", "prompts", "security callbacks", "component clients"],
        }
    ]

    for component in components:
        component_id = component["id"]
        component_kind = component.get("kind", "service")
        component_transport = component.get("transport", "unspecified")
        role = _role_for_component(component_kind, component_transport)
        targets = _targets_for_component(component)
        workstreams.append(
            {
                "id": f"component_{component_id}",
                "role": role,
                "description": _describe_component_workstream(component),
                "targets": targets,
            }
        )

    workstreams.extend(
        [
            {
                "id": "infra",
                "role": "infra_builder",
                "description": "Gerar conteinerizacao, compose, dependencias e variaveis de ambiente do projeto.",
                "targets": ["docker-compose.yml", "requirements.txt", ".env.example", "Dockerfile"],
            },
            {
                "id": "docs",
                "role": "documentation_builder",
                "description": "Gerar README final e instrucoes de execucao coerentes com a arquitetura declarada.",
                "targets": ["README.md"],
            },
        ]
    )

    plan = {
        "project_name": spec.get("name", "generated-agent"),
        "strategy": "phased_orchestrator_with_domain_workers",
        "think": [
            "Validar a spec e os contratos entre componentes antes de gerar arquivos.",
            "Preservar os componentes declarados pelo usuario sem impor um caso de uso predefinido.",
            "Gerar cada componente a partir de kind, transport e generated_tools.",
            "Executar revisao cruzada ao final para detectar inconsistencias estruturais.",
        ],
        "workstreams": workstreams,
    }
    logger.info("Plano de geracao criado com %s workstreams", len(workstreams))
    logger.debug("Plano completo: %s", plan)
    return {"status": "success", "plan": plan}


def _role_for_component(kind: str, transport: str) -> str:
    if kind == "mcp":
        return f"mcp_{transport}_builder"
    if transport == "http" or kind in {"http_api", "fastapi", "api"}:
        return "http_service_builder"
    if kind == "worker":
        return "worker_builder"
    if kind == "database":
        return "data_layer_builder"
    return "component_builder"


def _targets_for_component(component: dict) -> list[str]:
    component_id = component["id"]
    kind = component.get("kind", "service")
    if kind == "mcp":
        return [f"services/{component_id}/server.py", f"services/{component_id}/Dockerfile"]
    if component.get("transport") == "http" or kind in {"http_api", "fastapi", "api"}:
        return [f"services/{component_id}/main.py", f"services/{component_id}/Dockerfile"]
    return [f"services/{component_id}/main.py", f"services/{component_id}/Dockerfile"]


def _describe_component_workstream(component: dict) -> str:
    kind = component.get("kind", "service")
    transport = component.get("transport", "unspecified")
    purpose = component.get("purpose") or component.get("description") or "Componente sem descricao explicita."
    return (
        f"Gerar o componente `{component['id']}` como `{kind}` via `{transport}`. "
        f"Objetivo: {purpose}"
    )
