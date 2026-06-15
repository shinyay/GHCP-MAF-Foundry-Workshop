# Anti-Pattern: Using the Wrong Memory Primitive

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0)

Agent Framework has **three** distinct persistence primitives that are easy to confuse — and picking the wrong one silently degrades behavior or burns money. This page enumerates the most common mix-ups with concrete WRONG / RIGHT pairs.

## Quick map: which primitive do I need?

| Need | Primitive | Lives in | Hook |
|------|-----------|---------|------|
| Persist chat **transcript** per session, resume across restarts | **`HistoryProvider`** | `_sessions.py:L410-L531` | `load_messages` / `store_messages` |
| Inject **knowledge / memories** into the model's context | **`ContextProvider`** | `_sessions.py:L348-L407` | `before_run` (`Context.messages`) |
| Snapshot **workflow** state for resume / replay | **`CheckpointStorage`** | `_workflows/_checkpoint.py:L119-L189` (Protocol) | `Workflow.checkpoint_storage=` |
| Cache LLM **responses** | (Not a memory primitive) | Use `chat_middleware` | See [`../patterns/agent-middleware-retry.md`](../patterns/agent-middleware-retry.md) |

If you keep these three columns straight, the patterns below fall out naturally.

---

## ❌ Anti-pattern 1 — Using `CheckpointStorage` for chat transcripts

```python
# WRONG — workflow checkpoint as conversation history
from agent_framework import FileCheckpointStorage

storage = FileCheckpointStorage(path="./chat-state")
agent = client.as_agent(name="assistant", instructions="...")
# (no obvious way to wire CheckpointStorage to an Agent — that's the giveaway)
```

### Symptom

You can't actually wire `CheckpointStorage` into a plain `Agent.run()` — there's no parameter for it. People then write glue code like "before each `run()`, load checkpoint, replay messages, write checkpoint after." This:

- Re-serializes the entire transcript on every turn (O(N²) cost).
- Stores opaque pickled blobs (`_serialization.py`), so you can't query by user, content, or time.
- Bypasses framework hooks (no `load_messages` / `store_messages`), so middleware, summarization, and trimming never fire.

### Why it's wrong

`CheckpointStorage` is a **workflow-level** snapshotting protocol ([`_workflows/_checkpoint.py:L119-L189`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L119-L189)) for `WorkflowBuilder().with_checkpointing(storage)` — it captures executor graph state, not chat history.

### ✅ Correct pattern

```python
# Use a HistoryProvider — Cosmos-backed example
from agent_framework_azure_cosmos import CosmosHistoryProvider
from azure.identity.aio import DefaultAzureCredential

async with DefaultAzureCredential() as cred:
    history = CosmosHistoryProvider(
        endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
        database_name="agents",
        container_name="chat-history",
        credential=cred,
    )
    agent = client.as_agent(
        name="assistant",
        instructions="...",
        context_providers=[history],
    )
```

### How to detect

- Search for `CheckpointStorage` references attached to anything other than a `WorkflowBuilder` / `Workflow`.
- If a code path serializes `AgentSession` itself to disk between turns, that's the smell.

---

## ❌ Anti-pattern 2 — Using `HistoryProvider` for RAG knowledge

```python
# WRONG — stuffing a doc corpus into RedisHistoryProvider
from agent_framework_redis import RedisHistoryProvider

provider = RedisHistoryProvider(redis_url=os.environ["REDIS_URL"])
# Pre-populate with documents (wrong place):
await provider.store_messages(
    AgentSession(session_id="doc-store"),
    [ChatMessage(role="system", text=doc_text)],
)
```

### Symptom

- Documents and chat turns interleave in the same Redis keyspace.
- Every new conversation that uses `session_id="doc-store"` either inherits or overwrites the corpus.
- Retrieval is unbounded — the model sees the full corpus, hits context limits, and either errors or hallucinates from truncated text.
- No similarity / relevance ranking — `HistoryProvider.load_messages()` returns whatever was stored, in order.

### Why it's wrong

`HistoryProvider` is built to faithfully **replay** a conversation's messages. It has no concept of retrieval, scoring, or top-k. RAG providers like `AzureAISearchContextProvider`, `RedisContextProvider`, and `Mem0ContextProvider` implement the `ContextProvider` hook contract ([`_sessions.py:L348-L407`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L348-L407)), exposing a `before_run` hook that returns only the relevant context per turn.

### ✅ Correct pattern

```python
from agent_framework_azure_ai_search import AzureAISearchContextProvider

rag = AzureAISearchContextProvider(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name="docs",
    credential=cred,
    mode="semantic",
)
agent = client.as_agent(
    name="docs-assistant",
    instructions="Answer using retrieved context.",
    context_providers=[rag],
)
```

See [`../patterns/rag-with-azure-ai-search.md`](../patterns/rag-with-azure-ai-search.md) for the full recipe.

### How to detect

- Calling `store_messages()` from outside the framework, with content that isn't a conversation turn (e.g., document chunks, FAQ entries).
- A "session" whose `session_id` is shared across many users (e.g., `"doc-store"`, `"kb"`).
- `load_messages()` returns hundreds of messages and the model truncates.

---

## ❌ Anti-pattern 3 — Expecting workflow checkpoints in chat history

```python
# WRONG — assuming the workflow's checkpoint is visible to the agent
workflow = (
    WorkflowBuilder(start_executor=research, output_executors=[writer])
    .with_checkpointing(FileCheckpointStorage(path="./state"))
    .build()
)

# Later, in an agent's session:
session = AgentSession(session_id="user-1")
result = await agent.run("What did the workflow find?", session=session)
# ❌ Agent has no visibility into workflow state
```

> [!NOTE]
> Modern (1.8.0) correct equivalent: use `output_from=[writer]` instead of deprecated
> `output_executors=[writer]`. See [`workflows.md`](../api-reference/1.8.0/workflows.md#workflowbuilder).

### Symptom

The agent answers "I don't have access to that information" or fabricates. The workflow ran fine, checkpoints exist on disk, but the agent can't see them.

### Why it's wrong

`CheckpointStorage` and `HistoryProvider` are **separate stores** with separate schemas, separate keys, and no automatic bridge.

- `CheckpointStorage` keys by `workflow_name` + checkpoint id, stores opaque pickled executor state ([`_workflows/_checkpoint.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py)).
- `HistoryProvider` keys by `session_id`, stores `ChatMessage[]`.

Even when an executor is itself an `AgentExecutor`, the messages it generates during workflow execution are scoped to the workflow run, not to any external agent's session.

### ✅ Correct pattern

If you want a downstream agent to *consume* workflow output, pass it explicitly:

```python
async for event in workflow.run(initial_input, stream=True):
    if event.type == "output":
        result_text = event.data

# Hand off explicitly
session = AgentSession(session_id="user-1")
await agent.run(f"Here is the research output:\n{result_text}", session=session)
```

Or, if the *workflow itself* should hold the agent's chat history, run the agent **inside** the workflow (e.g., via `AgentExecutor`) and treat the workflow boundary as the session boundary.

### How to detect

- A workflow uses `with_checkpointing(...)` and a sibling agent shares a "user id" but no explicit data is passed between them.
- Logs show successful workflow checkpoint writes but agent responses can't reference the workflow's findings.

---

## ❌ Anti-pattern 4 — Stacking `HistoryProvider` + `MemoryContextProvider` for the same session

```python
# WRONG — both providers persist the transcript
from agent_framework_redis import RedisHistoryProvider
from agent_framework import MemoryContextProvider, MemoryFileStore

history = RedisHistoryProvider(redis_url=os.environ["REDIS_URL"])
memory = MemoryContextProvider(
    memory_store=MemoryFileStore(directory="./memory"),
    agent_id="assistant",
    user_id="user-42",
)

agent = client.as_agent(
    name="assistant",
    instructions="...",
    context_providers=[history, memory],  # ❌ double-persist
)
```

### Symptom

- Every turn is written **twice** (once to Redis, once to the memory store).
- On `load_messages()`, both providers contribute messages — the model sees the same transcript duplicated.
- Token bill doubles for the same conversation.

### Why it's wrong

`MemoryContextProvider` is itself an `HistoryProvider` subclass ([`_harness/_memory.py:L926-L1100`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py#L926-L1100)) — it persists the transcript **and** curates extracted memories from it. Stacking it on top of another `HistoryProvider` is redundant.

Additionally, `MemoryContextProvider` is `@experimental` and ships as an in-process index — it is not a production storage backend.

### ✅ Correct pattern

**Production path** — use one production `HistoryProvider` (Redis / Cosmos) for the transcript, and one `ContextProvider` for semantic memory:

```python
history = CosmosHistoryProvider(
    endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
    database_name="agents",
    container_name="chat-history",
    credential=cred,
)
rag = RedisContextProvider(redis_url=os.environ["REDIS_URL"])

agent = client.as_agent(
    name="assistant",
    instructions="...",
    context_providers=[history, rag],   # one persists, one injects knowledge
)
```

**Experimental path** — use `MemoryContextProvider` alone:

```python
memory = MemoryContextProvider(
    memory_store=MemoryFileStore(directory="./memory"),
    agent_id="assistant",
    user_id="user-42",
)
agent = client.as_agent(
    name="assistant",
    instructions="...",
    context_providers=[memory],         # transcript + memories in one provider
)
```

> [!CAUTION]
> `MemoryContextProvider` and `MemoryFileStore` are experimental ([`memory-experimental.md`](../api-reference/1.8.0/memory-experimental.md)). Do not deploy them to production.

### How to detect

- Two providers in `context_providers=[...]` where both inherit from `HistoryProvider`.
- Duplicate user / assistant messages in `result.messages` from a single `run()`.
- Token-count metrics roughly 2× expected for short conversations.

---

## ❌ Anti-pattern 5 — Hard-coding account keys for Cosmos / Redis / AI Search

```python
# WRONG — secret in source
provider = CosmosHistoryProvider(
    endpoint="https://my-acct.documents.azure.com:443/",
    database_name="agents",
    container_name="chat-history",
    credential="abc123==",                # ❌ account key in code
)
```

### Symptom

Secret leaks via git history, CI logs, or process listings. Rotation requires a code change and redeploy.

### Why it's wrong

All three persistence backends accept Entra ID credentials. Account keys grant **full data-plane access** and can't be scoped per-application.

### ✅ Correct pattern

```python
from azure.identity.aio import DefaultAzureCredential

async with DefaultAzureCredential() as cred:
    provider = CosmosHistoryProvider(
        endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
        database_name="agents",
        container_name="chat-history",
        credential=cred,                  # ✅ managed identity / az login
    )
```

Assign `Cosmos DB Built-in Data Contributor` (Cosmos), `Search Index Data Reader/Contributor` (AI Search), or Redis ACL roles to the runtime identity.

### How to detect

- Any `credential=` argument receiving a string literal or a `os.environ["*_KEY"]` value.
- Repos that gitignore `.env` but include actual keys in CI variables instead of identities.

See [`sync-credential-in-async.md`](sync-credential-in-async.md) for the related async-credential pitfall.

---

## See also

- [`../api-reference/1.8.0/history-providers.md`](../api-reference/1.8.0/history-providers.md)
- [`../api-reference/1.8.0/context-providers-rag.md`](../api-reference/1.8.0/context-providers-rag.md)
- [`../api-reference/1.8.0/memory-experimental.md`](../api-reference/1.8.0/memory-experimental.md)
- [`../api-reference/1.8.0/sessions.md`](../api-reference/1.8.0/sessions.md)
- [`../patterns/persistent-history-cosmos.md`](../patterns/persistent-history-cosmos.md)
- [`../patterns/rag-with-azure-ai-search.md`](../patterns/rag-with-azure-ai-search.md)
- [`../patterns/workflow-checkpointing.md`](../patterns/workflow-checkpointing.md)

Upstream source: [`_sessions.py:L348-L531`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L348-L531), [`_workflows/_checkpoint.py:L119-L189`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L119-L189), [`_harness/_memory.py:L926-L1100`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py#L926-L1100).
