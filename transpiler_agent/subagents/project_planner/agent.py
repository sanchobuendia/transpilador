from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from transpiler_agent.llm import build_bedrock_llm

from transpiler_agent.subagents.project_planner.callbacks import (
    after_model_callback,
    after_tool_callback,
    before_model_callback,
    before_tool_callback,
)
from transpiler_agent.tools.plan_tool import plan_project_tool


PROMPT_PATH = Path(__file__).with_name("prompt.md")

project_planner_agent = LlmAgent(
    name="project_planner",
    model=build_bedrock_llm(),
    description="Cria o plano de implementacao por dominios.",
    instruction=PROMPT_PATH.read_text(encoding="utf-8"),
    tools=[plan_project_tool],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
    output_key="plan_json",
)
