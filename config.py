"""Configuracoes centrais do transpilador."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    BEDROCK_CLAUDE_MODEL = (
        os.environ.get("BEDROCK_MODEL_ID")
        or os.environ.get("BEDROCK_CLAUDE_MODEL")
        or "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    TEMPERATURE = float(
        os.environ.get("MODEL_TEMPERATURE")
        or os.environ.get("LLM_TEMPERATURE")
        or "0.1"
    )
    MAX_TOKENS = int(
        os.environ.get("MODEL_MAX_TOKENS")
        or os.environ.get("LLM_MAX_TOKENS")
        or "4096"
    )
    AWS_REGION_NAME = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_REGION_NAME")
        or "us-east-1"
    )
