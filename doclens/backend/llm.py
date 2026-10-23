"""OpenAI-compatible client. Point LLM_BASE_URL at vLLM on Kaggle (via tunnel) or any compatible API."""
import os

import openai


class LLMUnavailable(Exception):
    pass


def chat(messages: list[dict], schema: dict | None = None, max_tokens: int = 1024) -> str:
    """One chat completion. With `schema`, the server is asked for JSON matching it (vLLM guided decoding)."""
    model = os.environ.get("LLM_MODEL")
    if not model:
        raise LLMUnavailable("LLM_MODEL is not set")
    client = openai.OpenAI(
        base_url=os.environ.get("LLM_BASE_URL"),
        api_key=os.environ.get("LLM_API_KEY", "none"),
        timeout=60,
        max_retries=1,
    )
    extra = {}
    if schema:
        extra["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
    try:
        r = client.chat.completions.create(
            model=model, messages=messages, temperature=0, max_tokens=max_tokens, **extra
        )
    except openai.APIError as e:
        raise LLMUnavailable(f"LLM unreachable — check LLM_BASE_URL ({type(e).__name__})") from e
    return r.choices[0].message.content or ""
