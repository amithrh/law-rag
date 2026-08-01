"""Ollama client wrapper — streaming + sync.

The verifier topology (PLAN §4.3) gates emission on per-sentence verification.
This module just speaks to Ollama; the verifier orchestration lives in main.py.
"""
from __future__ import annotations

import json
import logging
import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from apps.api.config import get_settings

logger = logging.getLogger(__name__)

_generation_slots: asyncio.Semaphore | None = None
_generation_slot_limit: int | None = None
_generation_slot_loop: asyncio.AbstractEventLoop | None = None
_model_preflight_cache: dict[str, tuple[float, dict]] = {}
_model_preflight_lock: asyncio.Lock | None = None
_model_preflight_lock_loop: asyncio.AbstractEventLoop | None = None


def _generation_semaphore() -> asyncio.Semaphore:
    """Return the per-process limiter for the configured Ollama capacity."""
    global _generation_slots, _generation_slot_limit, _generation_slot_loop
    settings = get_settings()
    limit = int(getattr(settings, "llm_max_concurrent", 1))
    loop = asyncio.get_running_loop()
    if (
        _generation_slots is None
        or _generation_slot_limit != limit
        or _generation_slot_loop is not loop
    ):
        _generation_slots = asyncio.Semaphore(limit)
        _generation_slot_limit = limit
        _generation_slot_loop = loop
    return _generation_slots


class LLMModelUnavailable(RuntimeError):
    """Raised when the configured Ollama model is not available locally."""


def _ollama_url(path: str) -> str:
    s = get_settings()
    host = getattr(s, "resolved_ollama_api_host", "127.0.0.1")
    port = getattr(s, "resolved_ollama_api_port", s.ollama_host_port)
    return f"http://{host}:{port}{path}"


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
    url = _ollama_url("/api/tags")
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
    """Cheap, single-flight preflight for /answer.

    A burst of answer requests must not turn the inexpensive ``/api/tags``
    check into a second overload of Ollama. Results are cached briefly and
    concurrent callers share one probe. The generation request still handles
    a model disappearing after this check, so the cache cannot authorize an
    unsafe answer.
    """
    s = get_settings()
    target = model or s.llm_model
    ttl = float(getattr(s, "llm_preflight_cache_sec", 5.0))

    def cached(now: float) -> dict | None:
        item = _model_preflight_cache.get(target)
        if item is None or ttl <= 0 or now - item[0] >= ttl:
            return None
        status = item[1]
        return {**status, "available_models": list(status.get("available_models") or [])}

    now = time.monotonic()
    hit = cached(now)
    if hit is not None:
        return hit

    global _model_preflight_lock, _model_preflight_lock_loop
    loop = asyncio.get_running_loop()
    if _model_preflight_lock is None or _model_preflight_lock_loop is not loop:
        _model_preflight_lock = asyncio.Lock()
        _model_preflight_lock_loop = loop

    async with _model_preflight_lock:
        hit = cached(time.monotonic())
        if hit is not None:
            return hit
        previous = _model_preflight_cache.get(target)
        try:
            available_models = await list_available_models()
        except Exception as e:
            error = str(e)
            status = {
                "ok": False,
                "model": target,
                "available_models": [],
                "error": error,
                "message": _model_unavailable_message(model=target, error=error),
            }
        else:
            ok = target in available_models
            if not ok and ":" not in target:
                ok = f"{target}:latest" in available_models
            status = {
                "ok": ok,
                "model": target,
                "available_models": available_models,
                "error": None if ok else "model_not_found",
                "message": None if ok else _model_unavailable_message(
                    model=target,
                    available_models=available_models,
                ),
            }
        # Never cache a negative probe. A transient Ollama /api/tags timeout
        # must not turn a short dependency blip into a burst-wide refusal;
        # callers will still share the in-flight probe through the lock.
        if ttl > 0 and status.get("ok"):
            _model_preflight_cache[target] = (time.monotonic(), status)
        elif previous is not None and previous[1].get("ok"):
            # /api/tags is an observability probe, not the authority to answer
            # a request. Keep the last known-good state through a transient
            # probe failure and let /api/chat be the final liveness check. If
            # the model really disappeared, stream_chat still emits the safe
            # llm_unavailable handoff.
            logger.warning(
                "model preflight refresh failed; using last known-good model state"
            )
            stale = previous[1]
            return {
                **stale,
                "available_models": list(stale.get("available_models") or []),
                "stale": True,
            }
        return {**status, "available_models": list(status.get("available_models") or [])}


def clear_model_preflight_cache() -> None:
    """Clear cached model probes for tests and controlled operator changes."""
    _model_preflight_cache.clear()


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
        source_type = str(p.get("source_type") or "").strip().lower()
        if source_type:
            readable_type = {
                "bare_act": "Bare Act",
                "sc_judgment": "Supreme Court judgment",
                "hc_judgment": "High Court judgment",
                "rule": "Rule",
                "regulation": "Regulation",
                "scheme": "Scheme",
                "guideline": "Guideline",
                "circular": "Circular",
                "notification": "Notification",
            }.get(source_type, source_type.replace("_", " ").title())
            meta_bits.insert(0, f"TYPE: {readable_type}")
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
    url = _ollama_url("/api/chat")
    slots = _generation_semaphore()
    wait_sec = float(getattr(s, "llm_admission_wait_sec", 120.0))
    try:
        await asyncio.wait_for(slots.acquire(), timeout=wait_sec)
    except TimeoutError as exc:
        message = (
            f"Ollama generation capacity was busy for {wait_sec:.0f} seconds; "
            "retry the request."
        )
        logger.warning("ollama generation admission timed out: %s", message)
        raise LLMModelUnavailable(message) from exc
    try:
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
    except LLMModelUnavailable:
        raise
    except (httpx.HTTPError, OSError, TimeoutError) as exc:
        # Treat connection, timeout, 5xx, and mid-stream transport failures
        # as an unavailable answer model. The API owns the safe handoff.
        logger.warning("ollama answer stream unavailable: %s", exc)
        raise LLMModelUnavailable(
            _model_unavailable_message(model=model, error=str(exc))
        ) from exc
    finally:
        slots.release()


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
    "clear_model_preflight_cache",
    "list_available_models",
    "load_answer_prompt",
    "stream_chat",
]
