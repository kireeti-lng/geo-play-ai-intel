"""Shared LLM client, mirroring the production ``geoplay.config``."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(encoding="utf-8-sig")

DEFAULT_MODEL = "openai/gpt-5.2"


def get_llm(model_name=None):
    """Build a LangChain chat model over OpenRouter.

    Args:
        model_name: Optional model slug. When omitted, falls back to
            OPENROUTER_MODEL from .env and then to DEFAULT_MODEL.
    """
    requested_model = (model_name or "").strip()
    if not requested_model:
        requested_model = (os.environ.get("OPENROUTER_MODEL") or "").strip()
    if not requested_model:
        requested_model = DEFAULT_MODEL

    return ChatOpenAI(
        model=requested_model,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        temperature=0.1,
    )
