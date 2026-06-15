# Serialization: `SerializationMixin` + `SerializationProtocol`

> Status: **Stable** in practice — every framework class that supports `to_dict()` / `from_dict()` uses this mixin. The module docstring notes *"in active development; API may change"* ([`_serialization.py:L138-L140`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L138-L140)).
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) at commit `950673b`
> Upstream source: [`python/packages/core/agent_framework/_serialization.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py)

> [!IMPORTANT]
> The module is `agent_framework._serialization` — leading underscore. The classes (`SerializationMixin`, `SerializationProtocol`, `is_serializable`) are **not re-exported** from `agent_framework` directly. Most users get serialization "for free" by subclassing framework base classes (`Message`, `BaseAgent`, `BaseTool`, `AgentSession`, …) which already extend `SerializationMixin`. Importing from the private module is officially possible but treated like an `@experimental` surface — see [`feature-stages.md`](feature-stages.md) for the warning model that applies to all private-module imports.

---

## When you actually touch this API

| Scenario | Likely entry point |
|---|---|
| Persisting agent / session / message state to JSON for a custom store | `instance.to_json()` / `Class.from_json(s)` (inherited from the mixin) |
| Custom executor that needs to ship state between distributed workers | Override `to_dict()` / `from_dict()` on your dataclass-like state class |
| Injecting non-serializable runtime deps at reconstruction time (`AsyncOpenAI` client, DB pool, function callable) | `from_dict(value, dependencies={...})` — see the [3 injection patterns](#dependency-injection-3-patterns) |
| `isinstance(obj, SerializationProtocol)` runtime check in your own helper | `from agent_framework._serialization import SerializationProtocol` (private import) |

If you're **not** doing any of the above, you do not need this page — your `agent.run(...)` calls already serialize messages internally.

---

## `SerializationProtocol`

```python
@runtime_checkable
class SerializationProtocol(Protocol):
    def to_dict(self, **kwargs: Any) -> dict[str, Any]: ...

    @classmethod
    def from_dict(
        cls: type[ProtocolT],
        value: MutableMapping[str, Any],
        /,
        **kwargs: Any,
    ) -> ProtocolT: ...
```

Cited: [`_serialization.py:L22-L110`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L22-L110).

- `@runtime_checkable` — `isinstance(x, SerializationProtocol)` works.
- `from_dict`'s `value` parameter is **positional-only** (note the `/`). Calling `Foo.from_dict(value=d)` raises `TypeError`.
- Any class that implements both methods satisfies the protocol — you do not have to inherit from `SerializationMixin`.

## `is_serializable(value)`

```python
def is_serializable(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict))
```

Cited: [`_serialization.py:L113-L132`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L113-L132).

Returns `True` only for **types JSON can encode directly**. Used by `SerializationMixin.to_dict` to decide whether to keep a value as-is, recurse, or drop it.

---

## `SerializationMixin` — the workhorse

### Class-level configuration

```python
class SerializationMixin:
    DEFAULT_EXCLUDE: ClassVar[set[str]] = set()
    INJECTABLE: ClassVar[set[str]] = set()
    _SHALLOW_COPY_FIELDS: ClassVar[set[str]] = {"raw_representation"}
```

Cited: [`_serialization.py:L265-L267`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L265-L267).

| Class var | Purpose |
|---|---|
| `DEFAULT_EXCLUDE` | Field names that should **never** appear in `to_dict()` output. Framework example: `BaseTool` sets `DEFAULT_EXCLUDE = {"additional_properties"}`. |
| `INJECTABLE` | Field names that are excluded from serialization **and** are expected to be supplied via the `dependencies` parameter on `from_dict`. Framework example: `FunctionTool.INJECTABLE = {"func"}` (the callable can't be JSON-serialized). |
| `_SHALLOW_COPY_FIELDS` | Field names that should be shallow-copied by `copy.deepcopy(instance)` — defaults to `{"raw_representation"}` so the underlying SDK / proto objects on `ChatResponse` etc. aren't deep-copied (which often fails or is prohibitively expensive). |

### `to_dict(*, exclude=None, exclude_none=True)`

Cited: [`_serialization.py:L287-L368`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L287-L368).

Walks `self.__dict__` and emits a dict according to these rules (in order):

1. **Adds a `"type"` field** with the type identifier (unless `"type"` is in `combined_exclude`). See [Type identification](#type-identification-4-tier-priority).
2. **Skips** keys that start with `_` (private), are in `DEFAULT_EXCLUDE`, are in `INJECTABLE`, or in the caller-supplied `exclude` set.
3. **Skips** `None` values when `exclude_none=True` (the default).
4. **Recurses** into nested `SerializationProtocol` instances by calling their `to_dict(exclude=..., exclude_none=...)`.
5. **For `list` fields**: recurses into items that are `SerializationProtocol`; keeps items that pass `is_serializable`; drops everything else with a `logger.debug` ("`Skipping non-serializable item in list attribute …`").
6. **For `dict` fields**: same as lists for values; additionally converts `datetime` / `date` / `time` values to `str(v)`; drops non-serializable values silently (debug log only).
7. **For all other values**: keeps if `is_serializable`; otherwise drops silently with a `logger.debug` ("`Skipping non-serializable attribute …`").

> [!NOTE]
> **Dropped values are silent at INFO level.** If you can't find a field in your serialized output, raise the logger to DEBUG: `logging.getLogger("agent_framework").setLevel(logging.DEBUG)`.

### `to_json(*, exclude=None, exclude_none=True, **kwargs)`

```python
def to_json(self, *, exclude=None, exclude_none=True, **kwargs) -> str:
    return json.dumps(self.to_dict(exclude=exclude, exclude_none=exclude_none), **kwargs)
```

Cited: [`_serialization.py:L370-L388`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L370-L388). `**kwargs` is forwarded to `json.dumps` — pass `indent=2`, `ensure_ascii=False`, etc.

### `from_dict(value, /, *, dependencies=None)` — classmethod

Cited: [`_serialization.py:L390-L558`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L390-L558). Note `value` is **positional-only** (the `/`).

1. Resolves `type_id` via [`_get_type_identifier`](#type-identification-4-tier-priority).
2. **If `value["type"]` is present and doesn't match** → `ValueError(f"Type mismatch: expected '{type_id}', got '{supplied_type}'")`.
3. Strips the `"type"` key, applies dependency injection (3 patterns below), then calls `cls(**kwargs)`.

### `from_json(value, /, *, dependencies=None)` — classmethod

```python
@classmethod
def from_json(cls, value: str, /, *, dependencies=None):
    return cls.from_dict(json.loads(value), dependencies=dependencies)
```

Cited: [`_serialization.py:L560-L585`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L560-L585).

### `__deepcopy__(memo)`

Cited: [`_serialization.py:L269-L285`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L269-L285).

Custom deepcopy that **preserves fields in `_SHALLOW_COPY_FIELDS` by reference**. This exists because LLM SDK responses often contain gRPC/proto types that can't be deep-copied without explosion. If you're seeing `TypeError: cannot pickle '_thread.RLock'` in copy paths, that's the symptom this guard fixes — add your field name to `_SHALLOW_COPY_FIELDS` in your subclass.

---

## Type identification (4-tier priority)

```python
@classmethod
def _get_type_identifier(cls, value: Mapping | None = None) -> str: ...
```

Cited: [`_serialization.py:L587-L616`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L587-L616).

| Rank | Source | Used by |
|---|---|---|
| 1 | `value["type"]` if `value` is given and contains a string `"type"` field | `from_dict` round-trip |
| 2 | Instance attribute `cls.type` if it's a string | classes with per-instance type discriminators |
| 3 | Class attribute `cls.TYPE` if it's a string | most framework classes (`FunctionTool.TYPE = "function_tool"`, …) |
| 4 | `snake_case(cls.__name__)` | fallback — e.g. `WeatherTool` → `"weather_tool"` |

The fallback uses `re.compile(r"(?<!^)(?=[A-Z])").sub("_", cls.__name__).lower()`. Examples: `MyAgent` → `my_agent`, `OpenAIChatClient` → `open_a_i_chat_client` (digits / acronyms not specially handled).

---

## Dependency injection: 3 patterns

`dependencies` is a `dict[str, dict[str, Any]]` keyed by **type identifier**, then by parameter name. The three forms differ in the **inner key**.

### Pattern 1: simple parameter injection

Most common case. Inject a single callable / client / connection by parameter name.

```python
from agent_framework import FunctionTool


async def get_weather(location: str) -> str:
    return f"{location}: 72°F"


# FunctionTool.INJECTABLE = {"func"}
serialized = {
    "type": "function_tool",
    "name": "get_weather",
    "description": "Get current weather",
    # 'func' is excluded — must be re-injected
}

tool = FunctionTool.from_dict(
    serialized,
    dependencies={"function_tool": {"func": get_weather}},
)
```

Cited: [`_serialization.py:L545-L556`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L545-L556).

### Pattern 2: dict-parameter merge

If both the **deserialized value** and the **dependency value** for the same key are `dict`s, they are merged (`update`) rather than overwritten. Useful when you've serialized some keys of a config dict but want to inject runtime credentials into it.

```python
serialized = {
    "type": "my_client",
    "config": {"endpoint": "https://example.com", "timeout": 30},
}

instance = MyClient.from_dict(
    serialized,
    dependencies={"my_client": {"config": {"api_key": "sk-..."}}},
)
# Resulting config: {"endpoint": "...", "timeout": 30, "api_key": "sk-..."}
```

Cited: [`_serialization.py:L552-L554`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L552-L554).

### Pattern 3: instance-specific injection (via `field:value` key)

When you have many instances of the same type but want to inject different deps per-instance (keyed by some discriminating field like `name`), use a key of the form `"<field>:<value>"`.

```python
serialized = {"type": "function_tool", "name": "get_weather"}

dependencies = {
    "function_tool": {
        # Only applied when kwargs["name"] == "get_weather"
        "name:get_weather": {"func": get_weather},
        "name:get_news":    {"func": get_news},
    },
}

tool = FunctionTool.from_dict(serialized, dependencies=dependencies)
# func is get_weather, not get_news, because the loaded dict has name="get_weather"
```

Cited: [`_serialization.py:L523-L544`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L523-L544). The match is exact-string on the kwargs value; if the field isn't present or doesn't match, the dep is skipped silently.

### Unknown injectable warning

If you pass a dependency key that isn't in the target class's `INJECTABLE` set, the mixin **does not raise** — it just emits a `logger.debug` ("`Dependency '<key>' for type '<type>' is not in INJECTABLE set. Available injectable parameters: …`") and still injects the value. This is permissive on purpose so subclasses can extend `INJECTABLE` without breaking parents, but it means typos go silent. ([`_serialization.py:L547-L551`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L547-L551))

---

## Building your own serializable class

```python
from agent_framework._serialization import SerializationMixin


class PipelineState(SerializationMixin):
    TYPE = "pipeline_state"
    DEFAULT_EXCLUDE = {"_cache"}
    INJECTABLE = {"db_pool"}

    def __init__(
        self,
        step: int = 0,
        results: list[dict] | None = None,
        db_pool=None,
    ) -> None:
        self.step = step
        self.results = results or []
        self.db_pool = db_pool
        self._cache: dict = {}


state = PipelineState(step=2, results=[{"name": "x"}])
data = state.to_dict()
# {"type": "pipeline_state", "step": 2, "results": [{"name": "x"}]}

restored = PipelineState.from_dict(
    data,
    dependencies={"pipeline_state": {"db_pool": my_pool}},
)
```

Notes:

- Set `TYPE = "pipeline_state"` explicitly to avoid the snake_case fallback drifting if you rename the class.
- `_cache` is auto-excluded (leading `_`), but also added to `DEFAULT_EXCLUDE` for self-documentation.
- `db_pool` is in `INJECTABLE` so `to_dict()` skips it and `from_dict` knows to inject it.

---

## Common mistakes

| ❌ Wrong | ✅ Right | Why |
|---|---|---|
| `from agent_framework import SerializationMixin` | `from agent_framework._serialization import SerializationMixin` | Mixin is in a private module; subclass framework classes (BaseTool/BaseAgent/etc.) where possible |
| `Foo.from_dict(value=serialized)` | `Foo.from_dict(serialized)` | `value` is positional-only ([`_serialization.py:L392`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L392)) |
| Putting `"type": "wrong_type"` in your serialized data | Strip/regenerate `"type"` if you renamed the class | Triggers `ValueError("Type mismatch: expected '<x>', got '<y>'")` ([`L514-L515`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py#L514-L515)) |
| Storing an `asyncio.Lock` / open file handle / DB connection as an instance attribute → silently dropped from `to_dict()` output | Mark it as `INJECTABLE` and re-supply via `dependencies` on `from_dict` | `to_dict` silently drops non-serializable values (debug log only) |
| Subclassing without setting `TYPE` and shipping the snake_case fallback to production | Always set `TYPE = "..."` explicitly on persisted classes | Rename refactors silently change the on-disk type identifier and break round-trips |
| Catching `KeyError` on a missing `"type"` field | The mixin only validates `"type"` *when present*; missing → uses `cls`'s own identifier | No exception is raised when `"type"` is missing |

---

## Worked example: round-trip a Message

`Message` already extends `SerializationMixin` — this is the most common surface contact.

```python
from agent_framework import Message

msg = Message(role="user", contents=["What's the weather like today?"])

data = msg.to_dict()
# {
#   "type": "chat_message",
#   "role": {"type": "role", "value": "user"},
#   "contents": [{"type": "text_content", "text": "What's the weather like today?"}],
#   "message_id": "...",
#   "additional_properties": {}
# }

restored = Message.from_dict(data)
assert restored.text == "What's the weather like today?"
```

---

## See also

- [`feature-stages.md`](feature-stages.md) — warning model that applies to private-module imports
- [`compaction.md`](compaction.md) — works on `Message` instances and relies on the same serialization round-trip
- [`sessions.md`](sessions.md) — `AgentSession.state` is round-tripped via this mixin

---

**Upstream source**: [`python/packages/core/agent_framework/_serialization.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_serialization.py) (616 LOC, fully verified)
