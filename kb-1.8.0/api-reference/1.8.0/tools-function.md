# Tools: Python function tools

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: introspection of `agent_framework.tool` + parent demo `src/demo1_run_agent.py`

A "Python function tool" is any plain Python callable you put into `tools=[...]` on `client.as_agent(...)`. The Agent Framework introspects the callable's signature, type hints, and docstring to produce the JSON schema the model sees.

You have two equivalent ways to author one: a plain callable, or with the `@tool` decorator.

---

## Form 1 — plain callable (simplest)

```python
from typing import Annotated
from pydantic import Field

def get_current_weather(
    city: Annotated[str, Field(description="City name, e.g. 'Seattle'")],
    units: Annotated[str, Field(description="'celsius' or 'fahrenheit'")] = "celsius",
) -> str:
    """Return the current weather in a single short sentence."""
    return f"It's 12°{units[0].upper()} and raining in {city}."

# Wire it in:
async with client.as_agent(
    name="weather_bot",
    instructions="You answer weather questions.",
    tools=[get_current_weather],
) as agent:
    ...
```

What the framework extracts:

| From | Used for |
|------|---------|
| Function name `get_current_weather` | Tool name shown to the model |
| Docstring (first sentence) | Tool description |
| `Annotated[str, Field(description=...)]` | Per-parameter description |
| Parameter type hints (`str`, `int`, `bool`, `list[X]`, `dict`, Pydantic models) | JSON schema generation |
| Default values | Marks the param as optional |
| Return type | Surfaced in tracing / logs |

> [!IMPORTANT]
> **Docstring matters.** The model decides whether to call your tool based largely on the docstring. Write it as if it were the tool description (because it is). One short sentence is ideal.

---

## Form 2 — `@tool` decorator (when you need explicit naming)

```python
from agent_framework import tool

@tool(name="weather_lookup", description="Look up current weather for a city.")
def get_current_weather(city: str, units: str = "celsius") -> str:
    return f"It's 12°{units[0].upper()} in {city}."
```

Use `@tool` when:

- You want a tool name different from the function name (e.g. snake_case in the API but a friendly display name)
- You want to override the description without changing the docstring
- You want to attach metadata (e.g. `tool_choice` hints) per-tool

For most cases, the plain callable form is enough.

---

## Async tools

```python
import httpx

async def fetch_url(url: str) -> str:
    """Fetch a URL and return its body as text."""
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(url)
        return r.text[:4000]
```

Async tools are first-class — the runtime awaits them. Prefer async whenever the tool does I/O, otherwise you'll block the event loop while the model is waiting.

---

## Error handling inside tools

The runtime catches exceptions raised inside your tool and surfaces them to the model as a tool error result. The model can then retry, ask a clarifying question, or apologise to the user.

For **expected** errors (bad input, missing resource), raise a plain `ValueError` / `LookupError` with a message useful to the model:

```python
def get_event_record(event_id: str) -> dict:
    """Look up an event by its ID."""
    record = _store.get(event_id)
    if record is None:
        raise LookupError(
            f"No event with id={event_id!r}. Valid IDs look like 'evt_<8-char-hex>'."
        )
    return record
```

For **unexpected** errors (network down, internal bug), let them propagate — Agent Framework wraps them in a `ToolException` and the surrounding `Agent.run(...)` raises an `AgentException` subclass. See [`exceptions.md`](exceptions.md).

---

## Type hints the runtime understands

| Type | Schema |
|------|--------|
| `str` / `int` / `float` / `bool` | Primitives |
| `list[T]` | Array of T |
| `dict[str, T]` | Object with arbitrary keys → T |
| `Literal["a", "b"]` | Enum |
| `T \| None` / `Optional[T]` | Marks param nullable |
| Pydantic `BaseModel` | Nested object with full schema |
| `Annotated[T, Field(description=...)]` | Adds description to T |
| `Annotated[T, Field(ge=0, le=100)]` | Adds validation constraints |

Anything else (custom dataclasses without Pydantic, opaque types) becomes a JSON `object` and the model loses guidance — avoid it.

---

## Multiple tools

```python
tools = [
    get_current_weather,
    fetch_url,
    get_event_record,
    # mix with hosted/MCP tools freely:
    client.get_code_interpreter_tool().as_dict(),
    MCPStdioTool(name="seq-thinking", command="npx",
                 args=["-y", "@modelcontextprotocol/server-sequential-thinking"]),
]
async with client.as_agent(name="planner", instructions="...", tools=tools) as agent:
    ...
```

The model picks which tool(s) to call. You can bias selection with `tool_choice` in `options=`.

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| No docstring | Add a one-sentence description. Model often won't call your tool without one. |
| Untyped params (`def f(x, y):`) | Add type hints — runtime can't infer the schema otherwise. |
| Async I/O in a sync function | Make the tool `async` and `await` the I/O. |
| Catching every exception inside the tool | Let `ValueError`/`LookupError` propagate with useful messages — the model recovers better than your `except` does. |
| Returning a large blob (e.g. 1MB JSON) | Summarise. Tool returns become part of the conversation and cost tokens. |

---

## See also

- [`agents.md`](agents.md) — passing tools to `client.as_agent(...)`
- [`tools-hosted.md`](tools-hosted.md) — combining function tools with hosted tools
- [`tools-mcp.md`](tools-mcp.md) — combining with MCP tools
- [`../../patterns/canonical-agent-creation.md`](../../patterns/canonical-agent-creation.md) — full recipe with a function tool
