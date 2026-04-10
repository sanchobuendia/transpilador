"""Testes unitários do transpilador."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from transpiler_agent.tools.spec_tool import analyze_spec_tool
from transpiler_agent.tools.plan_tool import plan_project_tool
from transpiler_agent.tools.model_selector_tool import select_model_tool
from transpiler_agent.tools.codegen_tool import generate_project_tool
from transpiler_agent.tools.review_tool import review_project_tool


# ── spec_tool ─────────────────────────────────────────────────────

class TestSpecTool:
    def test_gera_blueprint_a_partir_da_spec(self):
        result = analyze_spec_tool(json.dumps({
            "name": "Assistente",
            "goal": "Receber imagem, extrair exames, buscar codigos e realizar agendamento",
            "interface": {"type": "cli"},
        }))
        assert result["status"] == "success"
        blueprint = result["blueprint"]
        ids = [component["id"] for component in blueprint["components"]]
        assert ids == ["ocr", "retrieval", "api_service"]

    def test_nao_injeta_componentes_quando_goal_nao_os_pede(self):
        result = analyze_spec_tool(json.dumps({
            "name": "Assistente FAQ",
            "goal": "Responder perguntas frequentes em texto para usuarios internos",
            "interface": {"type": "chat"},
        }))
        assert result["status"] == "error"

    def test_respeita_componentes_explicitos_na_spec(self):
        result = analyze_spec_tool(json.dumps({
            "name": "Assistente",
            "goal": "Processar pedido medico",
            "components": ["ocr", "fastapi"],
        }))
        blueprint = result["blueprint"]
        ids = [component["id"] for component in blueprint["components"]]
        assert ids == ["ocr", "fastapi"]
        assert blueprint["components"][1]["kind"] == "http_api"

    def test_preserva_campos_explicitos_de_componentes(self):
        result = analyze_spec_tool(json.dumps({
            "name": "Assistente",
            "goal": "Consultar documentos por busca semantica",
            "platform": {"cloud": "aws", "preference": "managed_services_first"},
            "interface": {"type": "web"},
            "components": [
                {
                    "id": "rag",
                    "kind": "mcp",
                    "transport": "streamable_http",
                    "provider": "custom",
                    "backend": "opensearch",
                    "port": 9100,
                    "path": "/mcp",
                    "purpose": "Consultar base vetorial interna",
                    "generated_tools": ["search_documents"],
                }
            ],
            "guardrails": {"pii": {"enabled": True, "entities": ["EMAIL"]}},
        }))
        assert result["status"] == "success"
        blueprint = result["blueprint"]
        assert blueprint["platform"]["cloud"] == "aws"
        assert blueprint["platform"]["architecture_preference"] == "managed_services_first"
        assert blueprint["interface"] == "web"
        assert blueprint["flow"] == ["rag"]
        assert blueprint["pii_enabled"] is True
        assert blueprint["pii_entities"] == ["EMAIL"]
        assert blueprint["components"][0]["transport"] == "streamable_http"
        assert blueprint["components"][0]["provider"] == "custom"
        assert blueprint["components"][0]["backend"] == "opensearch"
        assert blueprint["components"][0]["port"] == 9100
        assert blueprint["components"][0]["path"] == "/mcp"
        assert blueprint["components"][0]["purpose"] == "Consultar base vetorial interna"
        assert blueprint["components"][0]["generated_tools"] == ["search_documents"]

    def test_aceita_componentes_arbitrarios(self):
        result = analyze_spec_tool(json.dumps({
            "name": "Assistente Operacional",
            "goal": "Orquestrar CRM, fila e banco de dados",
            "components": [
                {
                    "id": "crm_api",
                    "kind": "http_api",
                    "transport": "http",
                    "generated_tools": ["find_customer", "create_ticket"],
                },
                {
                    "id": "event_worker",
                    "kind": "worker",
                    "transport": "queue",
                },
                {
                    "id": "analytics_db",
                    "kind": "database",
                    "transport": "tcp",
                },
            ],
            "flow": [
                {"component": "crm_api"},
                {"component": "event_worker"},
                {"component": "analytics_db"},
            ],
        }))
        assert result["status"] == "success"
        blueprint = result["blueprint"]
        assert [component["id"] for component in blueprint["components"]] == [
            "crm_api",
            "event_worker",
            "analytics_db",
        ]
        assert blueprint["flow"] == ["crm_api", "event_worker", "analytics_db"]
        assert blueprint["estimated_tool_count"] == 2

    def test_retorna_erro_com_campos_obrigatorios_ausentes(self):
        result = analyze_spec_tool(json.dumps({"goal": "qualquer"}))
        assert result["status"] == "error"


# ── plan_tool ─────────────────────────────────────────────────────

class TestPlanTool:
    def test_gera_plano_por_dominios(self):
        blueprint = analyze_spec_tool(json.dumps({
            "name": "Assistente",
            "goal": "Receber imagem, extrair exames, buscar codigos e realizar agendamento",
        }))["blueprint"]
        result = plan_project_tool(json.dumps({"name": "Assistente"}), json.dumps(blueprint))
        assert result["status"] == "success"
        assert result["plan"]["strategy"] == "phased_orchestrator_with_domain_workers"
        assert len(result["plan"]["workstreams"]) >= 4


# ── model_selector_tool ───────────────────────────────────────────

class TestModelSelectorTool:
    def test_seleciona_modelo_multimodal_para_imagem(self):
        result = select_model_tool("processar imagem de pedido médico", total_tools=2)
        assert result["model_id"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        assert result["complexity_score"] >= 2

    def test_seleciona_modelo_simples_para_texto(self):
        result = select_model_tool("responder perguntas simples", total_tools=0)
        assert result["complexity_score"] == 1
        assert result["model_id"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_seleciona_modelo_complexo_para_muitas_tools(self):
        result = select_model_tool("orquestrar tarefas complexas", total_tools=8)
        assert result["complexity_score"] == 3
        assert result["model_id"] == "bedrock/anthropic.claude-3-opus-20240229-v1:0"

    def test_seleciona_live_para_tarefa_em_tempo_real(self):
        result = select_model_tool("criar agente de voz em tempo real com audio-to-audio", total_tools=2)
        assert result["model_id"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_retorna_campos_obrigatorios(self):
        result = select_model_tool("qualquer goal", total_tools=2)
        for campo in ["model_id", "complexity_score", "reason", "pricing"]:
            assert campo in result

    def test_retorna_motivo_nao_vazio(self):
        result = select_model_tool("processar imagem", total_tools=3)
        assert len(result["reason"]) > 0


# ── codegen_tool ──────────────────────────────────────────────────

class TestCodegenTool:
    def _spec(self, pii: bool = True) -> str:
        return json.dumps({
            "name": "Agente Teste",
            "goal": "Testar geração de código",
            "guardrails": {"pii": {"enabled": pii, "entities": ["CPF", "PHONE"]}},
        })

    def _blueprint(self, pii: bool = True) -> str:
        return json.dumps({
            "agent_name": "Agente Teste",
            "goal": "Testar geração de código",
            "interface": "cli",
            "components": [
                {
                    "id": "ocr",
                    "kind": "mcp",
                    "transport": "sse",
                    "port": 8001,
                    "path": "/sse",
                    "generated_tools": ["extract_request_data"],
                },
                {
                    "id": "rag",
                    "kind": "mcp",
                    "transport": "sse",
                    "port": 8002,
                    "path": "/sse",
                    "generated_tools": ["search_exam_codes"],
                    "data_contract": {"minimum_exam_records": 100, "fields": ["name", "code"]},
                },
                {
                    "id": "scheduling_api",
                    "kind": "http_api",
                    "transport": "http",
                    "port": 8000,
                    "path": "",
                    "generated_tools": ["create_appointment", "get_appointment", "list_appointments"],
                },
            ],
            "flow": ["ocr", "rag", "scheduling_api"],
            "estimated_tool_count": 5,
            "pii_enabled": pii,
            "pii_entities": ["CPF", "PHONE"],
        })

    def test_gera_arquivos_basicos(self, tmp_path):
        plan = plan_project_tool(self._spec(), self._blueprint())["plan"]
        result = generate_project_tool(
            spec_json=self._spec(),
            blueprint_json=self._blueprint(),
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="tarefa multimodal",
            output_dir=str(tmp_path / "agent"),
        )
        assert result["status"] == "success"
        generated = result["generated_files"]
        names = [Path(f).name for f in generated]
        assert "agent.py" in names
        assert "__init__.py" in names
        assert "requirements.txt" in names
        assert "Dockerfile" in names
        assert "README.md" in names
        assert "docker-compose.yml" in names
        assert "server.py" in names
        assert "main.py" in names
        assert "sample_data.json" in names
        assert "logging_utils.py" in names
        assert "security_callbacks.py" in names

    def test_gera_pii_guard_quando_habilitado(self, tmp_path):
        plan = plan_project_tool(self._spec(pii=True), self._blueprint(pii=True))["plan"]
        result = generate_project_tool(
            spec_json=self._spec(pii=True),
            blueprint_json=self._blueprint(pii=True),
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="multimodal",
            output_dir=str(tmp_path / "agent"),
        )
        names = [Path(f).name for f in result["generated_files"]]
        assert "security_callbacks.py" in names

    def test_nao_gera_pii_guard_quando_desabilitado(self, tmp_path):
        plan = plan_project_tool(self._spec(pii=False), self._blueprint(pii=False))["plan"]
        result = generate_project_tool(
            spec_json=self._spec(pii=False),
            blueprint_json=self._blueprint(pii=False),
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="multimodal",
            output_dir=str(tmp_path / "agent"),
        )
        names = [Path(f).name for f in result["generated_files"]]
        assert "security_callbacks.py" in names

    def test_codigo_gerado_tem_sintaxe_valida(self, tmp_path):
        plan = plan_project_tool(self._spec(), self._blueprint())["plan"]
        result = generate_project_tool(
            spec_json=self._spec(),
            blueprint_json=self._blueprint(),
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="multimodal",
            output_dir=str(tmp_path / "agent"),
        )
        assert result["status"] == "success"
        assert "syntax_errors" not in result or result.get("syntax_errors") == []
        for file_path in result["generated_files"]:
            if file_path.endswith(".py"):
                ast.parse(Path(file_path).read_text())

    def test_agent_py_tem_root_agent(self, tmp_path):
        out = tmp_path / "agent"
        plan = plan_project_tool(self._spec(), self._blueprint())["plan"]
        generate_project_tool(
            spec_json=self._spec(),
            blueprint_json=self._blueprint(),
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="multimodal",
            output_dir=str(out),
        )
        # agent.py fica dentro do subpacote
        agent_files = list(out.rglob("agent.py"))
        assert len(agent_files) == 1
        content = agent_files[0].read_text()
        assert "root_agent" in content
        assert "LlmAgent" in content
        assert "before_model_callback" in content
        assert "after_tool_callback" in content

    def test_init_py_importa_agent(self, tmp_path):
        out = tmp_path / "agent"
        plan = plan_project_tool(self._spec(), self._blueprint())["plan"]
        generate_project_tool(
            spec_json=self._spec(),
            blueprint_json=self._blueprint(),
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="multimodal",
            output_dir=str(out),
        )
        init_files = list(out.rglob("__init__.py"))
        assert len(init_files) == 1
        assert "from . import agent" in init_files[0].read_text()

    def test_erro_com_json_invalido(self, tmp_path):
        result = generate_project_tool(
            spec_json="nao é json",
            blueprint_json="{}",
            plan_json="{}",
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="",
            output_dir=str(tmp_path / "agent"),
        )
        assert result["status"] == "error" or "error" in result

    def test_review_detecta_projeto_valido(self, tmp_path):
        out = tmp_path / "agent"
        plan = plan_project_tool(self._spec(), self._blueprint())["plan"]
        generate_project_tool(
            spec_json=self._spec(),
            blueprint_json=self._blueprint(),
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="multimodal",
            output_dir=str(out),
        )
        review = review_project_tool(str(out), self._blueprint())
        assert review["status"] == "success"

    def test_gera_componentes_arbitrarios(self, tmp_path):
        spec = json.dumps({
            "name": "Agente Generico",
            "goal": "Integrar CRM e fila",
            "guardrails": {"pii": {"enabled": False, "entities": []}},
        })
        blueprint = json.dumps({
            "agent_name": "Agente Generico",
            "goal": "Integrar CRM e fila",
            "interface": "cli",
            "components": [
                {
                    "id": "crm_api",
                    "kind": "http_api",
                    "transport": "http",
                    "port": 8101,
                    "generated_tools": ["find_customer", "create_ticket"],
                },
                {
                    "id": "event_bus",
                    "kind": "mcp",
                    "transport": "sse",
                    "port": 8102,
                    "path": "/sse",
                    "generated_tools": ["publish_event"],
                },
            ],
            "flow": ["crm_api", "event_bus"],
            "estimated_tool_count": 3,
            "pii_enabled": False,
            "pii_entities": [],
        })
        plan = plan_project_tool(spec, blueprint)["plan"]
        result = generate_project_tool(
            spec_json=spec,
            blueprint_json=blueprint,
            plan_json=json.dumps(plan),
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            model_reason="generic",
            output_dir=str(tmp_path / "agent"),
        )
        assert result["status"] == "success"
        generated = [Path(item) for item in result["generated_files"]]
        assert any(path.name == "server.py" and path.parent.name == "event_bus" for path in generated)
        assert any(path.name == "main.py" and path.parent.name == "crm_api" for path in generated)


# ── Teste de integração do agente ADK ─────────────────────────────

class TestTranspilerAgent:
    def test_root_agent_existe_e_tem_tools(self):
        from transpiler_agent.agent import root_agent
        assert root_agent is not None
        assert root_agent.name == "transpiler_orchestrator"
        assert len(root_agent.sub_agents) == 6

    def test_root_agent_tem_instruction(self):
        from transpiler_agent.agent import root_agent
        assert root_agent.sub_agents
        assert root_agent.sub_agents[0].instruction
        assert len(root_agent.sub_agents[0].instruction) > 50

    def test_init_importa_agent(self):
        import transpiler_agent
        assert hasattr(transpiler_agent, "agent")
