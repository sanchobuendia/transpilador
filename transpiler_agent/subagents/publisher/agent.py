from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from transpiler_agent.llm import build_bedrock_llm

from transpiler_agent.subagents.publisher.callbacks import (
    after_model_callback,
    after_tool_callback,
    before_model_callback,
    before_tool_callback,
)
from transpiler_agent.tools.pipeline_tool import deliver_via_github_mcp_tool


PROMPT_PATH = Path(__file__).with_name("prompt.md")

publisher_agent = LlmAgent(
    name="publisher",
    model=build_bedrock_llm(),
    description="Publica o projeto no GitHub quando a spec habilita entrega.",
    instruction=PROMPT_PATH.read_text(encoding="utf-8"),
    tools=[deliver_via_github_mcp_tool],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
    output_key="publish_json",
)
