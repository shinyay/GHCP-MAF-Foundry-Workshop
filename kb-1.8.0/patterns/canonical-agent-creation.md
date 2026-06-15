# Pattern: Canonical Agent Creation (with a Python function tool)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: `templates/single-agent/main.py` + parent demo `src/demo1_run_agent.py`
> See also: [API ref — `agents.md`](../api-reference/1.8.0/agents.md), [`tools-function.md`](../api-reference/1.8.0/tools-function.md)

## Goal

Build a single agent that can answer questions using a custom Python function as a tool. This is the **starting point** for almost everything in Agent Framework — multi-agent workflows, RAG, hosted tools, etc. all extend this base.

## When to use this pattern

- ✅ You want one agent with one or more **deterministic Python tools** (lookups, calculations, format conversions, etc.).
- ✅ You want the absolute minimum runnable agent to validate your Foundry setup.
- ❌ You need Bing search / file search / code interpreter — those are **hosted tools** (see Section "Variations" below).
- ❌ You need multiple agents that hand off to each other — that's a **workflow** (out of PoC scope).

## Code

```python
import asyncio
import os
import socket
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


# --- 1. Load .env (fill-only, don't override) ---
_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
for _k, _v in dotenv_values(_DOTENV_PATH).items():
    if _v is None:
        continue
    if not (os.getenv(_k) or "").strip():
        os.environ[_k] = _v


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable is missing or empty: {name}. "
            "Set it via .env / export / Codespaces secrets and try again."
        )
    return value


# --- 2. Define the tool as a plain Python function ---
def get_weather(
    city: Annotated[str, "City name in English, e.g., 'Tokyo'."],
) -> str:
    """Return a short, plain-text weather description for the given city."""
    fake_data = {
        "Tokyo": "Sunny, 22°C, light breeze",
        "Seattle": "Cloudy, 14°C, light rain",
        "New York": "Partly cloudy, 18°C",
    }
    return fake_data.get(city, f"No data available for {city}.")


# --- 3. Wire the agent and run ---
async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")

    async with AzureCliCredential() as cred:
        async with FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=cred,
        ).as_agent(
            name="weather_specialist",
            instructions="You answer weather questions concisely using the get_weather tool.",
            tools=[get_weather],
        ) as agent:
            result = await agent.run("What's the weather like in Tokyo?")
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

| Piece | Why |
|------|-----|
| **`dotenv_values(...)` + fill-only loop** | Codespaces / Dev Containers may inject env vars as **empty strings**. `dotenv.load_dotenv()`'s default behavior won't fill them in. The fill-only pattern preserves intentional overrides (`VAR=... python ...`) while still populating missing values. |
| **`_require_env(...)` with explicit error** | Fail fast at startup, not at the API call. The error message tells the user what to do next. |
| **`AzureCliCredential` (async)** | Default Entra ID auth. Requires `az login`. Use the **async** version (`azure.identity.aio`) — the sync version blocks the event loop. |
| **`async with` for credential and client** | These hold HTTP sessions / token caches. Without `async with`, you'll leak connections and may see "Event loop is closed" warnings at shutdown. |
| **`client.as_agent(..., tools=[fn])`** | Canonical 1.8.0 form. The framework inspects the function's type hints and docstring to generate the tool schema for the LLM. |
| **`Annotated[str, "..."]`** | Gives the LLM a richer description of each parameter than the type alone. Strongly recommended for any tool with non-obvious params. |
| **`await agent.run(...)`** | Non-streaming. For streaming UI, use `agent.run(..., stream=True)` and `async for` over the result. |

## Common mistakes

| Mistake | Fix |
|--------|-----|
| `pip install agent-framework` (the meta package) | Use `agent-framework-foundry==1.8.0`. The meta overwrites `agent_framework/__init__.py` and breaks imports. |
| `from azure.identity import AzureCliCredential` (sync) | Use `from azure.identity.aio import AzureCliCredential`. |
| Calling `await agent.run_stream(...)` | `run_stream` was **removed in 1.5.0**. Use `agent.run(..., stream=True)`. |
| Forgetting `async with` on the credential | Leaked HTTP session + "Unclosed connector" warnings at shutdown. |
| Tool function with no type hints | The LLM gets a useless schema. Always type-hint args and return value. |
| Tool function with no docstring | Same as above. Docstrings become the tool's description for the LLM. |

## Variations (next steps)

### Add a hosted Bing web search tool

```python
bing_tool = client.get_web_search_tool(connection_id=os.environ["BING_CONNECTION_ID"])

async with client.as_agent(
    name="research_agent",
    instructions="...",
    tools=[get_weather, bing_tool],
) as agent:
    ...
```

You'll need a Bing grounding connection in your Foundry project. See [Microsoft Learn: Grounding with Bing Search](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/tools/bing-grounding).

### Stream the response (e.g., for a CLI/UI)

```python
async for chunk in agent.run("...", stream=True):
    # chunk shape can vary; for CLI just collect deltas.
    text = getattr(chunk, "text", None) or getattr(chunk, "content", None) or ""
    print(text, end="", flush=True)
```

### Disable instrumentation (1.6.0 default is ON)

```python
from agent_framework.observability import disable_instrumentation
disable_instrumentation()  # call BEFORE constructing any agent/client
```

---

## Verification

```bash
python3 -m compileall -q templates/single-agent/main.py
python templates/single-agent/main.py
```

Expected output:

```
Sunny, 22°C, light breeze
```

(The exact wording will vary because the LLM rephrases the tool's raw output.)
