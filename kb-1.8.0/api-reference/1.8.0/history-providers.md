# History Providers — Chat history persistence backends

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0` + backend extras
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent-framework-redis/_history_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_history_provider.py), [`agent-framework-azure-cosmos/_history_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-cosmos/agent_framework_azure_cosmos/_history_provider.py)

This page catalogs the **external** `HistoryProvider` implementations shipped as separate packages. For the **in-core** providers (`InMemoryHistoryProvider`, `FileHistoryProvider`) and the `HistoryProvider` base-class hook contract, see [`sessions.md`](sessions.md).

> [!IMPORTANT]
> A `HistoryProvider` persists **conversation turns** (the literal `Message` objects exchanged with the model). It is **not** a knowledge retrieval mechanism — that's a `ContextProvider` (see [`context-providers-rag.md`](context-providers-rag.md)) — and it is **not** a workflow state snapshot — that's a `CheckpointStorage` (see [`../../patterns/workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md)). The three are easy to confuse; see [`../../anti-patterns/using-the-wrong-memory-primitive.md`](../../anti-patterns/using-the-wrong-memory-primitive.md).

## Decision table

| Backend | Class | Install | Best for | Auth |
|---------|-------|---------|----------|------|
| In-memory (default) | `InMemoryHistoryProvider` | (core) | Tests, demos, single-process apps where history dies with the process | none |
| Local JSONL file | `FileHistoryProvider` ⚠️ `@experimental` | (core) | Local dev, single-machine apps | none |
| Redis (incl. Azure Cache for Redis) | `RedisHistoryProvider` | `agent-framework-redis` | Low-latency multi-tenant chat, ephemeral or short-retention sessions | `redis://...` URL **or** Entra ID via `credential_provider=` |
| Azure Cosmos DB (NoSQL) | `CosmosHistoryProvider` | `agent-framework-azure-cosmos` | Production durable storage, multi-region, schema-flexible audit | account key **or** `DefaultAzureCredential` |
| Chat service-managed (Foundry threads, OpenAI Assistants) | (no local provider) | (core) | Production with service-side history | `AgentSession(service_session_id=...)` |

---

## `RedisHistoryProvider`

[`agent_framework_redis._history_provider.py:L20-L88`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_history_provider.py#L20-L88).

Stores conversation messages in Redis Lists, with each session isolated by a unique Redis key (`{key_prefix}:{session_id}`).

### Constructor signature

```python
class RedisHistoryProvider(HistoryProvider):
    DEFAULT_SOURCE_ID: ClassVar[str] = "redis_memory"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        redis_url: str | None = None,
        credential_provider: CredentialProvider | None = None,
        host: str | None = None,
        port: int = 6380,                       # Azure Redis SSL port
        ssl: bool = True,
        username: str | None = None,
        *,
        key_prefix: str = "chat_messages",
        max_messages: int | None = None,
        # HistoryProvider base flags:
        load_messages: bool = True,
        store_outputs: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
    ) -> None: ...
```

### Auth modes

The constructor enforces **mutual exclusion** ([`_history_provider.py:L84-L88`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_history_provider.py#L84-L88)):

| You provide | What happens | Use when |
|-------------|--------------|----------|
| `redis_url="redis://..."` | Direct URL connection (with optional embedded password) | Local Redis, OSS Redis with password |
| `credential_provider=...` **+** `host="..."` | Azure AD / Entra ID token-based auth | Azure Cache for Redis with Entra ID |
| Both `redis_url` and `credential_provider` | **`ValueError`** | — |
| Only `credential_provider` (no `host`) | **`ValueError`** | — |
| Neither | **`ValueError`** | — |

### Local OSS Redis

```python
from agent_framework_redis import RedisHistoryProvider

provider = RedisHistoryProvider(
    redis_url="redis://localhost:6379",
    key_prefix="myapp:chat",
    max_messages=200,             # auto-trim oldest beyond 200
)
```

### Azure Cache for Redis with Entra ID

```python
from azure.identity.aio import DefaultAzureCredential
from redis.asyncio import auth
from agent_framework_redis import RedisHistoryProvider

# CredentialProvider is the redis-py async credential interface;
# wrap your azure-identity credential with redisvl's adapter.
cred = DefaultAzureCredential()
# (see redisvl + Azure Cache for Redis Entra ID docs for the adapter helper)
provider = RedisHistoryProvider(
    credential_provider=my_entra_credential_provider,
    host="myredis.redis.cache.windows.net",
    port=6380,
    ssl=True,
    key_prefix="prod:chat",
)
```

### `max_messages` auto-trim

When set, only the most-recent N messages per session are retained. Older messages are deleted by Redis `LTRIM` after each `after_run`. Set to `None` (default) for unlimited retention.

### Inherited `HistoryProvider` flags

See [`sessions.md`](sessions.md#historyprovider) for the semantics of `load_messages`, `store_outputs`, `store_inputs`, `store_context_messages`, `store_context_from`. They apply identically to `RedisHistoryProvider`.

---

## `CosmosHistoryProvider`

[`agent_framework_azure_cosmos._history_provider.py:L36-L125`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-cosmos/agent_framework_azure_cosmos/_history_provider.py#L36-L125).

Stores each session's conversation as a single Cosmos DB document, partitioned by session id. Batches writes up to `_BATCH_OPERATION_LIMIT = 100` operations per transactional batch.

### Constructor signature

```python
class CosmosHistoryProvider(HistoryProvider):
    DEFAULT_SOURCE_ID: ClassVar[str] = "azure_cosmos_history"
    _BATCH_OPERATION_LIMIT: ClassVar[int] = 100

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        # HistoryProvider base flags:
        load_messages: bool = True,
        store_outputs: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        # Backend config (any of these can come from env vars below):
        endpoint: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: str | AzureCredentialTypes | None = None,
        cosmos_client: CosmosClient | None = None,
        container_client: ContainerProxy | None = None,
        # .env loading:
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None: ...
```

### Env-var fallback

If the corresponding kwarg is `None`, settings are loaded from `AZURE_COSMOS_*` ([`_history_provider.py:L107-L119`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-cosmos/agent_framework_azure_cosmos/_history_provider.py#L107-L119)):

| Env var | Maps to |
|---------|---------|
| `AZURE_COSMOS_ENDPOINT` | `endpoint` |
| `AZURE_COSMOS_DATABASE_NAME` | `database_name` |
| `AZURE_COSMOS_CONTAINER_NAME` | `container_name` |
| `AZURE_COSMOS_KEY` | `credential` (as string) |

If you pass `cosmos_client=` or `container_client=`, the corresponding required fields are skipped.

### Auth modes

| You provide | What happens |
|-------------|--------------|
| `container_client=ContainerProxy(...)` | Use prebuilt container directly; no client lifecycle managed |
| `cosmos_client=CosmosClient(...)` | Use prebuilt client; provider builds database/container proxies |
| `endpoint=...` + `credential="<account-key>"` | New `CosmosClient` with key auth |
| `endpoint=...` + `credential=DefaultAzureCredential()` | New `CosmosClient` with Entra ID auth (managed identity) |
| Only env vars set | Loaded from `AZURE_COSMOS_*` |

### Production recipe (managed identity)

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework_azure_cosmos import CosmosHistoryProvider

async with DefaultAzureCredential() as cred:
    provider = CosmosHistoryProvider(
        endpoint="https://my-acct.documents.azure.com:443/",
        credential=cred,
        database_name="agents",
        container_name="chat-history",
    )
    # use as context_providers=[provider] on your agent
```

### Container partitioning

The provider expects a container partitioned by **session id**. Per upstream documentation, choose `/session_id` (or `/id` if session id is the document key) when creating the container.

### Why not just use Foundry threads?

Foundry threads are a great choice if your chat client is `FoundryChatClient` — set `AgentSession(service_session_id=thread_id)` and skip the provider entirely (see [`sessions.md`](sessions.md#agentsession)). Use `CosmosHistoryProvider` when you need:
- multi-client persistence (e.g., several chat clients backed by one history store)
- custom retention / TTL policy
- co-locating chat history with other Cosmos data your app already owns

---

## Cross-cutting concerns

### `async with` lifecycle

Both providers own credentials and clients. If you let the provider construct its client (`cosmos_client=None`, `container_client=None`, `credential_provider=None`), the provider sets `_owns_client = True` and you should close it. See [`../../anti-patterns/missing-async-with-cleanup.md`](../../anti-patterns/missing-async-with-cleanup.md) for the failure mode (Unclosed connector warnings, leaked sockets).

### Choosing `source_id`

Both providers default to a unique `source_id` (`redis_memory`, `azure_cosmos_history`). Override only if you wire **two** providers of the same type into one agent — `source_id` must be unique per agent's provider list ([`sessions.md`](sessions.md#sessioncontext--per-invocation-scratch-space)).

### Mixing chat-service history with a provider

Do **not** set both `AgentSession.service_session_id` and attach a `HistoryProvider`. The service stores history server-side; the provider would store a duplicate, drift on edits, and waste bandwidth. The framework's auto-attach logic respects this: if `service_session_id` is set, `InMemoryHistoryProvider` is **not** auto-wired ([`_sessions.py:L789-L791`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L789-L791)).

---

## See also

- [`sessions.md`](sessions.md) — `HistoryProvider` base class, hook contract, in-core providers
- [`context-providers-rag.md`](context-providers-rag.md) — RAG context providers (different mechanism)
- [`packages.md`](packages.md#persistence--memory-packages--capability-matrix) — package capability matrix
- [`../../patterns/persistent-history-cosmos.md`](../../patterns/persistent-history-cosmos.md) — end-to-end Cosmos recipe
- [`../../patterns/session-history-persistence.md`](../../patterns/session-history-persistence.md) — patterns including a custom-backend template
- [`../../anti-patterns/using-the-wrong-memory-primitive.md`](../../anti-patterns/using-the-wrong-memory-primitive.md) — chat history vs RAG vs checkpoints

Upstream source: [`agent-framework-redis/_history_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_history_provider.py), [`agent-framework-azure-cosmos/_history_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-cosmos/agent_framework_azure_cosmos/_history_provider.py).
