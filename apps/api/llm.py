"""Ollama client wrapper — streaming + sync.

The verifier topology (PLAN §4.3) gates emission on per-sentence verification.
This module just speaks to Ollama; the verifier orchestration lives in main.py.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from apps.api.config import get_settings

logger = logging.getLogger(__name__)


class LLMModelUnavailable(RuntimeError):
    """Raised when the configured Ollama model is not available locally."""


def _model_unavailable_message(
    *,
    model: str,
    available_models: list[str] | None = None,
    error: str | None = None,
) -> str:
    available = available_models or []
    if available:
        listed = ", ".join(available[:10])
        suffix = f" Available models: {listed}."
    elif error:
        suffix = f" Ollama error: {error}."
    else:
        suffix = " No local Ollama models were reported."
    return (
        f"Configured Ollama model '{model}' is not available. "
        f"Run `ollama pull {model}` or change LLM_MODEL to an installed model."
        f"{suffix}"
    )


async def list_available_models(timeout_s: float = 2.0) -> list[str]:
    """Return local Ollama model names from /api/tags."""
    s = get_settings()
    url = f"http://localhost:{s.ollama_host_port}/api/tags"
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    data = resp.json()
    names: list[str] = []
    for item in data.get("models", []):
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name:
            names.append(name)
    return names


async def check_model_available(model: str | None = None) -> dict:
    """Cheap preflight for /answer so model config failures fail early."""
    s = get_settings()
    target = model or s.llm_model
    try:
        available_models = await list_available_models()
    except Exception as e:
        error = str(e)
        return {
            "ok": False,
            "model": target,
            "available_models": [],
            "error": error,
            "message": _model_unavailable_message(model=target, error=error),
        }

    ok = target in available_models
    if not ok and ":" not in target:
        ok = f"{target}:latest" in available_models
    message = None if ok else _model_unavailable_message(
        model=target,
        available_models=available_models,
    )
    return {
        "ok": ok,
        "model": target,
        "available_models": available_models,
        "error": None if ok else "model_not_found",
        "message": message,
    }


def load_answer_prompt() -> str:
    p = Path(__file__).parent / "prompts" / "answer.md"
    return p.read_text(encoding="utf-8").strip()


def build_messages(
    *,
    system: str,
    user_question: str,
    passages: list[dict],
) -> list[dict]:
    """Build the chat messages for /answer.

    `passages` is a list of dicts with at least 'index' (1-based) and 'text'.
    Optional: 'anchor', 'title', 'as_at', 'court', 'citation', 'statute_short'.
    """
    passage_block = []
    for p in passages:
        idx = p["index"]
        meta_bits = []
        if p.get("title"):
            meta_bits.append(p["title"])
        if p.get("statute_short"):
            meta_bits.append(p["statute_short"])
        if p.get("court") and p.get("citation"):
            meta_bits.append(f"{p['court']} {p['citation']}")
        if p.get("anchor"):
            meta_bits.append(p["anchor"])
        if p.get("as_at"):
            meta_bits.append(f"as_at: {p['as_at']}")
        header = " | ".join(meta_bits)
        passage_block.append(f"[{idx}] {header}\n{p['text']}")
    passages_text = "\n\n".join(passage_block)
    user_content = (
        f"User question:\n{user_question}\n\n"
        f"Retrieved passages:\n{passages_text}\n\n"
        f"Answer the user's question using the rules in the system prompt."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


async def stream_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Stream tokens from Ollama's /api/chat. Yields delta strings."""
    s = get_settings()
    model = model or s.llm_model
    max_tokens = max_tokens or s.llm_max_tokens

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        # Modern open-weight models (Gemma 3, GLM 4.7, Qwen 3.5) default to
        # chain-of-thought "thinking" mode and emit reasoning into a separate
        # `thinking` field. The user-facing `content` stream only opens
        # AFTER thinking ends — at num_predict=1024 we routinely ran out of
        # budget mid-thought and got zero content. Ollama exposes `think:
        # false` as a per-request opt-out; we always disable thinking so the
        # entire generation budget goes to the cited answer.
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    url = f"http://localhost:{s.ollama_host_port}/api/chat"
    async with httpx.AsyncClient(timeout=600) as client, client.stream(
        "POST",
        url,
        json=payload,
    ) as resp:
        if resp.status_code == 404:
            raw = await resp.aread()
            detail = raw.decode("utf-8", errors="replace").strip()
            raise LLMModelUnavailable(
                _model_unavailable_message(model=model, error=detail)
            )
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("non-json line from ollama: %r", line[:200])
                continue
            if obj.get("done"):
                return
            msg = obj.get("message", {}).get("content", "")
            if msg:
                yield msg


async def chat_once(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    """Non-streaming variant — used by tests."""
    buf: list[str] = []
    async for chunk in stream_chat(messages, model=model, temperature=temperature, max_tokens=max_tokens):
        buf.append(chunk)
    return "".join(buf)


__all__ = [
    "LLMModelUnavailable",
    "build_messages",
    "chat_once",
    "check_model_available",
    "list_available_models",
    "load_answer_prompt",
    "stream_chat",
]
