from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from transpiler_agent.llm import build_bedrock_llm

from transpiler_agent.subagents.spec_analyst.callbacks import (
    after_model_callback,
    after_tool_callback,
    before_model_callback,
    before_tool_callback,
)
from transpiler_agent.tools.spec_tool import analyze_spec_tool


PROMPT_PATH = Path(__file__).with_name("prompt.md")

spec_analyst_agent = LlmAgent(
    name="spec_analyst",
    model=build_bedrock_llm(),
    description="Valida a spec e produz o blueprint estrutural do projeto.",
    instruction=PROMPT_PATH.read_text(encoding="utf-8"),
    tools=[analyze_spec_tool],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
    output_key="blueprint_json",
)
