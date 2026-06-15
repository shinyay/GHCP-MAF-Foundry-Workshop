# Pattern: Persistent Chat History with Azure Cosmos DB

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0` + `agent-framework-azure-cosmos`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent-framework-azure-cosmos/_history_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-cosmos/agent_framework_azure_cosmos/_history_provider.py)

## Goal

Persist agent conversation history durably in **Azure Cosmos DB** so chats survive process restarts, can be replayed across worker pods, and meet enterprise audit / retention requirements — with managed-identity (Entra ID) auth and zero secrets in code.

## When to use

- Production deployment (multi-replica, autoscaling).
- You need conversation continuity across process / pod restarts and across regions.
- You need audit-grade durability with multi-region replication SLAs.
- You are **not** using a service that stores history server-side (Foundry threads, OpenAI Assistants). If you are using Foundry threads, just set `AgentSession(service_session_id=thread_id)` and skip this pattern.

## Prerequisites

| Resource | What | RBAC role |
|----------|------|-----------|
| Azure Cosmos DB (NoSQL) account | Standard account | — |
| Database | E.g., `agents` | — |
| Container | E.g., `chat-history`, partition key `/session_id` | — |
| Identity | The runtime managed identity / `az login` user | `Cosmos DB Built-in Data Contributor` |

```bash
pip install "agent-framework-foundry==1.8.0" "agent-framework-azure-cosmos"
```

> [!IMPORTANT]
> The **data plane** role `Cosmos DB Built-in Data Contributor` (id `00000000-0000-0000-0000-000000000002`) is what `DefaultAzureCredential` needs. The control-plane RBAC role `Cosmos DB Account Reader Role` is **not** enough. Assign with `az cosmosdb sql role assignment create`.

## Env vars (recommended)

```bash
AZURE_COSMOS_ENDPOINT="https://my-acct.documents.azure.com:443/"
AZURE_COSMOS_DATABASE_NAME="agents"
AZURE_COSMOS_CONTAINER_NAME="chat-history"
# No AZURE_COSMOS_KEY needed when using DefaultAzureCredential

FOUNDRY_PROJECT_ENDPOINT="https://<project>.services.ai.azure.com/api/projects/<proj>"
FOUNDRY_MODEL="gpt-5-4"
```

## Code — Cosmos-backed history with managed identity

```python
import asyncio
import os
from agent_framework import AgentSession
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_cosmos import CosmosHistoryProvider
from azure.identity.aio import DefaultAzureCredential


async def main() -> None:
    async with (
        DefaultAzureCredential() as foundry_cred,
        DefaultAzureCredential() as cosmos_cred,
        FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=foundry_cred,
        ) as client,
    ):
        history = CosmosHistoryProvider(
            endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
            database_name=os.environ["AZURE_COSMOS_DATABASE_NAME"],
            container_name=os.environ["AZURE_COSMOS_CONTAINER_NAME"],
            credential=cosmos_cred,
        )

        agent = client.as_agent(
            name="durable-assistant",
            instructions="You are a helpful assistant. Remember context across turns.",
            context_providers=[history],
        )

        # First process: introduce the user
        session = AgentSession(session_id="user-42")
        await agent.run("My name is Yanai.", session=session)

        # Second process: same session_id resumes — history loaded from Cosmos
        session = AgentSession(session_id="user-42")
        result = await agent.run("What is my name?", session=session)
        print(result.text)   # → "Your name is Yanai."


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

- **`async with cosmos_cred, foundry_cred, client`** — Cosmos client (built internally), Foundry credential, and chat client are all async resources. Letting `async with` close them prevents `Unclosed connector` warnings; see [`../anti-patterns/missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md).
- **`credential=cosmos_cred`** — explicit `DefaultAzureCredential` rather than account-key `credential="..."`. Production must use managed identity.
- **No `cosmos_client=` / `container_client=`** — the provider creates its own client (`_owns_client = True`) and closes it on shutdown. Pass a prebuilt one only if you need to share a Cosmos client across providers.
- **Stable `session_id="user-42"`** — Cosmos stores history keyed by `session_id`. Reusing the same id across runs resumes the conversation; passing different ids (or `AgentSession()` with auto-UUID) starts fresh threads.
- **`context_providers=[history]`** — the provider implements the `HistoryProvider` hook contract and is wired by the framework. Optionally combine with a `ContextProvider` for RAG (e.g., `AzureAISearchContextProvider`) — they coexist; see [`../api-reference/1.8.0/context-providers-rag.md`](../api-reference/1.8.0/context-providers-rag.md#cross-cutting-concerns).

## Verification

```bash
python persistent_history_cosmos.py
```

Expected:
- First run: assistant acknowledges the name.
- Second run (after killing the process): assistant recalls "Yanai" from Cosmos.
- In the Azure portal → your Cosmos container, a document with `id` derived from `user-42` appears, containing the full message list.

## Variant — bring your own client (multi-provider, single connection pool)

If you wire multiple Cosmos providers (e.g., chat history + workflow checkpoints) and want them to share a connection pool:

```python
from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential
from agent_framework_azure_cosmos import (
    CosmosHistoryProvider,
    CosmosCheckpointStorage,
)

async with DefaultAzureCredential() as cred:
    cosmos = CosmosClient(
        url=os.environ["AZURE_COSMOS_ENDPOINT"],
        credential=cred,
    )
    try:
        history = CosmosHistoryProvider(
            cosmos_client=cosmos,
            database_name="agents",
            container_name="chat-history",
        )
        checkpoint = CosmosCheckpointStorage(
            cosmos_client=cosmos,
            database_name="agents",
            container_name="workflow-checkpoints",
        )
        # ... use history + checkpoint
    finally:
        await cosmos.close()
```

> [!NOTE]
> When you pass `cosmos_client=`, the provider sets `_owns_client = False` and will **not** close it. Closing is your responsibility.

## Variant — dev / fallback with account key

```python
history = CosmosHistoryProvider(
    endpoint="https://my-acct.documents.azure.com:443/",
    database_name="agents",
    container_name="chat-history",
    credential="account-key-here",        # str = key auth
)
```

Or rely on env var `AZURE_COSMOS_KEY`:

```bash
AZURE_COSMOS_KEY="..."   # provider picks it up automatically
```

> [!WARNING]
> Account keys grant **full data-plane access**. Use them only for local dev or short-lived demos. In CI/CD and production, use managed identity with `Cosmos DB Built-in Data Contributor`.

## Common mistakes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Forbidden` on every operation | Identity lacks `Cosmos DB Built-in Data Contributor` | `az cosmosdb sql role assignment create --account-name <acct> --resource-group <rg> --scope "/" --principal-id <oid> --role-definition-id 00000000-0000-0000-0000-000000000002` |
| `PartitionKey value must be supplied` | Container created with a partition key other than `/session_id` | Recreate the container with partition key `/session_id` (this is what the provider auto-creates on first use; see `_history_provider.py:L273`) |
| `Unclosed client session` warning at exit | Provider built its own Cosmos client but no `async with`/manual close | Wrap construction in an `async with` block, or call `await provider.close()` (when applicable) |
| Settings missing field error at construction | Neither kwargs nor env vars set | Provide `endpoint`+`database_name`+`container_name`+credential at construction OR set the matching `AZURE_COSMOS_*` env vars |
| History from old runs is gone | Used `AgentSession()` (auto-UUID) instead of a stable `session_id` | Pass `AgentSession(session_id="...")` with the same id across runs |
| Duplicate history | Used **both** `AgentSession.service_session_id=` and `CosmosHistoryProvider` | Pick one; if the service stores history, don't attach a `HistoryProvider` |

## See also

- [`../api-reference/1.8.0/history-providers.md`](../api-reference/1.8.0/history-providers.md#cosmoshistoryprovider) — full constructor / overload reference
- [`../api-reference/1.8.0/sessions.md`](../api-reference/1.8.0/sessions.md#historyprovider) — `HistoryProvider` hook contract
- [`session-history-persistence.md`](session-history-persistence.md) — broader patterns including custom backends
- [`workflow-checkpointing.md`](workflow-checkpointing.md) — sibling storage for **workflow** state (via `CosmosCheckpointStorage`)
- [`../anti-patterns/using-the-wrong-memory-primitive.md`](../anti-patterns/using-the-wrong-memory-primitive.md) — when to use a `HistoryProvider` vs `CheckpointStorage`
- [Azure Cosmos DB RBAC docs](https://learn.microsoft.com/azure/cosmos-db/role-based-access-control)

Upstream source: [`agent-framework-azure-cosmos/_history_provider.py:L36-L125`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-cosmos/agent_framework_azure_cosmos/_history_provider.py#L36-L125).
