"""Background memory extractor — asks Sonnet to extract remembering-worthy facts."""

from __future__ import annotations

import json

import structlog

from src.lib.bedrock import get_sonnet_model_id, invoke_model
from src.lib.memory import add_to_memory

logger = structlog.get_logger(__name__)

BATCH_SIZE = 4

EXTRACTION_PROMPT = """\
You are analyzing a conversation between a student and an AI assistant.

Extract any facts worth remembering long-term about the student. Focus on:
- Academic interests and preferences
- Career goals and target roles
- Campus preferences (buildings, locations)
- Scheduling patterns or constraints
- Skills and experience mentioned

Return a JSON array of short fact strings. Return [] if nothing notable.

Example: ["Student is interested in reinforcement learning", "Student prefers Garching campus"]

Conversation:
{conversation}"""


async def extract_and_remember(
    *,
    student_id: str,
    turns: list[dict[str, str]],
) -> None:
    """Extract facts from conversation turns and store in Cognee Cloud."""
    try:
        conversation = "\n".join(
            f"{'Student' if t['role'] == 'user' else 'Agent'}: {t['content']}" for t in turns
        )
        prompt = EXTRACTION_PROMPT.format(conversation=conversation)

        response = await invoke_model(
            model_id=get_sonnet_model_id(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.0,
        )

        raw = response["content"][0]["text"]
        facts: list[str] = json.loads(raw)

        if not facts:
            logger.info("memory_extract_nothing_notable", student_id=student_id)
            return

        logger.info("memory_extract_facts", student_id=student_id, count=len(facts))
        for fact in facts:
            await add_to_memory(user_id=student_id, content=fact)

    except Exception:
        logger.warning("memory_extract_failed", student_id=student_id, exc_info=True)
