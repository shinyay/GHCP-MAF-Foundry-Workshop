# Experimental Memory Harness

> Status: ⚠️ **Experimental** — `@experimental(feature_id=ExperimentalFeature.HARNESS)`
> Pinned: `agent-framework-foundry==1.8.0` (core)
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent_framework/_harness/_memory.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py)

> [!WARNING]
> Every class on this page is decorated with `@experimental(feature_id=ExperimentalFeature.HARNESS)`. The API surface, file-system layout, and prompt templates **can and will change** between minor versions. Do not use this for production memory storage. Pin tightly if you depend on it, and re-validate on every Agent Framework upgrade. See [`feature-stages.md`](feature-stages.md) for the full warning model and how to silence/track `[HARNESS] ... ExperimentalWarning`.
>
> For production semantic memory and chat-history persistence, use the stable external providers documented in [`history-providers.md`](history-providers.md) and [`context-providers-rag.md`](context-providers-rag.md).

## What this is

A self-contained, file-system-backed long-term memory system designed for the agent **test harness** and for local/personal agents that want a curated `MEMORY.md` plus a topics folder. It performs **automated** memory extraction from the conversation transcript and **periodic consolidation** via an LLM.

Three top-level classes, all exported from `agent_framework`:

| Class | Role | Source |
|-------|------|--------|
| `MemoryStore` (ABC) | Backing-store interface — 10 abstract methods | [`_harness/_memory.py:L555-L648`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py#L555-L648) |
| `MemoryFileStore` | Concrete file-backed implementation | [`_harness/_memory.py:L651-L920`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py#L651-L920) |
| `MemoryContextProvider(HistoryProvider)` | The provider that auto-extracts and consolidates memory | [`_harness/_memory.py:L926-L1100`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py#L926-L1100) |

> [!IMPORTANT]
> `MemoryContextProvider` inherits from **`HistoryProvider`**, not `ContextProvider`. It persists the transcript as well as injecting curated memory. That means you do **not** also wire a separate `HistoryProvider` for the same session — `MemoryContextProvider` covers both responsibilities.

## On-disk layout

A `MemoryFileStore` rooted at `<base_path>` organizes a single owner like this:

```
<base_path>/
└── <owner_prefix><owner_id>/
    └── <kind>/                    # default: "memory"
        ├── MEMORY.md              # top-level index (auto-rebuilt)
        ├── topics/
        │   ├── <slug-1>.md
        │   ├── <slug-2>.md
        │   └── ...
        ├── transcripts/
        │   └── <session-id>.jsonl
        └── state.json             # maintenance state (consolidation timestamps, etc.)
```

Constants (overridable per `MemoryFileStore` instance):
- `DEFAULT_MEMORY_INDEX_FILE_NAME = "MEMORY.md"`
- `DEFAULT_MEMORY_TOPICS_DIRECTORY_NAME = "topics"`
- `DEFAULT_MEMORY_TRANSCRIPTS_DIRECTORY_NAME = "transcripts"`
- `DEFAULT_MEMORY_SOURCE_ID = "memory"`

## `MemoryStore` ABC

10 abstract methods — implement all of them for a custom backend:

| Method | Purpose |
|--------|---------|
| `list_topics(session, *, source_id)` | List all topic memory files for the current owner |
| `get_topic(session, *, source_id, topic)` | Load one topic by name or slug |
| `write_topic(session, record, *, source_id)` | Persist one topic file |
| `delete_topic(session, *, source_id, topic)` | Delete one topic file |
| `rebuild_index(session, *, source_id, line_limit, line_length)` | Regenerate `MEMORY.md` from topic files |
| `get_index_text(session, *, source_id, line_limit, line_length, index_entries=None)` | Return current `MEMORY.md` text (rebuilding when stale) |
| `read_state(session, *, source_id)` | Read maintenance state JSON |
| `write_state(session, state, *, source_id)` | Persist maintenance state JSON |
| `get_transcripts_directory(session, *, source_id)` | Return the owner-level transcript directory path |
| `search_transcripts(session, *, source_id, query, session_id=None, limit=20)` | Search transcript archive for a text snippet |

Optional overrides (default impls are no-ops):
- `get_owner_id(session)` — logical owner ID for the store (e.g., user id)
- `export_provider_state(session)` / `import_provider_state(session, *, state)` — for cross-process session migration

## `MemoryContextProvider` constructor

```python
@experimental(feature_id=ExperimentalFeature.HARNESS)
class MemoryContextProvider(HistoryProvider):
    def __init__(
        self,
        recent_turns: int = 0,
        load_tool_turns: bool = True,
        *,
        store: MemoryStore,                                # required
        source_id: str = DEFAULT_MEMORY_SOURCE_ID,         # "memory"
        context_prompt: str | None = None,
        index_line_limit: int = DEFAULT_MEMORY_INDEX_LINE_LIMIT,        # 200
        index_line_length: int = DEFAULT_MEMORY_INDEX_LINE_LENGTH,      # 150
        selection_limit: int = DEFAULT_MEMORY_SELECTION_LIMIT,          # 3
        max_extractions: int = DEFAULT_MEMORY_MAX_EXTRACTIONS,          # 5
        consolidation_interval: timedelta = DEFAULT_MEMORY_CONSOLIDATION_INTERVAL,  # 24h
        consolidation_min_sessions: int = DEFAULT_MEMORY_CONSOLIDATION_MIN_SESSIONS,  # 5
        extraction_prompt: str = DEFAULT_MEMORY_EXTRACTION_PROMPT,
        consolidation_prompt: str = DEFAULT_MEMORY_CONSOLIDATION_PROMPT,
        consolidation_client: SupportsChatGetResponse[Any] | None = None,
        history_message_filter: HistoryMessageFilter | None = None,
        history_dumps: JsonDumps | None = None,
        history_loads: JsonLoads | None = None,
    ) -> None: ...
```

Validation (raises `ValueError`):
- `index_line_limit > 0`
- `index_line_length > 0`
- `selection_limit >= 0`
- `recent_turns >= 0`
- `max_extractions >= 0`
- `consolidation_min_sessions > 0`

## Lifecycle

```
before_run:
  1. Read MEMORY.md from MemoryStore.get_index_text(...)
  2. Auto-load up to `selection_limit` relevant topic files
  3. Optionally inject `recent_turns` of transcript context
  4. Inject all of the above as context messages (via extend_messages)

after_run:
  1. Persist transcript via transcripts/<session-id>.jsonl
  2. If the LLM emitted memory extraction signals (up to `max_extractions`),
     write/update corresponding topic files via write_topic(...)
  3. If `consolidation_interval` elapsed AND `consolidation_min_sessions`
     sessions accumulated, call `consolidation_client` (or default agent
     client) to run consolidation prompt over the topic files
```

The extraction and consolidation prompts are defined as module constants:
- `DEFAULT_MEMORY_EXTRACTION_PROMPT` — extracts durable facts from the latest turn
- `DEFAULT_MEMORY_CONSOLIDATION_PROMPT` — merges and deduplicates topic files

Override both via constructor kwargs to customize behavior.

## Custom override knobs (most useful)

| Knob | Why override |
|------|--------------|
| `consolidation_client=` | Use a **cheaper model** for the periodic consolidation pass (default is the agent's own client, which may be a high-cost model) |
| `recent_turns=` | Mix recent verbatim transcript into context alongside the curated `MEMORY.md` |
| `selection_limit=` | Cap how many topic files are auto-loaded per turn (cost / context-budget control) |
| `index_line_limit=` / `index_line_length=` | Cap the size of `MEMORY.md` itself |
| `extraction_prompt=` / `consolidation_prompt=` | Steer what kind of facts are extracted and how they are merged |
| `history_message_filter=` | Rewrite/drop messages before transcript persistence (e.g., redact PII) |

## Sample skeleton (illustrative — not for production)

```python
from agent_framework import (
    AgentSession,
    MemoryContextProvider,
    MemoryFileStore,
)
from agent_framework.foundry import FoundryChatClient

# Build the store. owner_state_key is the AgentSession.state key that
# holds the logical owner id (e.g., "user_id" for a per-user store).
store = MemoryFileStore(
    base_path="/var/lib/myapp/agent-memory",
    owner_state_key="user_id",
)

provider = MemoryContextProvider(
    store=store,
    selection_limit=3,            # max 3 topic files loaded per turn
    recent_turns=2,               # include 2 recent transcript turns
    max_extractions=5,
)

agent = client.as_agent(
    name="curator",
    instructions="You curate facts about the user.",
    context_providers=[provider],
)

session = AgentSession()
session.state["user_id"] = "user-42"
await agent.run("My favorite tea is hojicha.", session=session)
```

> [!CAUTION]
> The above is **illustrative** — verify the import path and constructor signature against your installed version, because this API is marked experimental and may have changed. Run `python -c "from agent_framework import MemoryContextProvider; help(MemoryContextProvider)"` to confirm against your pinned wheel.

## Why we do not provide an end-to-end pattern (yet)

Patterns under `kb/patterns/` are runnable, version-stable recipes meant to be copy-pasted. We deliberately do **not** ship one for the experimental harness because:

1. The on-disk layout and prompts may change across minor versions.
2. The auto-extraction / consolidation feedback loop has cost implications that depend on your `consolidation_client` choice — there is no single sensible default.
3. The stable cross-package providers ([`Mem0ContextProvider`](context-providers-rag.md#mem0contextprovider), [`RedisContextProvider`](context-providers-rag.md#rediscontextprovider), [`AzureAISearchContextProvider`](context-providers-rag.md#azureaisearchcontextprovider)) cover the same intent (semantic long-term memory) without experimental risk.

When `MemoryContextProvider` graduates out of `@experimental(HARNESS)`, this page will be promoted to a stable reference and an end-to-end pattern added.

## Related types

| Type | Role | Source |
|------|------|--------|
| `MemoryIndexEntry` | One row in `MEMORY.md` (topic name + summary + slug) | [`_harness/_memory.py:L241`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py#L241) |
| `MemoryTopicRecord` | One topic file (title, body, slug, timestamps) | [`_harness/_memory.py:L345`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py#L345) |
| `TodoStore` / `TodoFileStore` / `TodoSessionStore` | Companion todo-list harness (also `@experimental(HARNESS)`) | [`_harness/_todo.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_todo.py) |

## See also

- [`sessions.md`](sessions.md) — `HistoryProvider` base class (which `MemoryContextProvider` extends)
- [`history-providers.md`](history-providers.md) — stable external chat-history backends (Redis, Cosmos)
- [`context-providers-rag.md`](context-providers-rag.md) — stable external RAG providers (Mem0, Redis, AI Search)
- [`packages.md`](packages.md#persistence--memory-packages--capability-matrix) — full capability matrix
- [`../../anti-patterns/using-the-wrong-memory-primitive.md`](../../anti-patterns/using-the-wrong-memory-primitive.md) — chat history vs RAG vs checkpoints

Upstream source: [`agent_framework/_harness/_memory.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_memory.py).
