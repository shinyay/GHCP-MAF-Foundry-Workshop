# RAG Context Providers — Knowledge retrieval into agent context

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0` + backend extras
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent-framework-mem0/_context_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/mem0/agent_framework_mem0/_context_provider.py), [`agent-framework-redis/_context_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_context_provider.py), [`agent-framework-azure-ai-search/_context_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-ai-search/agent_framework_azure_ai_search/_context_provider.py)

This page catalogs `ContextProvider` implementations that perform **retrieval-augmented generation (RAG)** or **semantic memory injection** — they retrieve knowledge from an external store and add it to the model's context before each run.

> [!IMPORTANT]
> A `ContextProvider` is **not** chat history. It does not store the literal conversation turns; it injects retrieved snippets via `SessionContext.extend_messages(...)`. For chat history persistence, use a `HistoryProvider` (see [`history-providers.md`](history-providers.md)). For the base-class hook contract and `SessionContext` semantics, see [`sessions.md`](sessions.md#contextprovider).

## Decision table

| Backend | Class | Install | Best for | Retrieval mechanism |
|---------|-------|---------|----------|--------------------|
| Mem0 (Platform SaaS or OSS) | `Mem0ContextProvider` | `agent-framework-mem0` | Long-term semantic memory keyed by user/agent/application | Mem0 `search()` over stored memories |
| Redis (full-text + optional vector) | `RedisContextProvider` | `agent-framework-redis` | Low-latency hybrid retrieval, small-medium corpus | redisvl `AggregateHybridQuery` or `TextQuery` |
| Azure AI Search — semantic | `AzureAISearchContextProvider(mode="semantic")` | `agent-framework-azure-ai-search` | Large enterprise index with semantic ranker | AI Search `search()` with semantic config |
| Azure AI Search — agentic | `AzureAISearchContextProvider(mode="agentic")` | `agent-framework-azure-ai-search` | Multi-step retrieval planning with Azure OpenAI | AI Search Knowledge Base + reasoning |

---

## Scoping memories with user / agent / application IDs

Mem0 and Redis providers support **scoping filters**. These are the keys under which memories/context are partitioned. You almost always want to set at least one:

| Filter | Meaning | Typical use |
|--------|---------|-------------|
| `user_id` | End-user identity | Per-user personal memory |
| `agent_id` | Agent persona identity | Per-agent shared memory across users |
| `application_id` | Tenant / app boundary | Multi-tenant isolation |

`Mem0ContextProvider` raises `ValueError("At least one of the filters: agent_id, user_id, or application_id is required.")` if none are set ([`mem0/_context_provider.py:L171-L174`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/mem0/agent_framework_mem0/_context_provider.py#L171-L174)).

---

## `Mem0ContextProvider`

[`agent_framework_mem0._context_provider.py:L36-L188`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/mem0/agent_framework_mem0/_context_provider.py#L36-L188).

Integrates [Mem0](https://mem0.ai) for persistent semantic long-term memory. On every `before_run`, searches Mem0 for memories relevant to the incoming user text and injects them as a system-style context message. On every `after_run`, stores the new user+assistant turn back into Mem0 for future retrieval.

### Constructor signature

```python
class Mem0ContextProvider(ContextProvider):
    DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"
    DEFAULT_SOURCE_ID: ClassVar[str] = "mem0"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        mem0_client: AsyncMemory | AsyncMemoryClient | None = None,
        api_key: str | None = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        *,
        context_prompt: str | None = None,
    ) -> None: ...
```

### OSS vs Platform client

The provider accepts **two** Mem0 client types and handles them differently ([`mem0/_context_provider.py:L113-L117`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/mem0/agent_framework_mem0/_context_provider.py#L113-L117)):

| Client | Kind | Filter passing |
|--------|------|----------------|
| `mem0.AsyncMemory` | OSS / self-hosted | Direct kwargs: `search(query=..., user_id=..., agent_id=...)` |
| `mem0.AsyncMemoryClient` | Platform (cloud) | Wrapped in `filters` dict: `search(query=..., filters={"user_id": ..., "agent_id": ..., "app_id": ...})` |

If you pass neither, a default `AsyncMemoryClient(api_key=api_key)` is constructed and **owned** by the provider — it will be `__aexit__`-closed when the provider exits its own context manager ([`mem0/_context_provider.py:L82-L91`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/mem0/agent_framework_mem0/_context_provider.py#L82-L91)).

### Quick example (Platform)

```python
import os
from agent_framework_mem0 import Mem0ContextProvider

provider = Mem0ContextProvider(
    api_key=os.environ["MEM0_API_KEY"],
    user_id="user-42",                # at least one of these is required
    application_id="my-app",
)

# Wire into your agent:
agent = client.as_agent(
    name="assistant",
    instructions="You are a helpful assistant.",
    context_providers=[provider],
)
```

### `context_prompt` customization

Defaults to:

```text
## Memories
Consider the following memories when answering user questions:
```

Override via `context_prompt=` if you want different framing (e.g., "Recall the user's preferences:").

### Failure mode: no filter set

```python
Mem0ContextProvider()                        # explodes at first run with:
# ValueError: At least one of the filters: agent_id, user_id, or application_id is required.
```

This is a **runtime** error, raised by `_validate_filters()` inside `before_run` / `after_run`. Set at least one in the constructor to fail at import time instead.

---

## `RedisContextProvider`

[`agent_framework_redis._context_provider.py:L44-L107`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_context_provider.py#L44-L107).

Stores context entries in a Redis index (via the [`redisvl`](https://www.redisvl.com/) client) and retrieves them via full-text or hybrid vector search.

### Constructor signature

```python
class RedisContextProvider(ContextProvider):
    DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"
    DEFAULT_SOURCE_ID: ClassVar[str] = "redis"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        redis_url: str = "redis://localhost:6379",
        index_name: str = "context",
        prefix: str = "context",
        *,
        redis_vectorizer: BaseVectorizer | None = None,
        vector_field_name: str | None = None,
        vector_algorithm: Literal["flat", "hnsw"] | None = None,
        vector_distance_metric: Literal["cosine", "ip", "l2"] | None = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        context_prompt: str | None = None,
        redis_index: Any = None,
        overwrite_index: bool = False,
    ): ...
```

### Retrieval mode selection

| Mode | When | How to enable |
|------|------|---------------|
| Full-text only | No `redis_vectorizer` set | Default; uses `TextQuery` over indexed text |
| Hybrid (text + vector) | `redis_vectorizer=` set (e.g., `OpenAITextVectorizer`) | Uses `AggregateHybridQuery`; requires `vector_field_name=`, `vector_algorithm=`, `vector_distance_metric=` |

> [!NOTE]
> `redis_vectorizer` **must** be a `redisvl.utils.vectorize.BaseVectorizer` subclass — anything else raises `AgentException` ([`_context_provider.py:L96-L99`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_context_provider.py#L96-L99)).

### Quick example (full-text)

```python
from agent_framework_redis import RedisContextProvider

provider = RedisContextProvider(
    redis_url="redis://localhost:6379",
    index_name="company-policies",
    prefix="policies",
    user_id="user-42",
    overwrite_index=False,             # set True only once when bootstrapping
)
```

### Hybrid with OpenAI embeddings

```python
from redisvl.utils.vectorize import OpenAITextVectorizer
from agent_framework_redis import RedisContextProvider

vectorizer = OpenAITextVectorizer(model="text-embedding-3-small")

provider = RedisContextProvider(
    redis_url="redis://localhost:6379",
    index_name="docs-hybrid",
    redis_vectorizer=vectorizer,
    vector_field_name="embedding",
    vector_algorithm="hnsw",
    vector_distance_metric="cosine",
    user_id="user-42",
)
```

### Index ownership

Set `overwrite_index=True` only when you want to drop and recreate the index. Leave it `False` for normal operation; the provider connects to an existing index.

---

## `AzureAISearchContextProvider`

[`agent_framework_azure_ai_search._context_provider.py:L157-L285`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-ai-search/agent_framework_azure_ai_search/_context_provider.py#L157-L285).

Retrieves relevant context from an Azure AI Search index in one of three modes, distinguished by `@overload` on the constructor.

### Mode 1 — Semantic (most common)

Direct semantic search against an existing index using a `semantic_configuration_name`. Best for RAG over enterprise content.

```python
class AzureAISearchContextProvider(ContextProvider):
    DEFAULT_SOURCE_ID: ClassVar[str] = "azure_ai_search"

    @overload
    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        endpoint: str | None = None,
        index_name: str | None = None,
        api_key: str | AzureKeyCredential | None = None,
        credential: AzureCredentialTypes | None = None,
        *,
        mode: Literal["semantic"] = "semantic",
        top_k: int = 5,
        semantic_configuration_name: str | None = None,
        vector_field_name: str | None = None,
        embedding_function: EmbeddingFunction | None = None,
        context_prompt: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None: ...
```

Example:

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework_azure_ai_search import AzureAISearchContextProvider

async with DefaultAzureCredential() as cred:
    provider = AzureAISearchContextProvider(
        endpoint="https://my-search.search.windows.net",
        index_name="company-docs",
        credential=cred,
        mode="semantic",
        top_k=5,
        semantic_configuration_name="default",
    )
```

### Mode 2 — Agentic (Knowledge Base from index)

The provider **creates** an Azure AI Search Knowledge Base from your index and routes queries through it. Requires an Azure OpenAI resource for the reasoning model.

```python
@overload
def __init__(
    self,
    source_id: str = DEFAULT_SOURCE_ID,
    endpoint: str | None = None,
    index_name: str | None = None,       # required in this overload
    api_key: str | AzureKeyCredential | None = None,
    credential: AzureCredentialTypes | None = None,
    *,
    mode: Literal["agentic"],
    top_k: int = 5,
    semantic_configuration_name: str | None = None,
    vector_field_name: str | None = None,
    embedding_function: EmbeddingFunction | None = None,
    context_prompt: str | None = None,
    azure_openai_resource_url: str,      # required
    model: str,                          # required
    retrieval_instructions: str | None = None,
    azure_openai_api_key: str | None = None,
    knowledge_base_output_mode: KnowledgeBaseOutputModeLiteral = "extractive_data",
    retrieval_reasoning_effort: RetrievalReasoningEffortLiteral = "minimal",
    agentic_message_history_count: int = 10,
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
) -> None: ...
```

### Mode 3 — Agentic (use existing Knowledge Base)

If you already have an AI Search Knowledge Base, reference it by name instead of an index:

```python
@overload
def __init__(
    self,
    source_id: str = DEFAULT_SOURCE_ID,
    endpoint: str | None = None,
    index_name: None = None,             # MUST be None
    api_key: str | AzureKeyCredential | None = None,
    credential: AzureCredentialTypes | None = None,
    *,
    mode: Literal["agentic"],
    # ... (same shared options)
    knowledge_base_name: str,            # required
    # ... etc
) -> None: ...
```

### Mode comparison

| | Semantic | Agentic (from index) | Agentic (existing KB) |
|---|----------|---------------------|----------------------|
| `mode=` | `"semantic"` | `"agentic"` + `index_name=` | `"agentic"` + `knowledge_base_name=` |
| Requires Azure OpenAI? | No | Yes (`azure_openai_resource_url`, `model`) | Yes |
| Multi-step reasoning? | No (single search) | Yes | Yes |
| `top_k` enforced? | Yes | Yes (as max) | Yes (as max) |
| Latency | Lowest | Higher (LLM reasoning) | Higher |
| Best for | Standard RAG | Complex multi-aspect queries | Reusing an existing KB |

### Env-var fallback

Settings load from `AZURE_SEARCH_*` if not provided directly:

| Env var | Maps to |
|---------|---------|
| `AZURE_SEARCH_ENDPOINT` | `endpoint` |
| `AZURE_SEARCH_INDEX_NAME` | `index_name` |
| `AZURE_SEARCH_API_KEY` | `api_key` |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | `knowledge_base_name` (agentic mode 3) |

### Knowledge Base output modes

| Value | Behavior |
|-------|----------|
| `"extractive_data"` (default) | Returns raw extracted chunks |
| `"answer_synthesis"` | Returns synthesized answer text from the KB |

### Retrieval reasoning effort

`"minimal"` (default) | `"low"` | `"medium"` — controls the planning depth of the agentic retrieval LLM.

---

## Cross-cutting concerns

### `async with` lifecycle

All three providers manage owned credentials/clients. Use `async with provider:` or compose into your `async with credential, client:` block.

### `source_id` collisions

If you wire **two** of these into the same agent (e.g., one Mem0 for user memory and one Azure AI Search for docs), each needs a unique `source_id` ([`sessions.md`](sessions.md#sessioncontext--per-invocation-scratch-space)). The defaults are already unique across types (`mem0`, `redis`, `azure_ai_search`), so only override if you have multiple of the same.

### Mixing RAG + chat history

It is normal and correct to compose a `HistoryProvider` (for chat persistence) **and** a `ContextProvider` (for RAG) on the same agent. They serve orthogonal purposes:

```python
agent = client.as_agent(
    name="assistant",
    instructions="...",
    context_providers=[
        CosmosHistoryProvider(...),               # persists turns
        AzureAISearchContextProvider(...),        # injects RAG context
    ],
)
```

See [`../../anti-patterns/using-the-wrong-memory-primitive.md`](../../anti-patterns/using-the-wrong-memory-primitive.md) for the typical confusion patterns.

---

## See also

- [`sessions.md`](sessions.md#contextprovider) — `ContextProvider` base class and `SessionContext` API
- [`history-providers.md`](history-providers.md) — chat history persistence (different mechanism)
- [`memory-experimental.md`](memory-experimental.md) — experimental `MemoryContextProvider` harness from core
- [`packages.md`](packages.md#persistence--memory-packages--capability-matrix) — package capability matrix
- [`../../patterns/rag-with-azure-ai-search.md`](../../patterns/rag-with-azure-ai-search.md) — end-to-end Azure AI Search RAG recipe
- [`../../anti-patterns/using-the-wrong-memory-primitive.md`](../../anti-patterns/using-the-wrong-memory-primitive.md) — RAG vs history vs checkpoints

Upstream source: [`agent-framework-mem0/_context_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/mem0/agent_framework_mem0/_context_provider.py), [`agent-framework-redis/_context_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/redis/agent_framework_redis/_context_provider.py), [`agent-framework-azure-ai-search/_context_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-ai-search/agent_framework_azure_ai_search/_context_provider.py).
