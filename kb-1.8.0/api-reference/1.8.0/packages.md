# Packages — what to install (and what NOT to install)

> Status: **Stable** (this guidance applies to all 1.x including 1.8.0)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: PyPI metadata + `pip show` against the installed wheel

## TL;DR — install exactly this

```bash
pip install "agent-framework-foundry==1.8.0"
```

That is the **only** install line needed for a Foundry-backed agent in this template. It transitively pulls:

| Dependency | Pinned by | Why |
|------------|-----------|-----|
| `agent-framework-core==1.8.0` | `-foundry` | Core `Agent` / `WorkflowBuilder` / `MCPStdioTool` / exceptions |
| `agent-framework-openai==1.8.0` | `-foundry` | Underlying Responses-API client |
| `azure-ai-projects` | `-foundry` | Foundry project SDK (`BingGroundingTool`, `BingGroundingSearchConfiguration`, etc.) |
| `azure-identity` | `-foundry` | `AzureCliCredential`, `DefaultAzureCredential` |

You do **not** install `agent-framework-core` separately, and you must **never** install the meta `agent-framework` package — see "the meta-package trap" below.

---

## The meta-package trap (`agent-framework`)

> ⚠️ **Critical**: Do NOT run `pip install agent-framework`. It silently overwrites `agent_framework/__init__.py` from `agent-framework-core` and breaks imports.

The PyPI package literally named `agent-framework` (no suffix) is a **metapackage** that re-exports a curated subset of symbols. When pip installs it after `-foundry`, the `__init__.py` file from `-core` (which is what `-foundry` depends on) is **overwritten on disk**, and imports like `from agent_framework import MCPStdioTool` start failing with `ImportError`.

If you accidentally installed it:

```bash
pip uninstall -y agent-framework agent-framework-core agent-framework-foundry
pip install "agent-framework-foundry==1.8.0"
```

See also: [`../../anti-patterns/meta-package-overwrite.md`](../../anti-patterns/meta-package-overwrite.md).

---

## Optional add-ons

Install these **only when you need them**. None of them are pulled in by `-foundry`.

| Package | When to install | Provides |
|---------|----------------|----------|
| `agent-framework-devui` | Local UI / dashboard for an agent or workflow | `from agent_framework.devui import serve` |
| `agent-framework-anthropic` | Anthropic models as a `ChatClient` | `AnthropicChatClient` |
| `agent-framework-azure-ai-search` | RAG context retrieval from an Azure AI Search index (semantic or agentic mode) | `AzureAISearchContextProvider` — see [`context-providers-rag.md`](context-providers-rag.md) |
| `agent-framework-azure-contentunderstanding` | Azure Content Understanding analyzer | `ContentUnderstandingClient` |
| `agent-framework-azure-cosmos` | Cosmos DB-backed chat history **and** workflow checkpoint storage | `CosmosHistoryProvider`, `CosmosCheckpointStorage` — see [`history-providers.md`](history-providers.md) / [`../../patterns/workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) |
| `agent-framework-foundry-local` | Local Foundry runtime adapter | `FoundryLocalChatClient` |
| `agent-framework-mem0` | Semantic long-term memory via Mem0 (OSS or Platform) | `Mem0ContextProvider` — see [`context-providers-rag.md`](context-providers-rag.md) |
| `agent-framework-redis` | Redis-backed chat history **and** RAG context (full-text + optional vector search) | `RedisHistoryProvider`, `RedisContextProvider` — see [`history-providers.md`](history-providers.md) / [`context-providers-rag.md`](context-providers-rag.md) |
| `agent-framework-monty` | **Sandboxed code execution** (local + Docker) — *not* a memory store | `MontyExecuteCodeTool`, `MontyCodeActProvider` — `Status: Experimental` |
| `agent-framework-azurefunctions` | Bind agents to Azure Functions triggers | Function bindings |
| `agent-framework-orchestrations` | Multi-agent orchestrations (handoff, group chat) | `Handoff*`, `GroupChat*` |
| `agent-framework-durabletask` | Persist workflow state via Azure Durable Functions / Durable Task Framework | `DurableTaskWorkflowExecutor` |
| `agent-framework-declarative` | Load agents and workflows from YAML / JSON files | `AgentFactory`, `WorkflowFactory` — `Status: BETA` (`1.0.0b260528`). See [`declarative.md`](declarative.md) and [`../../anti-patterns/declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md). Brings `httpx`, `powerfx` (Python < 3.14 only), `pyyaml` as transitive deps. |
| `agent-framework-a2a` | Agent-to-Agent transport (`A2AClient` / server) | `A2AServer`, `A2AClient` |

> [!NOTE]
> **`agent-framework-devui` is on a date-based beta track**, not a 1.x pinned release. The current PyPI version is `1.0.0b260528`. Pin it explicitly: `pip install "agent-framework-devui==1.0.0b260528"`. The `serve()` signature changes between betas — see [`devui.md`](devui.md).

---

## Persistence / memory packages — capability matrix

Because "memory" overlaps three distinct mechanisms (chat history, RAG context, workflow checkpoints), it is easy to install the wrong package. This matrix is the authoritative mapping:

| Package | Chat history (`HistoryProvider`) | RAG context (`ContextProvider`) | Workflow checkpoints (`CheckpointStorage`) | Notes |
|---------|----------------------------------|----------------------------------|--------------------------------------------|-------|
| (core) | `InMemoryHistoryProvider`, `FileHistoryProvider` ⚠️ exp | — | `InMemoryCheckpointStorage`, `FileCheckpointStorage` | Ships with `agent-framework-core` |
| `agent-framework-mem0` | — | `Mem0ContextProvider` (Mem0 SaaS or OSS) | — | Long-term semantic memory |
| `agent-framework-redis` | `RedisHistoryProvider` | `RedisContextProvider` (full-text + optional vector via redisvl) | — | Two **separate** classes; install once, choose mechanism |
| `agent-framework-azure-cosmos` | `CosmosHistoryProvider` | — | `CosmosCheckpointStorage` | Production storage for both turns and workflow state |
| `agent-framework-azure-ai-search` | — | `AzureAISearchContextProvider` (`mode="semantic"` or `mode="agentic"`) | — | RAG retrieval over an existing AI Search index |
| `agent-framework-monty` | — | — | — | **Not memory** — sandboxed code execution (`MontyExecuteCodeTool`, `MontyCodeActProvider`) |

> [!IMPORTANT]
> A row that is empty is not a gap — it means the package **deliberately does not** offer that mechanism. For example, `agent-framework-azure-ai-search` does not implement `HistoryProvider`; pairing it with a chat history backend means installing **two** packages (e.g., `-azure-ai-search` for RAG + `-azure-cosmos` for history).

Deep dives:
- [`history-providers.md`](history-providers.md) — `RedisHistoryProvider`, `CosmosHistoryProvider` constructors and auth
- [`context-providers-rag.md`](context-providers-rag.md) — `Mem0ContextProvider`, `RedisContextProvider`, `AzureAISearchContextProvider`
- [`memory-experimental.md`](memory-experimental.md) — experimental `MemoryStore` / `MemoryFileStore` / `MemoryContextProvider` from `_harness/_memory.py`
- [`../../patterns/workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) — checkpoint backends including Cosmos

---

## Lazy namespace re-exports

`agent_framework.foundry` is a **lazy namespace**, not a normal package. When you access an attribute, it tries to import the matching `agent-framework-<provider>` package on demand. If you have not installed the package, you get a `ModuleNotFoundError` with a pip hint:

```python
>>> from agent_framework.foundry import AnthropicChatClient
ModuleNotFoundError: To use AnthropicChatClient, install `agent-framework-anthropic`.
```

This is by design — it lets the top-level `agent_framework.foundry` namespace expose every backend without forcing you to install every backend. Just install the one you actually need.

---

## How to verify your install

```python
import importlib.metadata as md
for pkg in [
    "agent-framework-foundry",
    "agent-framework-core",
    "agent-framework-openai",
]:
    print(pkg, "==", md.version(pkg))
```

Expected:

```
agent-framework-foundry == 1.8.0
agent-framework-core == 1.8.0
agent-framework-openai == 1.8.0
```

If `agent-framework-core` is missing or pinned to a different minor, the wheel was overwritten — re-install per the recovery snippet above.

---

## See also

- [`clients.md`](clients.md) — `FoundryChatClient` usage
- [`devui.md`](devui.md) — DevUI beta version pinning
- [`../../anti-patterns/meta-package-overwrite.md`](../../anti-patterns/meta-package-overwrite.md) — full explanation of the meta-package trap
- [`../../migration-guides/from-1.5-to-1.6.md`](../../migration-guides/from-1.5-to-1.6.md) — what changed for installations between 1.5 and 1.6
