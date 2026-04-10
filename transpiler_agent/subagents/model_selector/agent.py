from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from transpiler_agent.llm import build_bedrock_llm

from transpiler_agent.subagents.model_selector.callbacks import (
    after_model_callback,
    after_tool_callback,
    before_model_callback,
    before_tool_callback,
)
from transpiler_agent.tools.pipeline_tool import select_model_for_project_tool


PROMPT_PATH = Path(__file__).with_name("prompt.md")

model_selector_agent = LlmAgent(
    name="model_selector",
    model=build_bedrock_llm(),
    description="Seleciona o modelo ideal para o projeto.",
    instruction=PROMPT_PATH.read_text(encoding="utf-8"),
    tools=[select_model_for_project_tool],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
    output_key="model_selection_json",
)
