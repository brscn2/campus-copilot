"""Centralized AWS Bedrock client. All LLM calls go through here."""

from __future__ import annotations

from typing import Any

import boto3
import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)

_client: Any | None = None


def _get_client() -> Any:
    """Lazy-init the Bedrock runtime client."""
    global _client  # noqa: PLW0603
    if _client is None:
        settings = get_settings()
        _client = boto3.client(
            "bedrock-runtime",
            region_name=settings.bedrock_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
    return _client


async def invoke_model(
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Invoke a Bedrock model with the Messages API.

    Args:
        model_id: Bedrock model ID or inference profile ARN.
        messages: Conversation messages in Bedrock Messages API format.
        system: Optional system prompt.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.

    Returns:
        Parsed response dict from Bedrock.
    """
    import asyncio
    import json

    client = _get_client()

    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }
    if system:
        body["system"] = system

    logger.info("bedrock_invoke", model_id=model_id, max_tokens=max_tokens)

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    result: dict[str, Any] = json.loads(response["body"].read())
    return result


def get_sonnet_model_id() -> str:
    """Return the configured Sonnet model ID."""
    return get_settings().bedrock_sonnet_model_id


def get_haiku_model_id() -> str:
    """Return the configured Haiku model ID."""
    return get_settings().bedrock_haiku_model_id


def get_titan_embed_model_id() -> str:
    """Return the configured Titan Embed model ID."""
    return get_settings().bedrock_titan_embed_model_id


def get_chat_model(
    *, model: str = "sonnet", temperature: float = 0.3, max_tokens: int = 1024
) -> Any:
    """Return a LangChain ChatBedrock instance for use with LangGraph.

    Args:
        model: Model name (currently only 'sonnet' is available).
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
    """
    from langchain_aws import ChatBedrock

    settings = get_settings()
    model_id = get_sonnet_model_id()

    return ChatBedrock(
        model_id=model_id,
        region_name=settings.bedrock_region,
        credentials_profile_name=None,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        model_kwargs={"temperature": temperature, "max_tokens": max_tokens},
    )
