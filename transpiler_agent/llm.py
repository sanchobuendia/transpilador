from __future__ import annotations

from google.adk.models.lite_llm import LiteLlm

from config import Config


def build_bedrock_llm() -> LiteLlm:
    return LiteLlm(
        model=Config.BEDROCK_CLAUDE_MODEL,
        temperature=Config.TEMPERATURE,
        max_tokens=Config.MAX_TOKENS,
    )
