"""Tool ADK: gera um projeto ADK completo a partir de um blueprint."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from transpiler_agent.langsmith_utils import traceable
from transpiler_agent.logging_utils import get_logger

logger = get_logger(__name__)
RUNTIME_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "subagents" / "project_generator" / "runtime_agent_prompt.md"
)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")


def _agent_package_name(name: str) -> str:
    return _slugify(name) or "generated_agent"


def _service_name(component: dict) -> str:
    return component["id"].replace("_", "-")


def _component_port(component: dict, index: int) -> int:
    port = component.get("port")
    if isinstance(port, int):
        return port
    if isinstance(port, str) and port.isdigit():
        return int(port)
    return 8100 + index


def _service_url(component: dict, index: int) -> str:
    port = _component_port(component, index)
    path = component.get("path", "") or ""
    if component.get("kind") == "mcp" and component.get("transport") == "sse":
        path = path or "/sse"
        return f"http://{_service_name(component)}:{port}{path}"
    return f"http://{_service_name(component)}:{port}"


def _is_http_component(component: dict) -> bool:
    kind = component.get("kind", "")
    transport = component.get("transport", "")
    return transport == "http" or kind in {"http_api", "fastapi", "api"}


def _python_identifier(name: str) -> str:
    identifier = _slugify(name)
    if not identifier:
        identifier = "tool"
    if identifier[0].isdigit():
        identifier = f"tool_{identifier}"
    return identifier


def _http_tool_specs(components: list[dict]) -> list[dict]:
    specs: list[dict] = []
    for index, component in enumerate(components, start=1):
        if not _is_http_component(component):
            continue
        tool_names = component.get("generated_tools") or [f"call_{component['id']}"]
        for tool_name in tool_names:
            specs.append(
                {
                    "component_id": component["id"],
                    "tool_name": tool_name,
                    "function_name": _python_identifier(tool_name),
                    "base_url": _service_url(component, index),
                }
            )
    return specs


def _gen_agent_py(spec: dict, blueprint: dict, model_id: str) -> str:
    mcp_components = [
        (index, component)
        for index, component in enumerate(blueprint["components"], start=1)
        if component.get("kind") == "mcp" and component.get("transport") == "sse"
    ]
    http_specs = _http_tool_specs(blueprint["components"])

    imports = [
        "from google.adk.agents import LlmAgent",
        "from google.adk.models.lite_llm import LiteLlm",
        "from config import Config",
        "from .logging_utils import configure_logging, get_logger",
    ]
    tool_exprs: list[str] = []

    if mcp_components:
        imports.extend(
            [
                "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset",
                "from mcp.client.sse import SseServerParams",
            ]
        )
        mcp_lines = [
            f'    MCPToolset(connection_params=SseServerParams(url="{_service_url(component, index)}")),'
            for index, component in mcp_components
        ]
        tool_exprs.append("[\n" + "\n".join(mcp_lines) + "\n]")

    if http_specs:
        imports.append(
            "from .tools import " + ", ".join(spec["function_name"] for spec in http_specs)
        )
        tool_exprs.append("[" + ", ".join(spec["function_name"] for spec in http_specs) + "]")

    imports.append(
        "from .security_callbacks import after_model_callback, after_tool_callback, before_model_callback, before_tool_callback"
    )

    instruction = _build_runtime_instruction(spec, blueprint)
    tools_expr = " + ".join(tool_exprs) if tool_exprs else "[]"

    return "\n".join(imports) + f"""

configure_logging()
logger = get_logger(__name__)

root_agent = LlmAgent(
    name="{_agent_package_name(spec['name'])}",
    model=LiteLlm(
        model=Config.BEDROCK_CLAUDE_MODEL or "{model_id}",
        temperature=Config.TEMPERATURE,
        max_tokens=Config.MAX_TOKENS,
    ),
    description="{spec['name']}",
    instruction=\"\"\"{instruction}\"\"\",
    tools={tools_expr},
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
)
"""


def _build_runtime_instruction(spec: dict, blueprint: dict) -> str:
    steps = []
    for position, component in enumerate(blueprint["components"], start=1):
        tool_names = component.get("generated_tools") or []
        if tool_names:
            steps.append(
                f"{position}. Interaja com o componente `{component['id']}` "
                f"usando as tools disponiveis: {', '.join(f'`{name}`' for name in tool_names)}."
            )
        else:
            steps.append(
                f"{position}. Use o componente `{component['id']}` de acordo com o contrato definido na spec."
            )
    steps.append(
        f"{len(steps) + 1}. Responda no formato esperado pela interface `{blueprint.get('interface', 'cli')}`."
    )

    return RUNTIME_PROMPT_PATH.read_text(encoding="utf-8").format(
        goal=spec["goal"],
        steps="\n".join(steps),
    )


def _gen_tools_py(components: list[dict]) -> str:
    http_specs = _http_tool_specs(components)
    if not http_specs:
        return '''"""Clientes HTTP gerados para componentes com transporte HTTP."""
from __future__ import annotations

# Nenhum componente HTTP foi definido para este projeto.
'''

    lines = [
        '"""Clientes HTTP gerados para componentes com transporte HTTP."""',
        "from __future__ import annotations",
        "",
        "import httpx",
        "",
        "from .logging_utils import get_logger",
        "",
        "logger = get_logger(__name__)",
        "",
    ]
    for spec in http_specs:
        lines.extend(
            [
                f'BASE_URL_{spec["component_id"].upper()} = "{spec["base_url"]}"',
                "",
                f"def {spec['function_name']}(payload: dict | None = None) -> dict:",
                f'    logger.info("Chamando {spec["tool_name"]} em {spec["component_id"]}")',
                "    response = httpx.post(",
                f'        f"{{BASE_URL_{spec["component_id"].upper()}}}/invoke/{spec["tool_name"]}",',
                "        json=payload or {},",
                "        timeout=30,",
                "    )",
                "    response.raise_for_status()",
                "    return response.json()",
                "",
            ]
        )
    return "\n".join(lines)


def _gen_runtime_logging_utils() -> str:
    return '''from __future__ import annotations

import logging
import os

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
'''


def _gen_security_callbacks(components: list[dict], entities: list[str]) -> str:
    allowed_tool_names: set[str] = set()
    for component in components:
        for tool_name in component.get("generated_tools", []):
            allowed_tool_names.add(tool_name)
    allowed_tools_repr = json.dumps(sorted(allowed_tool_names), ensure_ascii=False)
    return f'''"""Callbacks de seguranca e validacao para o runtime gerado."""
from __future__ import annotations

import json
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool

ENTITIES: list[str] = {entities!r}
SUSPICIOUS_PATTERNS = [
    re.compile(r"ignore\\s+(all\\s+)?previous\\s+instructions?", re.IGNORECASE),
    re.compile(r"system\\s+prompt", re.IGNORECASE),
    re.compile(r"developer\\s+message", re.IGNORECASE),
    re.compile(r"call\\s+this\\s+tool", re.IGNORECASE),
    re.compile(r"execute\\s+tool", re.IGNORECASE),
    re.compile(r"<\\s*tool", re.IGNORECASE),
]
ALLOWED_TOOL_NAMES = set({allowed_tools_repr})

PATTERNS = {{
    "CPF": re.compile(r"\\b\\d{{3}}[.\\s]?\\d{{3}}[.\\s]?\\d{{3}}[-\\s]?\\d{{2}}\\b"),
    "PHONE": re.compile(r"\\b(\\+?55[\\s-]?)?(\\(?\\d{{2}}\\)?[\\s-]?)?9?\\d{{4}}[-\\s]?\\d{{4}}\\b"),
    "EMAIL": re.compile(r"[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{{2,}}"),
    "ADDRESS": re.compile(r"\\b(rua|avenida|av|alameda|praca)[.,]?\\s+[\\w\\s]{{3,50}}\\b", re.IGNORECASE),
    "PERSON_NAME": re.compile(r"\\b([A-Z][a-z]{{2,}})(\\s+[A-Z][a-z]{{2,}}){{1,4}}\\b"),
}}


def _mask_pii(value: Any) -> Any:
    if isinstance(value, str):
        masked = value
        for entity in ENTITIES:
            pattern = PATTERNS.get(entity)
            if pattern:
                masked = pattern.sub(f"[{{entity}}_REDACTED]", masked)
        return masked
    if isinstance(value, dict):
        return {{key: _mask_pii(item) for key, item in value.items()}}
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
        raise ValueError(f"Tool nao permitida pelo runtime: {{tool_name}}")
    if not isinstance(args, dict):
        raise ValueError("Args da tool devem ser um objeto JSON.")


def _validate_tool_result(tool_name: str, result: Any) -> Any:
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    if _contains_injection(text):
        raise ValueError(f"Possivel prompt injection detectado na saida da tool {{tool_name}}")
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
'''


def _gen_generated_readme(spec: dict, blueprint: dict, model_id: str, model_reason: str) -> str:
    components = "\n".join(
        f"- `{component['id']}`: `{component.get('kind', 'unknown')}` via `{component.get('transport', 'unknown')}`"
        for component in blueprint["components"]
    )
    return f"""# {spec['name']}

Projeto gerado automaticamente pelo transpilador ADK.

## Objetivo
{spec['goal']}

## Modelo
`{model_id}` - {model_reason}

## Componentes gerados
{components}

## Como subir o ambiente

```bash
cp .env.example .env
docker compose up --build
```

## Como executar o agente localmente

```bash
pip install -r requirements.txt
adk run .
```
"""


def _gen_root_docker_compose(blueprint: dict) -> str:
    lines = ['version: "3.9"', "", "services:"]
    for index, component in enumerate(blueprint["components"], start=1):
        service_name = _service_name(component)
        port = _component_port(component, index)
        build_path = f"./services/{component['id']}"
        lines.extend(
            [
                f"  {service_name}:",
                f"    build: {build_path}",
                "    ports:",
                f'      - "{port}:{port}"',
                "    networks:",
                "      - agent-net",
            ]
        )
        health_path = component.get("path") if component.get("kind") == "mcp" else "/health"
        if component.get("kind") == "mcp":
            health_path = health_path or "/sse"
        lines.extend(
            [
                "    healthcheck:",
                f'      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen(\'http://localhost:{port}{health_path}\', timeout=2)"]',
                "      interval: 10s",
                "      retries: 5",
                "      start_period: 10s",
            ]
        )
    lines.extend(["", "networks:", "  agent-net:", "    driver: bridge", ""])
    return "\n".join(lines)


def _gen_mcp_requirements() -> str:
    return "mcp>=1.27.0\nstarlette>=0.40.0\nuvicorn>=0.30.0\n"


def _gen_http_requirements() -> str:
    return "fastapi>=0.115.0\nuvicorn>=0.30.0\npydantic>=2.0.0\n"


def _gen_service_dockerfile(module_name: str, app_var: str, port: int) -> str:
    return f"""FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "{module_name}:{app_var}", "--host", "0.0.0.0", "--port", "{port}"]
"""


def _gen_root_requirements(pii_enabled: bool) -> str:
    deps = [
        "google-adk>=1.28.1",
        "litellm>=1.52.0",
        "anthropic>=0.39.0",
        "boto3>=1.35.0",
        "botocore>=1.35.0",
        "mcp>=1.27.0",
        "httpx>=0.27.0",
        "fastapi>=0.115.0",
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.0",
    ]
    if pii_enabled:
        deps.append("presidio-analyzer>=2.2.0")
    return "\n".join(deps) + "\n"


def _gen_root_dockerfile() -> str:
    return """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "google.adk.cli", "run", "."]
"""


def _gen_root_config(default_model_id: str) -> str:
    return f'''"""Configuracoes centrais do runtime gerado."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    BEDROCK_CLAUDE_MODEL = (
        os.environ.get("BEDROCK_MODEL_ID")
        or os.environ.get("BEDROCK_CLAUDE_MODEL")
        or "{default_model_id}"
    )
    TEMPERATURE = float(
        os.environ.get("MODEL_TEMPERATURE")
        or os.environ.get("LLM_TEMPERATURE")
        or "0.1"
    )
    MAX_TOKENS = int(
        os.environ.get("MODEL_MAX_TOKENS")
        or os.environ.get("LLM_MAX_TOKENS")
        or "4096"
    )
    AWS_REGION_NAME = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_REGION_NAME")
        or "us-east-1"
    )
'''


def _gen_env_example(blueprint: dict, default_model_id: str) -> str:
    lines = [
        "AWS_REGION=us-east-1",
        "AWS_ACCESS_KEY_ID=",
        "AWS_SECRET_ACCESS_KEY=",
        "AWS_SESSION_TOKEN=",
        f"BEDROCK_MODEL_ID={default_model_id}",
        "MODEL_TEMPERATURE=0.1",
        "MODEL_MAX_TOKENS=4096",
        "LOG_LEVEL=INFO",
    ]
    for component in blueprint["components"]:
        prefix = component["id"].upper()
        lines.append(f"{prefix}_PORT={component.get('port', '')}")
        if component.get("kind") == "mcp":
            lines.append(f"{prefix}_TRANSPORT={component.get('transport', '')}")
    return "\n".join(lines) + "\n"


def _build_sample_dataset(component: dict) -> str:
    minimum = int(component.get("data_contract", {}).get("minimum_exam_records", 25) or 25)
    fields = component.get("data_contract", {}).get("fields") or ["id", "name", "code"]
    dataset = []
    for index in range(1, minimum + 1):
        item = {}
        for field in fields:
            if field == "id":
                item[field] = index
            elif field == "name":
                item[field] = f"{component['id'].replace('_', ' ').title()} Item {index:03d}"
            elif field == "code":
                item[field] = f"{component['id'].upper()}_{index:03d}"
            else:
                item[field] = f"{field}_{index:03d}"
        dataset.append(item)
    return json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"


def _component_tools(component: dict) -> list[str]:
    return component.get("generated_tools") or [f"invoke_{component['id']}"]


def _gen_generic_mcp_server(component: dict) -> str:
    tool_names = _component_tools(component)
    tools_schema = ",\n".join(
        [
            f"""        Tool(
            name="{tool_name}",
            description="Executa a operacao {tool_name} no componente {component['id']}.",
            inputSchema={{"type": "object", "additionalProperties": True}},
        )"""
            for tool_name in tool_names
        ]
    )
    allowed = json.dumps(tool_names, ensure_ascii=False)
    return f'''from __future__ import annotations

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
mcp_server = Server("{component["id"]}")
ALLOWED_TOOLS = set({allowed})


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
{tools_schema}
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name not in ALLOWED_TOOLS:
        raise ValueError(f"Tool desconhecida: {{name}}")
    payload = {{
        "component_id": "{component["id"]}",
        "tool": name,
        "arguments": arguments,
        "status": "ok",
    }}
    logger.info("Executando %s em {component['id']}", name)
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
        Route("{component.get("path") or "/sse"}", endpoint=handle_sse),
        Mount("/messages", app=transport.handle_post_message),
    ]
)
'''


def _gen_generic_http_app(component: dict) -> str:
    tool_names = _component_tools(component)
    allowed = json.dumps(tool_names, ensure_ascii=False)
    title = component.get("name") or component["id"].replace("_", " ").title()
    return f'''from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException

from logging_utils import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
app = FastAPI(title="{title}", version="1.0.0")
ALLOWED_OPERATIONS = set({allowed})


@app.get("/health")
def health() -> dict:
    return {{"status": "ok", "component_id": "{component["id"]}"}}


@app.post("/invoke/{{operation}}")
def invoke(operation: str, payload: dict | None = None) -> dict:
    if operation not in ALLOWED_OPERATIONS:
        raise HTTPException(status_code=404, detail="Operation not found")
    body = payload or {{}}
    logger.info("Executando %s em {component['id']}", operation)
    return {{
        "component_id": "{component["id"]}",
        "operation": operation,
        "received": body,
        "status": "ok",
        "processed_at": datetime.utcnow().isoformat() + "Z",
    }}
'''


@traceable(name="generate_project_tool", run_type="tool")
def generate_project_tool(
    spec_json: str,
    blueprint_json: str,
    plan_json: str,
    model_id: str,
    model_reason: str,
    output_dir: str = "./generated-agent",
) -> dict:
    try:
        spec = json.loads(spec_json)
        blueprint = json.loads(blueprint_json) if isinstance(blueprint_json, str) else blueprint_json
        plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
    except Exception as e:
        logger.exception("Falha ao parsear inputs do codegen")
        return {"status": "error", "error": f"Falha ao parsear inputs: {e}"}

    out = Path(output_dir)
    pkg = out / _agent_package_name(spec["name"])
    services_dir = out / "services"
    pkg.mkdir(parents=True, exist_ok=True)
    services_dir.mkdir(parents=True, exist_ok=True)

    files: dict[Path, str] = {
        pkg / "__init__.py": "from . import agent\n",
        pkg / "agent.py": _gen_agent_py(spec, blueprint, model_id),
        pkg / "tools.py": _gen_tools_py(blueprint["components"]),
        pkg / "logging_utils.py": _gen_runtime_logging_utils(),
        pkg / "security_callbacks.py": _gen_security_callbacks(
            blueprint["components"], blueprint.get("pii_entities", [])
        ),
        out / "config.py": _gen_root_config(model_id),
        out / "requirements.txt": _gen_root_requirements(blueprint["pii_enabled"]),
        out / "Dockerfile": _gen_root_dockerfile(),
        out / "docker-compose.yml": _gen_root_docker_compose(blueprint),
        out / ".env.example": _gen_env_example(blueprint, model_id),
        out / "README.md": _gen_generated_readme(spec, blueprint, model_id, model_reason),
        out / ".gitignore": ".env\n__pycache__/\n*.pyc\n.venv/\nvenv/\n",
    }
    logger.info("Gerando projeto em %s", out)
    logger.debug("Plano usado no codegen: %s", plan)

    for index, component in enumerate(blueprint["components"], start=1):
        component_dir = services_dir / component["id"]
        component_dir.mkdir(parents=True, exist_ok=True)
        port = _component_port(component, index)
        kind = component.get("kind")
        if kind == "mcp":
            files[component_dir / "server.py"] = _gen_generic_mcp_server(component)
            files[component_dir / "requirements.txt"] = _gen_mcp_requirements()
            files[component_dir / "Dockerfile"] = _gen_service_dockerfile("server", "app", port)
        else:
            files[component_dir / "main.py"] = _gen_generic_http_app(component)
            files[component_dir / "requirements.txt"] = _gen_http_requirements()
            files[component_dir / "Dockerfile"] = _gen_service_dockerfile("main", "app", port)
        files[component_dir / "logging_utils.py"] = _gen_runtime_logging_utils()

        if component.get("data_contract", {}).get("minimum_exam_records") or component.get("seed_data"):
            files[component_dir / "sample_data.json"] = _build_sample_dataset(component)

    syntax_errors: list[str] = []
    generated_files: list[str] = []

    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        generated_files.append(str(path))
        if path.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError as e:
                syntax_errors.append(f"{path.name}: linha {e.lineno}: {e.msg}")

    if syntax_errors:
        logger.error("Projeto gerado com erros de sintaxe: %s", syntax_errors)
        return {
            "status": "error",
            "syntax_errors": syntax_errors,
            "generated_files": generated_files,
        }

    logger.info("Projeto gerado com sucesso: %s arquivos", len(generated_files))
    return {
        "status": "success",
        "output_dir": str(out.resolve()),
        "generated_files": generated_files,
        "components": [component["id"] for component in blueprint["components"]],
        "model": model_id,
        "workstreams": [item["id"] for item in plan.get("workstreams", [])],
    }
