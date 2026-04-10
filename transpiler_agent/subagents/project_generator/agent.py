from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from transpiler_agent.llm import build_bedrock_llm

from transpiler_agent.subagents.project_generator.callbacks import (
    after_model_callback,
    after_tool_callback,
    before_model_callback,
    before_tool_callback,
)
from transpiler_agent.tools.pipeline_tool import generate_project_from_context_tool


PROMPT_PATH = Path(__file__).with_name("prompt.md")

project_generator_agent = LlmAgent(
    name="project_generator",
    model=build_bedrock_llm(),
    description="Gera o repositorio completo da aplicacao.",
    instruction=PROMPT_PATH.read_text(encoding="utf-8"),
    tools=[generate_project_from_context_tool],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
    output_key="generation_json",
)
