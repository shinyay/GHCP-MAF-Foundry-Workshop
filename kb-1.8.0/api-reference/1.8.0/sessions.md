# Sessions and Context Providers

> Status: **Stable** (with one `@experimental` class noted)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent_framework/_sessions.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py)

Sessions own **conversation history**, **provider-injected context**, and **cross-call state**. The framework's session model is two-layered:

1. **`AgentSession`** — a lightweight state container (`session_id`, optional `service_session_id`, a `state: dict[str, Any]`).
2. **`ContextProvider`** (and `HistoryProvider` subclass) — pluggable hooks that run before/after every model invocation and read/write the session.

Both are top-level exports of `agent_framework`.

## `AgentSession`

[`_sessions.py:L711-L776`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L711-L776).

```python
from agent_framework import AgentSession

session = AgentSession()                              # auto-generates session_id (UUID4)
session = AgentSession(session_id="user-42")          # explicit id
session = AgentSession(service_session_id="conv-123") # service-managed (e.g., Foundry conversation)
```

| Attribute | Type | Notes |
|-----------|------|-------|
| `session_id` | `str` | Property — defaults to `uuid.uuid4()` ([line 735](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L735)). |
| `service_session_id` | `str \| None` | Set when the chat service stores history server-side (e.g., Foundry threads). |
| `state` | `dict[str, Any]` | Free-form per-provider state. `provider.source_id` is the conventional key prefix. |

### Serialization

`session.to_dict()` / `AgentSession.from_dict(data)` round-trip the session. Any value in `state` that implements `SerializationProtocol` (`to_dict` / `from_dict`) is restored to its concrete type; plain JSON types are kept as-is. Register custom types with `register_state_type(cls)` ([`_sessions.py:L66`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L66)) so deserialization can find them.

## `SessionContext` — per-invocation scratch space

[`_sessions.py:L151-L345`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L151-L345).

Created fresh for **each** `agent.run()`. Providers mutate it in `before_run`; the framework reads it to assemble the actual model call.

| Field | Set by | Purpose |
|-------|--------|---------|
| `session_id` / `service_session_id` | framework | Identifiers passed to providers. |
| `input_messages` | caller | The new user-side messages for this invocation. |
| `context_messages` | providers (`extend_messages`) | `dict[source_id, list[Message]]` — context to prepend. |
| `instructions` | providers (`extend_instructions`) | Additional system instructions. |
| `tools` | providers (`extend_tools`) | Additional tools. |
| `middleware` | providers (`extend_middleware`) | `dict[source_id, list[MiddlewareTypes]]`. **Only chat/function middleware allowed** (raises `MiddlewareException` if a provider adds agent middleware — [`_sessions.py:L300`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L300)). |
| `response` | framework (after the run) | Read in `after_run` to react to the model output. |
| `options` | caller | Read-only run options (for reflection). |
| `metadata` | providers | Cross-provider scratch space. |

`SessionContext.get_messages(...)` ([line 312](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L312)) returns a flattened conversation in provider execution order, with optional `sources=`, `exclude_sources=`, `include_input`, `include_response` filters.

> [!NOTE]
> Each message inserted via `extend_messages` is **copied** and stamped with `additional_properties["_attribution"] = {"source_id": ..., "source_type": ...}` so downstream providers can filter by origin ([`_sessions.py:L240-L248`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L240-L248)).

## `ContextProvider`

[`_sessions.py:L348-L407`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L348-L407).

```python
from agent_framework import ContextProvider, SessionContext, AgentSession

class TimestampProvider(ContextProvider):
    def __init__(self) -> None:
        super().__init__(source_id="timestamp")

    async def before_run(self, *, agent, session, context, state):
        from datetime import datetime
        context.extend_instructions(self.source_id, f"Current UTC time: {datetime.utcnow().isoformat()}")

    async def after_run(self, *, agent, session, context, state):
        # context.response is now populated
        ...
```

The `state` parameter is **provider-scoped** — it is `session.state.setdefault(provider.source_id, {})` and persists across `agent.run()` calls within the same session.

> [!IMPORTANT]
> `source_id` is **required** and must be unique per provider instance. Two providers with the same `source_id` will overwrite each other's attribution.

## `HistoryProvider` — pluggable history storage

[`_sessions.py:L410-L531`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L410-L531).

A `ContextProvider` subclass that handles the load-before / save-after pattern automatically. Subclasses implement just two methods:

```python
async def get_messages(self, session_id, *, state=None, **kwargs) -> list[Message]: ...
async def save_messages(self, session_id, messages, *, state=None, **kwargs) -> None: ...
```

Configuration flags ([line 431](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L431)):

| Flag | Default | Effect |
|------|---------|--------|
| `load_messages` | `True` | Call `get_messages()` in `before_run`. Set `False` for audit/logging-only sinks. |
| `store_inputs` | `True` | Persist the user-side input messages. |
| `store_context_messages` | `False` | Persist messages contributed by *other* providers. |
| `store_context_from` | `None` | If set, only persist context from the listed source_ids. |
| `store_outputs` | `True` | Persist the model response messages. |

### Built-in providers

#### `InMemoryHistoryProvider`

[`_sessions.py:L779-L856`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L779-L856).

Stores messages in `session.state["messages"]`. **This is the default** provider auto-attached for local sessions when no providers are configured and the chat service does not manage history server-side ([line 789](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L789)).

```python
from agent_framework import InMemoryHistoryProvider

provider = InMemoryHistoryProvider(
    skip_excluded=True,        # honor _excluded flags from CompactionProvider
)
```

`DEFAULT_SOURCE_ID: ClassVar[str] = "in_memory"`.

#### `FileHistoryProvider` ⚠️ `@experimental`

[`_sessions.py:L858-L1099`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L858) — decorated `@experimental(feature_id=ExperimentalFeature.FILE_HISTORY)`. Writes one JSONL file per session. Plaintext on local disk — **not encrypted**.

> [!WARNING]
> `@experimental` APIs may change without notice between minor versions. Pin to `agent-framework-foundry==1.8.0` exactly if you depend on `FileHistoryProvider`. See [`feature-stages.md`](feature-stages.md) for the full warning model and how to silence/track the `[FILE_HISTORY] ... ExperimentalWarning`.

## Wiring it up

```python
import os
from agent_framework import AgentSession, ContextProvider, InMemoryHistoryProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async with AzureCliCredential() as cred:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=cred,
    )
    async with client.as_agent(
        name="assistant",
        instructions="You are a helpful assistant.",
        context_providers=[
            TimestampProvider(),                       # custom
            InMemoryHistoryProvider(),                 # explicit
        ],
    ) as agent:
        session = AgentSession()
        response1 = await agent.run("Hello!", session=session)
        response2 = await agent.run("What did I just say?", session=session)  # history loaded
```

> [!NOTE]
> `FoundryChatClient` itself is **not** an async context manager in 1.8.0 — only the `credential` and the `Agent` returned by `client.as_agent(...)` are. Constructing `client` as a bare value (not wrapped in `async with`) is the canonical Pattern C used throughout this KB. See [`kb/api-reference/1.8.0/clients.md § Lifecycle`](clients.md#lifecycle) and [`kb/anti-patterns/missing-async-with-cleanup.md`](../../anti-patterns/missing-async-with-cleanup.md).

## Service-managed history (Foundry / OpenAI Assistants)

When the chat service stores conversation history server-side (e.g., Foundry threads or OpenAI Assistants), set `session.service_session_id` and skip local history providers. The framework detects `service_session_id` is set and routes accordingly — `InMemoryHistoryProvider` is **not** auto-added in that case.

## `PerServiceCallHistoryPersistingMiddleware`

[`_sessions.py:L567-L708`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L567-L708).

A built-in `ChatMiddleware` the framework installs automatically when `require_per_service_call_history_persistence=True` is set on the chat client. It persists provider history **after each individual model call** (including intermediate tool-call rounds), not just once per agent run. Most users never wire this directly.

## Helper: `is_local_history_conversation_id`

[`_sessions.py:L537-L539`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L537-L539). Returns `True` for the framework sentinel string `"agent_framework_local_history_persistence"`. Use to detect that a response came back through the local-history path (so you don't propagate that conversation_id to a real chat service).

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Two providers using the same `source_id` | Attribution collisions; `before_run` ordering gets confusing. Use unique IDs. |
| Mutating a `Message` after `extend_messages(...)` | The provider's copy is stored; your mutation is invisible. Mutate the message *before* passing it in. |
| Subclassing `ContextProvider` to add **agent** middleware in `before_run` | Raises `MiddlewareException` — context providers may only add chat/function middleware ([`_sessions.py:L300`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L300)). |
| Reusing one `AgentSession` across two concurrent `agent.run()` calls | `session.state` is shared, not locked. Use distinct sessions or serialize the runs. |
| Putting non-serializable objects in `session.state` and calling `to_dict()` | Will be dropped. Register a type with `register_state_type()` or pre-convert. |
| Calling `agent.run(..., session=session)` and never persisting `session` | History lives in `session.state`. Reuse the **same session instance** across calls, or persist with `session.to_dict()` and restore. |

## See also

- [`middleware.md`](middleware.md) — chat/function middleware that providers may attach
- [`agents.md`](agents.md) — `context_providers=` agent parameter
- [`../../patterns/session-history-persistence.md`](../../patterns/session-history-persistence.md)
