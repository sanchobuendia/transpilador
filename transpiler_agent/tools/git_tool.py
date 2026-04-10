"""
Tool ADK: entrega o projeto gerado via GitHub MCP Server oficial.
Cria branch, faz push dos arquivos e abre Pull Request.
"""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _run_coro_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


def _get_owner_repo(owner: str = "", repo: str = "") -> tuple[str, str]:
    """Retorna (owner, repo) a partir dos parametros ou do GITHUB_REPO."""
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    placeholder_owners = {"your-github-owner", "owner", "your-github-username"}
    placeholder_repos = {"repository", "repo", "your-repository-name"}

    if owner and repo and owner not in placeholder_owners and repo not in placeholder_repos:
        return owner, repo

    github_repo = os.environ.get("GITHUB_REPO", "")
    if "/" not in github_repo:
        raise ValueError(
            f"GITHUB_REPO deve ter formato 'owner/' ou 'owner/repo', obtido: '{github_repo}'"
        )
    resolved_owner, resolved_repo = github_repo.split("/", 1)
    resolved_owner = resolved_owner.strip()
    resolved_repo = resolved_repo.strip()

    if not resolved_owner:
        raise ValueError(
            f"GITHUB_REPO deve informar ao menos o owner, obtido: '{github_repo}'"
        )

    final_owner = owner if owner and owner not in placeholder_owners else resolved_owner
    final_repo = repo if repo and repo not in placeholder_repos else resolved_repo

    if not final_repo:
        raise ValueError(
            "Nome do repositorio ausente. Informe `delivery.github.repository_name` na spec "
            "ou use GITHUB_REPO no formato 'owner/repo'."
        )
    return final_owner, final_repo


def _get_server_params() -> StdioServerParameters:
    """Parâmetros para iniciar o GitHub MCP Server oficial via Docker."""
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError(
            "GITHUB_PERSONAL_ACCESS_TOKEN (ou GITHUB_TOKEN) não definido no ambiente."
        )
    image = os.environ.get("GITHUB_MCP_DOCKER_IMAGE", "ghcr.io/github/github-mcp-server")
    return StdioServerParameters(
        command="docker",
        args=[
            "run", "-i", "--rm",
            "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={token}",
            image,
        ],
    )


def deliver_via_git(
    agent_name: str,
    output_dir: str,
    model_id: str,
    goal: str,
    selected_services: list[str],
    owner: str = "",
    repo: str = "",
    create_repository: bool = False,
    private: bool = True,
    repo_description: str = "",
    default_branch: str = "main",
) -> dict:
    """
    Entrega o projeto gerado via GitHub MCP Server oficial:
    cria branch, faz push de todos os arquivos e abre um Pull Request.

    Args:
        agent_name: Nome do agente gerado (usado no nome da branch e no título do PR).
        output_dir: Diretório com os arquivos gerados pelo generate_project_tool.
        model_id: Modelo selecionado pelo transpilador (para incluir na descrição do PR).
        goal: Objetivo do agente (para incluir na descrição do PR).
        selected_services: IDs dos serviços utilizados.

    Returns:
        Dicionário com status da entrega e URL do PR criado.
    """
    out = Path(output_dir)
    if not out.exists():
        return {"status": "error", "error": f"Diretório não encontrado: {output_dir}"}

    # Coleta todos os arquivos gerados
    files: list[dict] = []
    for path in out.rglob("*"):
        if path.is_file():
            try:
                files.append({
                    "path": str(path.relative_to(out)),
                    "content": path.read_text(encoding="utf-8"),
                })
            except Exception:
                pass  # ignora binários

    if not files:
        return {"status": "error", "error": "Nenhum arquivo encontrado no output_dir."}

    slug = agent_name.lower().replace(" ", "-")
    branch_name = f"feat/transpiler/{slug}"

    pr_description = _build_pr_description(
        agent_name=agent_name,
        goal=goal,
        model_id=model_id,
        selected_services=selected_services,
        files=[f["path"] for f in files],
    )

    commit_message = (
        f"feat(transpiler): gera agente '{agent_name}'\n\n"
        f"Gerado automaticamente pelo Transpilador ADK.\n"
        f"Modelo: {model_id}\n"
        f"Serviços: {', '.join(selected_services)}"
    )

    try:
        results = _run_coro_sync(_run_git_pipeline(
            owner=owner,
            repo=repo,
            branch_name=branch_name,
            files=files,
            commit_message=commit_message,
            pr_title=f"feat: agente '{agent_name}' gerado pelo transpilador",
            pr_description=pr_description,
            create_repository=create_repository,
            private=private,
            repo_description=repo_description,
            default_branch=default_branch,
        ))
        return {
            "status": "success",
            "branch": branch_name,
            "files_committed": len(files),
            "github_repo": "/".join(_get_owner_repo(owner, repo)),
            "git_steps": results,
        }
    except Exception as e:
        return {"status": "error", "error": f"Falha no pipeline Git: {e}"}


async def _run_git_pipeline(
    owner: str,
    repo: str,
    branch_name: str,
    files: list[dict],
    commit_message: str,
    pr_title: str,
    pr_description: str,
    create_repository: bool,
    private: bool,
    repo_description: str,
    default_branch: str,
) -> list[str]:
    """Executa o pipeline GitHub após descobrir as tools publicadas pelo MCP.

    Usa uma única sessão do GitHub MCP Server para todo o pipeline.
    """
    owner, repo = _get_owner_repo(owner, repo)
    params = _get_server_params()
    results = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            available_tools = await session.list_tools()
            tool_specs = {tool.name: tool for tool in available_tools.tools}
            results.append(
                "list_tools: "
                + ", ".join(sorted(tool_specs))
                if tool_specs
                else "list_tools: nenhuma tool publicada pelo servidor"
            )

            create_branch_tool = _resolve_tool(
                tool_specs,
                operation="create_branch",
                candidates=("create_branch",),
                keywords=("branch", "ref"),
            )
            push_files_tool = _resolve_tool(
                tool_specs,
                operation="push_files",
                candidates=("push_files",),
                keywords=("push", "file", "commit"),
            )
            create_pr_tool = _resolve_tool(
                tool_specs,
                operation="create_pull_request",
                candidates=("create_pull_request", "create_pr"),
                keywords=("pull request", "pull", "pr"),
            )
            create_repo_tool = None
            if create_repository:
                create_repo_tool = _resolve_optional_tool(
                    tool_specs,
                    operation="create_repository",
                    candidates=("create_repository", "create_repo"),
                    keywords=("create", "repository"),
                )
                if not create_repo_tool:
                    raise ValueError(
                        "O GitHub MCP nao publicou uma tool compativel com criacao de repositorio."
                    )

                r = await session.call_tool(
                    create_repo_tool.name,
                    _build_tool_args(
                        create_repo_tool,
                        {
                            "owner": owner,
                            "repo": repo,
                            "name": repo,
                            "private": private,
                            "description": repo_description or f"Repositorio gerado para {agent_name_from_branch(branch_name)}",
                            "auto_init": False,
                        },
                    ),
                )
                results.append(f"{create_repo_tool.name}: {_extract_text(r)}")

            # 1. Cria branch
            base_branch = default_branch or os.environ.get("GITHUB_BASE_BRANCH", "main")
            if create_repository:
                r = await session.call_tool(
                    push_files_tool.name,
                    _build_tool_args(
                        push_files_tool,
                        {
                            "owner": owner,
                            "repo": repo,
                            "branch": base_branch,
                            "files": files,
                            "message": commit_message,
                        },
                    ),
                )
                results.append(f"{push_files_tool.name}: {_extract_text(r)}")
                results.append("create_pull_request: skipped (repositorio novo com commit inicial na branch base)")
            else:
                r = await session.call_tool(
                    create_branch_tool.name,
                    _build_tool_args(
                        create_branch_tool,
                        {
                            "owner": owner,
                            "repo": repo,
                            "branch": branch_name,
                            "from_branch": base_branch,
                        },
                    ),
                )
                results.append(f"{create_branch_tool.name}: {_extract_text(r)}")

                # 2. Push de todos os arquivos em um único commit
                r = await session.call_tool(
                    push_files_tool.name,
                    _build_tool_args(
                        push_files_tool,
                        {
                            "owner": owner,
                            "repo": repo,
                            "branch": branch_name,
                            "files": files,
                            "message": commit_message,
                        },
                    ),
                )
                results.append(f"{push_files_tool.name}: {_extract_text(r)}")

                # 3. Abre Pull Request
                r = await session.call_tool(
                    create_pr_tool.name,
                    _build_tool_args(
                        create_pr_tool,
                        {
                            "owner": owner,
                            "repo": repo,
                            "title": pr_title,
                            "body": pr_description,
                            "head": branch_name,
                            "base": base_branch,
                        },
                    ),
                )
                results.append(f"{create_pr_tool.name}: {_extract_text(r)}")

    return results


def _extract_text(result) -> str:
    texts = [c.text for c in result.content if hasattr(c, "text")]
    return "\n".join(texts)


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _resolve_tool(
    tool_specs: dict[str, Any],
    operation: str,
    candidates: tuple[str, ...],
    keywords: tuple[str, ...],
):
    for candidate in candidates:
        if candidate in tool_specs:
            return tool_specs[candidate]

    normalized_candidates = {_normalize(candidate) for candidate in candidates}
    for name, tool in tool_specs.items():
        if _normalize(name) in normalized_candidates:
            return tool

    for tool in tool_specs.values():
        haystack = " ".join(
            [
                tool.name,
                getattr(tool, "description", "") or "",
            ]
        ).lower()
        if all(keyword in haystack for keyword in keywords):
            return tool

    raise ValueError(
        f"O GitHub MCP não publicou uma tool compatível com '{operation}'. "
        f"Disponíveis: {', '.join(sorted(tool_specs)) or '(nenhuma)'}"
    )


def _resolve_optional_tool(
    tool_specs: dict[str, Any],
    operation: str,
    candidates: tuple[str, ...],
    keywords: tuple[str, ...],
):
    try:
        return _resolve_tool(tool_specs, operation, candidates, keywords)
    except ValueError:
        return None


def _build_tool_args(tool: Any, values: dict[str, Any]) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or {}
    properties = schema.get("properties", {})
    if not properties:
        return values

    aliases = {
        "owner": ("owner",),
        "repo": ("repo", "repository"),
        "name": ("name", "repo", "repository"),
        "branch": ("branch", "branch_name", "new_branch", "name"),
        "from_branch": ("from_branch", "base_branch", "source_branch", "from"),
        "files": ("files",),
        "message": ("message", "commit_message"),
        "title": ("title", "pr_title"),
        "body": ("body", "description", "pr_body"),
        "head": ("head", "source_branch"),
        "base": ("base", "target_branch", "base_branch"),
        "private": ("private", "is_private"),
        "description": ("description", "repo_description"),
        "auto_init": ("auto_init", "initialize_with_readme"),
    }

    built: dict[str, Any] = {}
    for canonical_name, value in values.items():
        for alias in aliases.get(canonical_name, (canonical_name,)):
            if alias in properties:
                built[alias] = value
                break

    required = schema.get("required", [])
    missing = [name for name in required if name not in built]
    if missing:
        raise ValueError(
            f"A tool '{tool.name}' exige parâmetros não suportados automaticamente: {missing}. "
            f"Schema disponível: {schema}"
        )

    return built


def agent_name_from_branch(branch_name: str) -> str:
    return branch_name.split("/")[-1].replace("-", " ")


def _build_pr_description(
    agent_name: str,
    goal: str,
    model_id: str,
    selected_services: list[str],
    files: list[str],
) -> str:
    files_list = "\n".join(f"- `{f}`" for f in sorted(files))
    services_list = ", ".join(f"`{s}`" for s in selected_services)

    return f"""## Agente gerado pelo Transpilador ADK

**Nome:** {agent_name}
**Objetivo:** {goal}

---

### Decisões do transpilador

| Campo | Valor |
|-------|-------|
| Modelo selecionado | `{model_id}` |
| Serviços utilizados | {services_list} |
| Total de arquivos | {len(files)} |

### Arquivos gerados

{files_list}

### Checklist de revisão

- [ ] `agent.py` define `root_agent` corretamente
- [ ] `__init__.py` importa o módulo agent
- [ ] Tools MCP conectam nos endpoints corretos
- [ ] PII guard está ativo (se configurado na spec)
- [ ] `docker-compose.yml` sobe todos os serviços
- [ ] `README.md` tem instruções claras de execução
- [ ] Testes de integração executados com sucesso
- [ ] Revisão humana aprovada

---
*Gerado automaticamente pelo Transpilador de Agentes ADK*
"""
