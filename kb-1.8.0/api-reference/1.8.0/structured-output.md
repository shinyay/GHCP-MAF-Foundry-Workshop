# Structured output (`response_format=`)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: parent demo `src/demo4_structured_output.py` lines 95-194

When you need the agent's output as a **typed Python object** (not free-form text), pass a Pydantic `BaseModel` as `response_format`. The model is constrained to emit JSON matching the schema, and you get back a parsed instance on `result.value`.

---

## Recipe (canonical)

From parent demo `src/demo4_structured_output.py`:

```python
from pydantic import BaseModel

class VenueInfoModel(BaseModel):
    """Information about a venue."""
    title: str | None = None
    description: str | None = None
    services: str | None = None
    address: str | None = None
    estimated_cost_per_person: float = 0.0

class VenueOptionsModel(BaseModel):
    """Options for a venue."""
    options: list[VenueInfoModel]


async with client.as_agent(
    name="venue_specialist",
    instructions=(
        "You are the Venue Specialist. Find venue options and return only structured "
        "data that matches the provided schema."
    ),
    tools=[bing_tool],
) as agent:
    response = await agent.run(
        "Find venue options for a 50-person event in Seattle.",
        options={"response_format": VenueOptionsModel},   # <-- the key bit
    )

venue_options = response.value          # parsed VenueOptionsModel instance
for option in venue_options.options:
    print(option.title, "—", option.estimated_cost_per_person)
```

---

## Where to put `response_format`

Two equivalent forms:

### Form 1 — per-call via `options=` (recommended)

```python
response = await agent.run(query, options={"response_format": MyModel})
```

Use when different runs of the same agent need different schemas.

### Form 2 — at agent creation (apply to every run)

```python
async with client.as_agent(
    name="...",
    instructions="...",
    default_options={"response_format": MyModel},  # baked into every run
) as agent:
    response = await agent.run(query)
```

Use when the agent always returns the same schema. **Note:** `response_format=` is **not** a direct constructor kwarg on `as_agent(...)`; it must go through `default_options=`. Per-call `options=` shallow-merges over `default_options=`.

> [!NOTE]
> When `response_format` is set via `default_options`, `response.value` is parsed at runtime but the **static type** of `.value` is `Any`, not `MyModel`. Use per-call `options={"response_format": MyModel}` (Form 1) when you want the typed return. See [`_agents.py:L699`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L699).

---

## Accessing the parsed result

| Field | Content |
|-------|---------|
| `response.value` | The parsed `BaseModel` instance (or None if structured output failed) |
| `response.text` | The raw JSON string the model produced |
| `response.messages` | The message list (the last assistant message contains the JSON) |

Always check `response.value is not None` — if the model failed to comply with the schema, `value` may be None and you should fall back to `response.text`.

---

## Tips for reliable structured output

| Tip | Why |
|-----|-----|
| Add a docstring to every Pydantic model + field (`Field(description=...)`) | The model uses these as guidance — empty descriptions hurt accuracy. |
| Make fields **optional with defaults** (`x: str \| None = None`) | Lets the model partially fill if it can't find all data. |
| Avoid deeply nested `Union[...]` / discriminated unions | Some models choke. Prefer flat shapes. |
| State "return only data that matches the schema" explicitly in instructions | Reduces narration text leaking outside the JSON. |
| For lists, wrap in a top-level model (`{"options": [...]}`) instead of returning a bare array | Many model deployments require the top-level value to be an object. |

---

## Combining with tools

Structured output is fully compatible with tools (function tools, hosted, MCP). The model calls tools as needed, then formats its final response per the schema:

```python
tools=[bing_tool, code_interpreter_tool]
response = await agent.run(query, options={"response_format": MyModel})
```

The intermediate tool calls don't disrupt the schema constraint on the final answer.

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Using `dataclass` instead of Pydantic `BaseModel` | The runtime only generates schema from Pydantic. Migrate. |
| Empty docstrings / no `Field(description=...)` | Add them — they're how the model knows what to fill. |
| Returning `Union[A, B]` at the top level | Wrap each in a top-level object (`{"variant": "A", "data": {...}}`) or use discriminated unions sparingly. |
| Reading `response.text` and parsing yourself with `json.loads` | Use `response.value` — it's already parsed. |
| Not handling `response.value is None` | The model may fail the schema. Add a fallback. |

---

## See also

- [`agents.md`](agents.md#optionsmodel--most-common-keys) — passing `options=`
- [`../../patterns/structured-output-pydantic.md`](../../patterns/structured-output-pydantic.md) — full recipe
- [Pydantic docs — Field](https://docs.pydantic.dev/latest/api/fields/) (use Field for descriptions/constraints)
