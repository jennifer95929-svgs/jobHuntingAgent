from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
import httpx

_client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    http_client=httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)),
    max_retries=0,
)


def call_tool(messages: list, tools: list, **kwargs) -> str:
    resp = _client.chat.completions.create(
        model=kwargs.get("model", LLM_MODEL),
        messages=messages,
        tools=tools,
        tool_choice=kwargs.get("tool_choice", "auto"),
        temperature=kwargs.get("temperature", 0.0),
        seed=kwargs.get("seed", 42),
        max_tokens=kwargs.get("max_tokens", 2048),
    )
    return resp.choices[0].message


def call_light(system: str, user: str) -> str:
    from config import MODEL_LIGHT
    resp = _client.chat.completions.create(
        model=MODEL_LIGHT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        seed=42,
        max_tokens=1024,
    )
    return resp.choices[0].message.content or ""


def call_heavy(system: str, user: str) -> str:
    from config import MODEL_HEAVY
    resp = _client.chat.completions.create(
        model=MODEL_HEAVY,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        seed=42,
        max_tokens=2048,
    )
    return resp.choices[0].message.content or ""
