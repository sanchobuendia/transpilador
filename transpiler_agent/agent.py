from __future__ import annotations

from pathlib import Path

from google.adk.agents import SequentialAgent

from transpiler_agent.logging_utils import configure_logging
from transpiler_agent.subagents.model_selector.agent import model_selector_agent
from transpiler_agent.subagents.project_generator.agent import project_generator_agent
from transpiler_agent.subagents.project_planner.agent import project_planner_agent
from transpiler_agent.subagents.project_reviewer.agent import project_reviewer_agent
from transpiler_agent.subagents.publisher.agent import publisher_agent
from transpiler_agent.subagents.spec_analyst.agent import spec_analyst_agent

configure_logging()

PROMPT_PATH = Path(__file__).with_name("root_prompt.md")


root_agent = SequentialAgent(
    name="transpiler_orchestrator",
    description=PROMPT_PATH.read_text(encoding="utf-8").strip(),
    sub_agents=[
        spec_analyst_agent,
        project_planner_agent,
        model_selector_agent,
        project_generator_agent,
        project_reviewer_agent,
        publisher_agent,
    ],
)
