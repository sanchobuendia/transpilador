from __future__ import annotations

import json

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from logging_utils import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
mcp_server = Server("ocr")
ALLOWED_TOOLS = set(["extract_request_data"])


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="extract_request_data",
            description="Executa a operacao extract_request_data no componente ocr.",
            inputSchema={"type": "object", "additionalProperties": True},
        )
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name not in ALLOWED_TOOLS:
        raise ValueError(f"Tool desconhecida: {name}")
    payload = {
        "component_id": "ocr",
        "tool": name,
        "arguments": arguments,
        "status": "ok",
    }
    logger.info("Executando %s em ocr", name)
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


transport = SseServerTransport("/messages")


async def handle_sse(request: Request):
    async with transport.connect_sse(
        request.scope,
        request.receive,
        request._send,
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options(),
        )
    return None


app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages", app=transport.handle_post_message),
    ]
)
