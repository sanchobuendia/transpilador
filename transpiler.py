#!/usr/bin/env python3
"""
Transpilador de Agentes ADK.

Uso:
    python transpiler.py --spec agent_spec.json
    python transpiler.py --spec agent_spec.json --output ./meu-agente
    python transpiler.py --spec agent_spec.json --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from transpiler_agent.langsmith_utils import configure_langsmith, traceable, tracing_context
from transpiler_agent.logging_utils import configure_logging, get_logger
from transpiler_agent.tools.codegen_tool import generate_project_tool
from transpiler_agent.tools.model_selector_tool import select_model_tool
from transpiler_agent.tools.plan_tool import plan_project_tool
from transpiler_agent.tools.pipeline_tool import deliver_via_github_mcp_tool
from transpiler_agent.tools.review_tool import review_project_tool
from transpiler_agent.tools.spec_tool import analyze_spec_tool

load_dotenv()
configure_logging()
configure_langsmith()
logger = get_logger(__name__)


def _read_spec(spec_path: str) -> dict:
    spec_file = Path(spec_path)
    if not spec_file.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {spec_path}")
    if spec_file.suffix.lower() != ".json":
        raise ValueError(f"O arquivo deve ser .json. Recebido: {spec_file.suffix}")
    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc}") from exc

    missing = [field for field in ("name", "goal") if field not in spec]
    if missing:
        raise ValueError(f"Campos obrigatórios ausentes na spec: {missing}")
    return spec


def _require_success(result: dict, step_name: str) -> dict:
    status = result.get("status")
    if status in {"success", "warning", "skipped", "skip"}:
        return result
    raise RuntimeError(f"{step_name} falhou: {json.dumps(result, ensure_ascii=False)}")


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")


def _default_output_dir(spec: dict) -> str:
    slug = _slugify(spec.get("name", "generated-agent")) or "generated-agent"
    return f"./{slug}"


def _print_banner(spec_path: str, spec: dict, dry_run: bool) -> None:
    print("=" * 60)
    print("  Transpilador de Agentes ADK")
    print("=" * 60)
    print(f"  Spec: {spec_path}")
    print(f"  Agente: {spec['name']}")
    print(f"  Goal: {spec['goal'][:70]}...")
    if dry_run:
        print("  Modo: DRY RUN (nenhum arquivo será criado)")
    print("=" * 60)


@traceable(name="transpiler_run", run_type="chain")
async def run_transpiler(spec_path: str, output_dir: str, dry_run: bool) -> int:
    run_id = uuid.uuid4().hex[:12]
    spec = _read_spec(spec_path)
    resolved_output_dir = output_dir or _default_output_dir(spec)
    _print_banner(spec_path, spec, dry_run)
    logger.info("run_id=%s | inicio da execucao do transpilador", run_id)
    logger.info("run_id=%s | spec=%s | output_dir=%s | dry_run=%s", run_id, spec_path, resolved_output_dir, dry_run)

    with tracing_context(
        project_name=None,
        metadata={
            "run_id": run_id,
            "spec_path": spec_path,
            "output_dir": resolved_output_dir,
            "dry_run": dry_run,
            "agent_name": spec.get("name"),
        },
    ):
        spec_json = json.dumps(spec, ensure_ascii=False)

        logger.info("run_id=%s | etapa=spec_analysis | iniciando", run_id)
        blueprint_result = _require_success(analyze_spec_tool(spec_json), "analyze_spec_tool")
        blueprint = blueprint_result["blueprint"]
        blueprint_json = json.dumps(blueprint, ensure_ascii=False)
        logger.info(
            "run_id=%s | etapa=spec_analysis | concluida | componentes=%s",
            run_id,
            [component.get("id") for component in blueprint.get("components", [])],
        )

        logger.info("run_id=%s | etapa=planning | iniciando", run_id)
        plan_result = _require_success(
            plan_project_tool(spec_json, blueprint_json),
            "plan_project_tool",
        )
        plan = plan_result["plan"]
        plan_json = json.dumps(plan, ensure_ascii=False)
        logger.info(
            "run_id=%s | etapa=planning | concluida | workstreams=%s",
            run_id,
            [item.get("id") for item in plan.get("workstreams", [])],
        )

        logger.info("run_id=%s | etapa=model_selection | iniciando", run_id)
        model_result = select_model_tool(
            goal=spec.get("goal", ""),
            total_tools=int(blueprint.get("estimated_tool_count", 0)),
        )
        model_result["status"] = "success" if "error" not in model_result else "error"
        _require_success(model_result, "select_model_tool")
        model_json = json.dumps(model_result, ensure_ascii=False)
        logger.info(
            "run_id=%s | etapa=model_selection | concluida | model_id=%s",
            run_id,
            model_result.get("model_id"),
        )

        if dry_run:
            dry_run_payload = {
                "status": "success",
                "run_id": run_id,
                "spec_summary": {
                    "name": spec["name"],
                    "goal": spec["goal"],
                },
                "blueprint": blueprint,
                "plan": plan,
                "model_selection": model_result,
                "output_dir": str(Path(resolved_output_dir).resolve()),
            }
            print(json.dumps(dry_run_payload, ensure_ascii=False, indent=2))
            return 0

        logger.info("run_id=%s | etapa=generation | iniciando", run_id)
        generation_result = _require_success(
            generate_project_tool(
                spec_json=spec_json,
                blueprint_json=blueprint_json,
                plan_json=plan_json,
                model_id=model_result.get("model_id", ""),
                model_reason=model_result.get("reason", ""),
                output_dir=resolved_output_dir,
            ),
            "generate_project_tool",
        )
        generation_json = json.dumps(generation_result, ensure_ascii=False)
        logger.info(
            "run_id=%s | etapa=generation | concluida | output_dir=%s | arquivos=%s",
            run_id,
            generation_result.get("output_dir"),
            len(generation_result.get("generated_files", [])),
        )

        generated_dir = Path(generation_result["output_dir"])
        if not generated_dir.exists():
            raise RuntimeError(
                f"generate_project_tool reportou sucesso, mas o diretório não existe: {generated_dir}"
            )

        logger.info("run_id=%s | etapa=review | iniciando", run_id)
        review_result = _require_success(
            review_project_tool(str(generated_dir), blueprint_json),
            "review_project_tool",
        )
        logger.info(
            "run_id=%s | etapa=review | concluida | status=%s | findings=%s",
            run_id,
            review_result.get("status"),
            len(review_result.get("findings", [])),
        )

        logger.info("run_id=%s | etapa=publish | iniciando", run_id)
        publish_result = deliver_via_github_mcp_tool(
            spec_json=spec_json,
            blueprint_json=blueprint_json,
            model_selection_json=model_json,
            generation_json=generation_json,
        )
        logger.info(
            "run_id=%s | etapa=publish | concluida | status=%s",
            run_id,
            publish_result.get("status"),
        )

        final_payload = {
            "status": "success",
            "run_id": run_id,
            "output_dir": str(generated_dir),
            "generated_files": generation_result.get("generated_files", []),
            "review": review_result,
            "publish": publish_result,
        }
        print(json.dumps(final_payload, ensure_ascii=False, indent=2))
        logger.info("run_id=%s | execucao concluida com sucesso", run_id)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transpilador de agentes Google ADK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--spec", required=True, help="Caminho para o JSON de especificação")
    parser.add_argument(
        "--output",
        default=None,
        help="Diretório de saída. Default: derivado do nome do agente na spec",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Descreve o que seria gerado sem criar arquivos",
    )

    args = parser.parse_args()
    try:
        exit_code = asyncio.run(run_transpiler(args.spec, args.output, args.dry_run))
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
