"""Tool ADK: descobre tools disponíveis em serviços MCP e REST."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

REGISTRY_PATH = Path(__file__).parents[2] / "registry" / "registry.json"


def _load_service(service_id: str) -> dict | None:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return next((s for s in data["services"] if s["id"] == service_id), None)


async def _discover_mcp(service: dict) -> dict:
    """Tenta conectar ao servidor MCP e listar tools via SSE."""
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        tools = []
        async with sse_client(service["url"]) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema or {},
                    }
                    for t in result.tools
                ]
        return {"service_id": service["id"], "type": "mcp", "tools": tools}
    except Exception as e:
        return {
            "service_id": service["id"],
            "type": "mcp",
            "tools": [],
            "warning": f"Servidor MCP indisponível agora (será resolvido em runtime): {e}",
        }


async def _discover_rest(service: dict) -> dict:
    """Busca /openapi.json e extrai endpoints como tools."""
    url = service["url"].rstrip("/") + "/openapi.json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            spec = resp.json()

        tools = []
        for path, methods in spec.get("paths", {}).items():
            for method, op in methods.items():
                if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    continue
                tool_name = (
                    op.get("operationId")
                    or f"{method.lower()}_{path.replace('/', '_').strip('_')}"
                )
                tools.append({
                    "name": tool_name,
                    "method": method.upper(),
                    "path": path,
                    "description": op.get("summary") or op.get("description") or path,
                    "input_schema": (
                        op.get("requestBody", {})
                        .get("content", {})
                        .get("application/json", {})
                        .get("schema", {})
                    ),
                })
        return {"service_id": service["id"], "type": "rest", "url": service["url"], "tools": tools}
    except Exception as e:
        return {
            "service_id": service["id"],
            "type": "rest",
            "tools": [],
            "warning": f"API REST indisponível agora (será resolvida em runtime): {e}",
        }


async def _discover_all(service_ids: list[str]) -> list[dict]:
    tasks = []
    for sid in service_ids:
        svc = _load_service(sid)
        if not svc:
            continue
        if svc["type"] == "mcp":
            tasks.append(_discover_mcp(svc))
        elif svc["type"] == "rest":
            tasks.append(_discover_rest(svc))
    return await asyncio.gather(*tasks)


def discover_services_tool(service_ids: list[str]) -> dict:
    """
    Descobre as tools disponíveis em cada serviço selecionado.

    Para serviços MCP: conecta via SSE e chama list_tools().
    Para serviços REST: faz GET /openapi.json e extrai os endpoints.

    Args:
        service_ids: Lista de IDs de serviços retornados pelo select_services_tool.

    Returns:
        Dicionário com tools descobertas por serviço.
    """
    try:
        results = asyncio.run(_discover_all(service_ids))
        return {
            "discovered": results,
            "total_tools": sum(len(r.get("tools", [])) for r in results),
        }
    except Exception as e:
        return {"error": f"Falha no discovery: {e}"}
