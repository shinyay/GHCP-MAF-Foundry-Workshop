# Pattern: Structured Output with Pydantic BaseModel

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: parent demo `src/demo4_structured_output.py`
> See also: [API ref — `structured-output.md`](../api-reference/1.8.0/structured-output.md)

## Goal

Force the agent to return a **parsed Pydantic instance** instead of free-form text. Use this whenever your downstream code expects structured data (DB row, API payload, decision tree, etc.).

## When to use

- ✅ The agent's output feeds into typed code (e.g., builds an HTTP request body, writes to a database).
- ✅ You want compile-time guarantees on field names and types.
- ✅ You want the model to gracefully omit fields it's unsure about (use `Optional[...]`).
- ❌ The agent should write prose for a human — use plain `agent.run(...)` and read `.text`.
- ❌ You need streaming **of the structured fields incrementally** — not supported in 1.8.0; use non-streaming.

## Code

```python
import asyncio
import os
from pathlib import Path
from typing import Annotated, Optional

from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.models import (
    BingGroundingSearchConfiguration,
    BingGroundingSearchToolParameters,
    BingGroundingTool,
)
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values
from pydantic import BaseModel, Field


for k, v in dotenv_values(Path(__file__).resolve().parents[1] / ".env").items():
    if v is not None and not (os.getenv(k) or "").strip():
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


# --- 1. Define the response schema with Pydantic ---
class Venue(BaseModel):
    """A single venue recommendation."""

    name: str = Field(description="Venue name")
    address: Optional[str] = Field(default=None, description="Street address")
    capacity: Optional[int] = Field(default=None, description="Maximum occupancy")
    notes: str = Field(description="Why this venue is a good match")


class VenueShortlist(BaseModel):
    """The agent's complete answer."""

    city: str
    options: list[Venue] = Field(description="3–5 candidate venues, sorted by best fit")


# --- 2. Build a Bing tool (optional but useful for real data) ---
def _build_bing_tool() -> dict:
    cid = _require_env("BING_CONNECTION_ID")
    cfg = BingGroundingSearchConfiguration()
    cfg.project_connection_id = cid
    cfg.market = "en-US"
    cfg.count = 5
    return BingGroundingTool(
        bing_grounding=BingGroundingSearchToolParameters(search_configurations=[cfg])
    ).as_dict()


# --- 3. Run and parse ---
async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=project_endpoint, model=model, credential=cred
        )
        async with client.as_agent(
            name="venue_analyst",
            instructions=(
                "You research venues. ALWAYS return JSON that exactly matches the "
                "VenueShortlist schema. Do not include prose outside the JSON."
            ),
            tools=[_build_bing_tool()],
        ) as agent:
            result = await agent.run(
                "Find 3 venues for a 50-person corporate event in Seattle in Dec 2026.",
                options={"response_format": VenueShortlist},
            )

    # result.value is the parsed Pydantic instance
    shortlist: VenueShortlist = result.value
    for v in shortlist.options:
        print(f"- {v.name} (cap: {v.capacity}) — {v.notes}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| `options={"response_format": VenueShortlist}` per-call | This is the **per-run override** form. You can also bake it into every run on the agent via `client.as_agent(..., default_options={"response_format": VenueShortlist})`. Note: `response_format=` is **not** a direct constructor kwarg on `as_agent(...)` in 1.8.0 — it must go through `default_options=`. |
| `result.value` (not `result.text`) | `.value` is the parsed Pydantic instance. `.text` is still the raw JSON string. Always read `.value` for structured output. |
| `Field(description="...")` | Becomes the field description in the JSON schema sent to the model. The model uses it to decide what to put in each field. |
| `Optional[int] = Field(default=None, ...)` | Models often don't have enough info for every field. Allowing `None` prevents hallucinated values. |
| Explicit instruction: "JSON that matches the schema" | The framework already enforces the schema, but mentioning it in `instructions` reduces malformed-JSON retries. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Reading `result.text` and `json.loads(...)` manually | Just read `result.value`. The framework already parsed it. |
| Putting `response_format=...` as a top-level kwarg on `agent.run(...)` | It belongs **inside** `options={"response_format": ...}` per the 1.8.0 API. |
| Using `dataclass` or `TypedDict` instead of `BaseModel` | Only Pydantic `BaseModel` is supported as a schema source in 1.8.0. |
| Schema fields with **no** descriptions | The model fills them in randomly. Always use `Field(description="...")`. |
| Required fields the model can't always supply | Use `Optional[...] = Field(default=None, ...)` for soft fields. |
| Streaming with `stream=True` and expecting partial parsed objects | 1.8.0 streams text deltas only. Use non-streaming for structured output. |

## Verification

```bash
python path/to/this/script.py
```

Expected: prints 3 lines, each a parsed venue with name and notes.

## See also

- [`structured-output.md`](../api-reference/1.8.0/structured-output.md) — full `response_format` reference
- [`hosted-bing-search.md`](hosted-bing-search.md) — Bing config
- [`canonical-agent-creation.md`](canonical-agent-creation.md)
