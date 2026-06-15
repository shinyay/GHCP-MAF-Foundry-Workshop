# Pattern: Conversation History Persistence with Sessions

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_sessions.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py)

## Goal

Maintain conversation continuity across multiple `agent.run()` calls — load past messages before each turn, store the latest exchange after each turn.

## When to use which approach

| Storage location | Provider | Use when |
|------------------|----------|----------|
| In-process dict (`session.state["messages"]`) | `InMemoryHistoryProvider` (default, auto-wired) | Tests, demos, single-process apps where history dies with the process. |
| Local JSONL file per session | `FileHistoryProvider` ⚠️ `@experimental` | Local dev; small-scale single-machine apps. **Not** for prod (plaintext, not encrypted). |
| Chat service (Foundry threads, OpenAI Assistants) | Set `session.service_session_id`; no local provider needed | Production with service-managed history. |
| Database / Redis / KV store | Your own `HistoryProvider` subclass | Production with custom storage. |

## Pattern 1 — Default in-memory history (zero config)

```python
import os
from agent_framework import AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async with AzureCliCredential() as cred:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=cred,
    )
    async with client.as_agent(name="assistant", instructions="You are helpful.") as agent:
        session = AgentSession()                       # auto UUID
        await agent.run("My name is Yanai.", session=session)
        r = await agent.run("What is my name?", session=session)
        # r.messages[-1].text → "Your name is Yanai."
```

When no `context_providers=` is passed and `session.service_session_id is None`, the framework auto-attaches `InMemoryHistoryProvider` ([`_sessions.py:L789-L791`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L789-L791)).

## Pattern 2 — Custom storage backend

> [!IMPORTANT]
> For Redis / Cosmos persistence in production, **do not roll your own** — use the ready-made [`RedisHistoryProvider`](../api-reference/1.8.0/history-providers.md#redishistoryprovider) (in `agent-framework-redis`) or [`CosmosHistoryProvider`](../api-reference/1.8.0/history-providers.md#cosmoshistoryprovider) (in `agent-framework-azure-cosmos`). The example below shows the shape of a **custom backend** for stores not covered by official packages (e.g., an internal Postgres / DynamoDB / Cassandra layer).

Subclass `HistoryProvider` and implement `get_messages` + `save_messages`. The base class handles `before_run`/`after_run` dispatching for you.

```python
from typing import Any, Sequence
from agent_framework import HistoryProvider, Message

class MyDbHistoryProvider(HistoryProvider):
    """Skeleton showing the HistoryProvider contract.

    Replace the in-memory dict below with calls to your real backend
    (Postgres, DynamoDB, Cassandra, etc.).
    """

    def __init__(self, *, source_id: str = "mydb_history") -> None:
        super().__init__(source_id=source_id)
        self._store: dict[str, list[str]] = {}

    async def get_messages(self, session_id: str | None, *, state=None, **kwargs) -> list[Message]:
        if not session_id:
            return []
        raw = self._store.get(session_id, [])
        return [Message.model_validate_json(b) for b in raw]

    async def save_messages(self, session_id: str | None, messages: Sequence[Message], *, state=None, **kwargs) -> None:
        if not session_id:
            return
        self._store.setdefault(session_id, []).extend(m.model_dump_json() for m in messages)
```

Wire it:

```python
agent = client.as_agent(
    name="assistant",
    instructions="...",
    context_providers=[MyDbHistoryProvider()],
)
```

For the official Redis / Cosmos backends:

```python
# Redis (no custom subclass needed)
from agent_framework_redis import RedisHistoryProvider
provider = RedisHistoryProvider(redis_url=os.environ["REDIS_URL"])

# Cosmos DB (no custom subclass needed)
from agent_framework_azure_cosmos import CosmosHistoryProvider
provider = CosmosHistoryProvider(
    endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
    database_name="agents",
    container_name="chat-history",
    credential=DefaultAzureCredential(),
)
```

See [`persistent-history-cosmos.md`](persistent-history-cosmos.md) for the end-to-end Cosmos recipe.

## Pattern 3 — Multiple providers (history + audit + per-call timestamps)

```python
agent = client.as_agent(
    name="assistant",
    instructions="...",
    context_providers=[
        TimestampProvider(),                                    # adds context
        InMemoryHistoryProvider(source_id="primary"),           # loads + stores
        InMemoryHistoryProvider(                                # stores only (audit)
            source_id="audit",
            load_messages=False,
            store_context_messages=True,
        ),
    ],
)
```

Providers run in **list order** for `before_run`; the framework iterates in **reverse** for `after_run` so producers see their own output last ([`_sessions.py:L627`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L627)).

> [!IMPORTANT]
> Each provider's `source_id` must be unique. The same `source_id` collides on attribution in `SessionContext.context_messages` and on per-provider state in `session.state`.

## Pattern 4 — Round-trip a session to disk

```python
import json
from pathlib import Path
from agent_framework import AgentSession

# Save
Path("session.json").write_text(json.dumps(session.to_dict()))

# Load
session = AgentSession.from_dict(json.loads(Path("session.json").read_text()))
```

Custom types in `session.state` must implement `SerializationProtocol` (`to_dict`/`from_dict`) and be registered with `register_state_type()` ([`_sessions.py:L66`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L66)) so deserialization can find them.

## Pattern 5 — Service-managed history (Foundry threads)

When the underlying chat service stores history server-side, set `service_session_id` and don't attach a `HistoryProvider`:

```python
session = AgentSession(service_session_id="thread_abc123")
await agent.run("hello", session=session)
```

In this case `InMemoryHistoryProvider` is **not** auto-attached, and the framework routes the conversation id to the chat client.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Creating a fresh `AgentSession()` per turn | History is empty every time. Persist and reuse the `AgentSession` instance. |
| Forgetting to pass `session=...` to `agent.run(...)` | The framework creates a one-shot session that's discarded — no history. |
| Putting non-serializable objects in `session.state` and calling `to_dict()` | Dropped silently or raises. Use `register_state_type()` for custom types. |
| Subclassing `ContextProvider` and trying to add `AgentMiddleware` | `MiddlewareException`. Only chat/function middleware allowed via `extend_middleware`. |
| Reusing the same `source_id` across two providers | Attribution collisions, state is shared. Pick unique IDs. |
| Using `FileHistoryProvider` in production | `@experimental`, plaintext, no encryption. Build a real backend. |

## Verification

```python
from agent_framework import AgentSession, InMemoryHistoryProvider

session = AgentSession()
provider = InMemoryHistoryProvider()

# Round-trip a session through to_dict/from_dict
session.state["messages"] = [Message(role="user", contents=["hello"])]
data = session.to_dict()
restored = AgentSession.from_dict(data)
assert restored.session_id == session.session_id
assert len(restored.state["messages"]) == 1
```

## See also

- [`../api-reference/1.8.0/sessions.md`](../api-reference/1.8.0/sessions.md)
- [`../api-reference/1.8.0/history-providers.md`](../api-reference/1.8.0/history-providers.md) — production Redis / Cosmos backends
- [`../api-reference/1.8.0/middleware.md`](../api-reference/1.8.0/middleware.md) — `PerServiceCallHistoryPersistingMiddleware`
- [`persistent-history-cosmos.md`](persistent-history-cosmos.md) — end-to-end Cosmos recipe with managed identity
- [`agent-middleware-retry.md`](agent-middleware-retry.md)
- [`../anti-patterns/using-the-wrong-memory-primitive.md`](../anti-patterns/using-the-wrong-memory-primitive.md)
