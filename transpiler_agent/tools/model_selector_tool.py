"""Tool ADK: seleciona o modelo mais adequado com base na complexidade da tarefa."""
from __future__ import annotations

import json
from pathlib import Path

from transpiler_agent.langsmith_utils import traceable
from transpiler_agent.logging_utils import get_logger

CATALOG_PATH = Path(__file__).parents[2] / "catalog" / "models_catalog.json"
logger = get_logger(__name__)


@traceable(name="select_model_tool", run_type="tool")
def select_model_tool(goal: str, total_tools: int) -> dict:
    """
    Seleciona o modelo LLM mais adequado com base na complexidade da tarefa.

    Analisa o objetivo e o número de ferramentas para calcular um score de
    complexidade e escolher o modelo com melhor custo-benefício do catálogo.

    Args:
        goal: Descrição do objetivo do agente.
        total_tools: Número total de tools descobertas nos serviços.

    Returns:
        Dicionário com o modelo selecionado, motivo e informações de custo.
    """
    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["models"]
    except Exception as e:
        logger.exception("Falha ao carregar catalogo de modelos")
        return {"error": f"Não foi possível carregar o catálogo de modelos: {e}"}

    reasons = []
    score = 1
    lowered_goal = goal.lower()

    vision_keywords = [
        "imagem",
        "foto",
        "scan",
        "ocr",
        "fotografia",
        "digitalizado",
        "image",
        "picture",
        "pdf",
        "documento",
        "video",
    ]
    if any(kw in lowered_goal for kw in vision_keywords):
        score = max(score, 2)
        reasons.append("tarefa envolve processamento de imagem — necessita modelo multimodal")

    if total_tools > 8:
        score = max(score, 4)
        reasons.append(f"{total_tools} ferramentas sugerem um caso excepcionalmente complexo")
    elif total_tools > 5:
        score = max(score, 3)
        reasons.append(f"{total_tools} ferramentas exigem raciocínio complexo de orquestração")
    elif total_tools > 2:
        score = max(score, 2)
        reasons.append(f"{total_tools} ferramentas requerem orquestração moderada")

    retrieval_keywords = [
        "buscar",
        "pesquisar",
        "search",
        "rag",
        "retrieval",
        "base de dados",
        "base de conhecimento",
        "knowledge base",
        "consultar",
        "documentos",
        "semantic",
        "semantica",
    ]
    if any(kw in lowered_goal for kw in retrieval_keywords):
        score = max(score, 2)
        reasons.append("inclui recuperacao de contexto externo ou busca semantica")

    live_keywords = ["tempo real", "realtime", "real-time", "audio-to-audio", "voz", "voice", "live api", "streaming"]
    wants_live = any(keyword in lowered_goal for keyword in live_keywords)
    if wants_live:
        score = max(score, 2)
        reasons.append("caso de uso pede dialogo em tempo real ou audio")

    deep_keywords = ["prova matematica", "pesquisa cientifica", "otimizacao dificil", "deep think", "raciocinio profundo"]
    if any(keyword in lowered_goal for keyword in deep_keywords):
        score = max(score, 4)
        reasons.append("objetivo sugere raciocinio profundo de alta complexidade")

    candidates = [m for m in catalog if m["complexity_score"] == score]
    if not candidates:
        candidates = sorted(catalog, key=lambda m: abs(m["complexity_score"] - score))

    if wants_live:
        live_candidate = next((m for m in candidates if "live_api" in m.get("capabilities", [])), None)
        if live_candidate:
            chosen = live_candidate
        else:
            chosen = candidates[0]
    else:
        non_live_candidates = [m for m in candidates if "live_api" not in m.get("capabilities", [])]
        chosen = _choose_best_candidate(non_live_candidates or candidates)

    result = {
        "model_id": chosen["id"],
        "complexity_score": score,
        "reason": "; ".join(reasons) if reasons else "tarefa simples de texto",
        "capabilities": chosen["capabilities"],
        "pricing": chosen["pricing"],
        "context_window": chosen["context_window"],
    }
    logger.info("Modelo selecionado: %s", chosen["id"])
    logger.debug("Motivos da selecao: %s", result)
    return result


def _choose_best_candidate(candidates: list[dict]) -> dict:
    def candidate_cost(model: dict) -> float:
        pricing = model.get("pricing", {})
        numeric_values = [value for value in pricing.values() if isinstance(value, (int, float))]
        return min(numeric_values) if numeric_values else float("inf")

    return sorted(
        candidates,
        key=lambda model: (
            0 if model.get("latency_tier") in ("low", "realtime") else 1,
            candidate_cost(model),
        ),
    )[0]
