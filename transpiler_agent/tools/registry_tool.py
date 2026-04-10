"""Tool ADK: consulta o registry e seleciona serviços relevantes para o goal."""
from __future__ import annotations

import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).parents[2] / "registry" / "registry.json"


def select_services_tool(goal: str) -> dict:
    """
    Consulta o registry de serviços e retorna quais são relevantes para o goal.

    Analisa o objetivo do agente e o compara com as descrições e tags de cada
    serviço registrado, retornando apenas os necessários para implementar o goal.

    Args:
        goal: Descrição em linguagem natural do objetivo do agente a ser criado.

    Returns:
        Dicionário com lista de serviços selecionados e justificativa.
    """
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        services = data["services"]
    except Exception as e:
        return {"error": f"Não foi possível carregar o registry: {e}"}

    catalog_summary = [
        {
            "id": s["id"],
            "type": s["type"],
            "url": s["url"],
            "description": s["description"],
            "tags": s["tags"],
        }
        for s in services
    ]

    return {
        "goal": goal,
        "available_services": catalog_summary,
        "instruction": (
            "Analise o goal e os serviços disponíveis. "
            "Selecione apenas os serviços necessários para implementar o goal. "
            "Não inclua serviços de versionamento; a entrega ao GitHub é feita separadamente "
            "pela tool `deliver_via_git` usando o MCP oficial do GitHub. "
            "Retorne os IDs selecionados na próxima chamada de discover_services_tool."
        ),
    }
