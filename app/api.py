"""Thin wrappers around the Meta Model API and Baseten, plus retry/budget logic.

The pipeline only talks to a `ModelApi`-shaped object, so tests can pass a fake.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
from pathlib import Path
from typing import Any, Awaitable, Callable

import openai
from openai import OpenAI

from .config import Settings
from .schema import INSTRUCTIONS, SCHEMA


class TransientError(Exception):
    """Retryable failure (used by fakes in tests)."""


RETRYABLE = (
    TransientError,
    TimeoutError,
    asyncio.TimeoutError,
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def final_text(response) -> str:
    """Last assistant message only (web_search adds commentary messages before it)."""
    messages = [i for i in response.output if getattr(i, "type", "") == "message"]
    if not messages:
        return response.output_text or ""
    return "".join(c.text for c in messages[-1].content if getattr(c, "type", "") == "output_text")


class ModelApi:
    """Synchronous calls; the pipeline runs them in threads."""

    def __init__(self, settings: Settings, meta_key: str | None, baseten_key: str | None):
        self.s = settings
        self.meta = OpenAI(base_url=settings.meta_base_url, api_key=meta_key, max_retries=0) if meta_key else None
        self.baseten = (OpenAI(base_url=settings.baseten_base_url, api_key=baseten_key, max_retries=0)
                        if baseten_key else None)

    def segment(self, image: Path, concept: str) -> str:
        response = self.meta.responses.create(
            model=self.s.sam_model,
            input=[{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": concept},
                {"type": "input_image", "image_url": data_url(image)},
            ]}],
            metadata={"include_confidence": "true"},
            timeout=self.s.timeout_sam,
        )
        return response.output_text or ""

    def assess(self, image: Path, overlay: Path, listing: str, feedback: str | None) -> tuple[dict, str]:
        """Returns (parsed JSON or raises ValueError, model name)."""
        text_parts = [f"Objects (number: SAM label):\n{listing or '(none – return objects: [])'}"]
        if feedback:
            text_parts.append(f"Your previous answer was rejected: {feedback}. Fix exactly these problems.")
        if self.s.assess_backend == "baseten":
            content = [
                {"type": "text", "text": "Original photo:"},
                {"type": "image_url", "image_url": {"url": data_url(image)}},
                {"type": "text", "text": "Same photo with numbered SAM masks:"},
                {"type": "image_url", "image_url": {"url": data_url(overlay)}},
                {"type": "text", "text": "\n\n".join(text_parts)},
            ]
            response = self.baseten.chat.completions.create(
                model=self.s.baseten_assess_model,
                messages=[{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": content}],
                response_format={"type": "json_schema", "json_schema": {"name": "assessment", "schema": SCHEMA}},
                timeout=self.s.timeout_assess,
            )
            raw, model = response.choices[0].message.content, self.s.baseten_assess_model
        else:
            content = [
                {"type": "input_text", "text": "Original photo:"},
                {"type": "input_image", "image_url": data_url(image)},
                {"type": "input_text", "text": "Same photo with numbered SAM masks:"},
                {"type": "input_image", "image_url": data_url(overlay)},
                {"type": "input_text", "text": "\n\n".join(text_parts)},
            ]
            response = self.meta.responses.create(
                model=self.s.meta_assess_model,
                instructions=INSTRUCTIONS,
                input=[{"type": "message", "role": "user", "content": content}],
                reasoning={"effort": self.s.assess_effort},
                text={"format": {"type": "json_schema", "name": "assessment", "schema": SCHEMA}},
                timeout=self.s.timeout_assess,
            )
            raw, model = final_text(response), self.s.meta_assess_model
        try:
            return json.loads(raw), model
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"not valid JSON: {exc}") from exc


async def call_with_retry(
    fn: Callable[[], Any],
    *,
    timeout: float,
    delays: tuple[float, ...],
    before_attempt: Callable[[], None],
) -> Any:
    """Run a blocking API call in a thread. Retries only transient errors.
    `before_attempt` reserves budget and may raise BudgetExceeded – then no call is made."""
    attempt = 0
    while True:
        before_attempt()
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout + 5)
        except RETRYABLE:
            if attempt >= len(delays):
                raise
            delay = delays[attempt] * (1 + random.uniform(-0.2, 0.2))
            attempt += 1
            await asyncio.sleep(delay)


AsyncCall = Callable[[], Awaitable[Any]]
