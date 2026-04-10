"""Tool ADK: revisa o projeto gerado em busca de lacunas estruturais."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from transpiler_agent.langsmith_utils import traceable
from transpiler_agent.logging_utils import get_logger


logger = get_logger(__name__)


@traceable(name="review_project_tool", run_type="tool")
def review_project_tool(output_dir: str, blueprint_json: str) -> dict:
    out = Path(output_dir)
    if not out.exists():
        return {"status": "error", "error": f"Diretorio nao encontrado: {output_dir}"}

    try:
        blueprint = json.loads(blueprint_json) if isinstance(blueprint_json, str) else blueprint_json
    except Exception as e:
        return {"status": "error", "error": f"Blueprint invalido: {e}"}

    required = [
        out / "docker-compose.yml",
        out / "README.md",
        out / "requirements.txt",
    ]
    for component in blueprint.get("components", []):
        component_dir = out / "services" / component["id"]
        if component.get("kind") == "mcp":
            required.append(component_dir / "server.py")
        else:
            required.append(component_dir / "main.py")
        required.append(component_dir / "Dockerfile")
        required.append(component_dir / "requirements.txt")

    missing = [str(path.relative_to(out)) for path in required if not path.exists()]

    syntax_errors: list[str] = []
    for path in out.rglob("*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            syntax_errors.append(f"{path.relative_to(out)}:{e.lineno}: {e.msg}")

    findings = []
    if missing:
        findings.append({"severity": "high", "message": f"Arquivos ausentes: {missing}"})
    if syntax_errors:
        findings.append({"severity": "high", "message": f"Erros de sintaxe: {syntax_errors}"})

    status = "success" if not findings else "warning"
    logger.info("Revisao concluida com status %s", status)
    logger.debug("Findings da revisao: %s", findings)
    return {
        "status": status,
        "findings": findings,
        "checked_python_files": len(list(out.rglob("*.py"))),
    }
