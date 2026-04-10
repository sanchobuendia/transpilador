from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from transpiler_agent.llm import build_bedrock_llm

from transpiler_agent.subagents.project_reviewer.callbacks import (
    after_model_callback,
    after_tool_callback,
    before_model_callback,
    before_tool_callback,
)
from transpiler_agent.tools.review_tool import review_project_tool


PROMPT_PATH = Path(__file__).with_name("prompt.md")

project_reviewer_agent = LlmAgent(
    name="project_reviewer",
    model=build_bedrock_llm(),
    description="Revisa o projeto gerado em busca de inconsistencias.",
    instruction=PROMPT_PATH.read_text(encoding="utf-8"),
    tools=[review_project_tool],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
    output_key="review_json",
)
