"""Wrappers para executar o pipeline com subagentes reais."""
from __future__ import annotations

import json

from transpiler_agent.langsmith_utils import traceable
from transpiler_agent.logging_utils import get_logger
from transpiler_agent.tools.codegen_tool import generate_project_tool
from transpiler_agent.tools.model_selector_tool import select_model_tool


logger = get_logger(__name__)


@traceable(name="select_model_for_project_tool", run_type="tool")
def select_model_for_project_tool(spec_json: str, blueprint_json: str) -> dict:
    try:
        spec = json.loads(spec_json)
        blueprint = json.loads(blueprint_json) if isinstance(blueprint_json, str) else blueprint_json
    except Exception as e:
        logger.exception("Falha ao parsear payload em select_model_for_project_tool")
        return {"status": "error", "error": f"Payload invalido: {e}"}

    result = select_model_tool(
        goal=spec.get("goal", ""),
        total_tools=int(blueprint.get("estimated_tool_count", 0)),
    )
    result["status"] = "success" if "error" not in result else "error"
    return result


@traceable(name="generate_project_from_context_tool", run_type="tool")
def generate_project_from_context_tool(
    spec_json: str,
    blueprint_json: str,
    plan_json: str,
    model_selection_json: str,
    output_dir: str = "./generated-agent",
) -> dict:
    try:
        model_selection = (
            json.loads(model_selection_json)
            if isinstance(model_selection_json, str)
            else model_selection_json
        )
    except Exception as e:
        return {"status": "error", "error": f"Model selection invalido: {e}"}

    return generate_project_tool(
        spec_json=spec_json,
        blueprint_json=blueprint_json,
        plan_json=plan_json,
        model_id=model_selection.get("model_id", ""),
        model_reason=model_selection.get("reason", ""),
        output_dir=output_dir,
    )


@traceable(name="deliver_via_github_mcp_tool", run_type="tool")
def deliver_via_github_mcp_tool(
    spec_json: str,
    blueprint_json: str,
    model_selection_json: str,
    generation_json: str,
) -> dict:
    try:
        spec = json.loads(spec_json)
        blueprint = json.loads(blueprint_json) if isinstance(blueprint_json, str) else blueprint_json
        model_selection = (
            json.loads(model_selection_json)
            if isinstance(model_selection_json, str)
            else model_selection_json
        )
        generation = (
            json.loads(generation_json)
            if isinstance(generation_json, str)
            else generation_json
        )
    except Exception as e:
        return {"status": "error", "error": f"Falha ao parsear payload da entrega: {e}"}

    delivery = spec.get("delivery", {})
    github = delivery.get("github", {})
    github_enabled = bool(github.get("enabled"))
    if not github_enabled:
        return {
            "status": "skipped",
            "reason": "Entrega GitHub nao habilitada na spec em delivery.github.enabled.",
        }

    from transpiler_agent.tools.git_tool import deliver_via_git

    return deliver_via_git(
        agent_name=spec.get("name", "generated-agent"),
        output_dir=generation.get("output_dir", "./generated-agent"),
        model_id=model_selection.get("model_id", ""),
        goal=spec.get("goal", ""),
        selected_services=[component["id"] for component in blueprint.get("components", [])],
        owner=github.get("owner", ""),
        repo=github.get("repository_name", ""),
        create_repository=bool(github.get("create_repository")),
        private=bool(github.get("private", True)),
        repo_description=github.get("description", ""),
        default_branch=github.get("default_branch", "main"),
    )
