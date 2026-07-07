"""Thin wrapper over the Anthropic SDK for the Claude-powered passes.

Everything Claude-facing goes through `structured()`, which forces a Pydantic-typed
JSON response so the rest of the pipeline never parses free text. `anthropic` is
imported lazily so the deterministic modules (taxonomy, variance, report, feedback)
run with no SDK and no API key.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional, TypeVar

from pydantic import BaseModel

# Opus 4.8 — provenance and mapping correctness matter more than token cost here.
# Override per-run with --model or ANTHROPIC_MODEL.
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
DEFAULT_EFFORT = os.environ.get("BIDCOMPARE_EFFORT", "high")

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def _client():
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - environment dependent
        raise LLMError(
            "The `anthropic` package is required for the extract/map/exclusions "
            "passes. Install it with `pip install anthropic`."
        ) from e
    return anthropic.Anthropic()


def pdf_block(path: Path | str) -> dict:
    """A base64 PDF document block. Goes *before* the text block in message content."""
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")
    return {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
    }


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def structured(
    *,
    system: str,
    content: list[dict],
    schema: type[T],
    model: Optional[str] = None,
    effort: Optional[str] = None,
    max_tokens: int = 16000,
) -> T:
    """One Claude call that must return an instance of `schema`.

    `content` is the user-turn content blocks (a PDF document block + an instruction
    text block, typically). Returns the parsed, validated Pydantic model.
    """
    client = _client()
    resp = client.messages.parse(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": effort or DEFAULT_EFFORT},
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
    )
    parsed = resp.parsed_output
    if parsed is None:
        reason = getattr(resp, "stop_reason", "unknown")
        raise LLMError(f"Claude did not return a parseable result (stop_reason={reason})")
    return parsed
