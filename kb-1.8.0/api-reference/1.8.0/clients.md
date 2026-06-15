# `FoundryChatClient` — clients

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: `inspect.signature(FoundryChatClient.__init__)` + parent demo `src/demo1_run_agent.py` through `src/demo8_rag.py`

`FoundryChatClient` is the single entry point to Microsoft Foundry from this template. Once constructed, it serves three roles:

1. **A chat client** — directly callable for one-off Responses-API requests (rarely used by you; `Agent` does this for you).
2. **An agent factory** — `client.as_agent(...)` returns an `Agent` you actually run.
3. **A hosted-tool factory** — `client.get_*_tool(...)` returns ready-to-pass tool config dicts for `tools=[...]`.

> [!NOTE]
> **1.8.0 — Sync tools run on a worker thread ([PR #5773](https://github.com/microsoft/agent-framework/pull/5773))**: When a synchronous Python function is passed in `tools=[...]`, the framework now dispatches it via `asyncio.to_thread(...)` instead of executing it inline on the event loop. Long-running or blocking sync tools no longer stall streaming, other concurrent tool calls, or the heartbeat. Async tools are unchanged. No code change is required — wrap blocking work in your own thread pool only if you need a custom executor.

---

## Signature

```python
class FoundryChatClient:
    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        project_client: "AIProjectClient | None" = None,
        model: str | None = None,
        credential: AsyncTokenCredential | None = None,
        # Common optionals:
        default_headers: dict[str, str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        # Advanced — covered in detail in PR-I:
        allow_preview: bool | None = None,
        instruction_role: str | None = None,
        compaction_strategy: "CompactionStrategy | None" = None,
        tokenizer: "Tokenizer | None" = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: "list[ChatMiddleware] | None" = None,
        function_invocation_configuration: "FunctionInvocationConfiguration | None" = None,
    ) -> None:
        ...
```

| Parameter | Required? | Notes |
|-----------|----------|-------|
| `project_endpoint` | ✅ (or `project_client`) | Full Foundry project endpoint URL (e.g. `https://<account>.services.ai.azure.com/api/projects/<project>`). Source from `FOUNDRY_PROJECT_ENDPOINT` env var. |
| `project_client` | ✅ (alt) | Pre-built `azure.ai.projects.aio.AIProjectClient` — use if you need to share one across multiple chat clients. Mutually exclusive with `project_endpoint`. |
| `model` | ✅ | The **deployment name** of the chat model in this Foundry project (not the model family). Often `gpt-5-4` or similar. Source from `FOUNDRY_MODEL`. |
| `credential` | ✅ (when using `project_endpoint`) | An **async** `AsyncTokenCredential`. Use `azure.identity.aio.AzureCliCredential` (this template's default). Never pass the sync `azure.identity.AzureCliCredential` — see [`../../anti-patterns/sync-credential-in-async.md`](../../anti-patterns/sync-credential-in-async.md). |
| `default_headers` | optional | Extra headers for every HTTP request (e.g. tracking). |
| `env_file_path` / `env_file_encoding` | optional | Override `.env` discovery (default behavior loads `.env` from CWD). |
| Other params | optional | `allow_preview`, `instruction_role`, `compaction_strategy`, `tokenizer`, `additional_properties`, `middleware`, `function_invocation_configuration` — documented in PR-I (cross-cutting). |

> [!NOTE]
> **There is no `instrumentation_enabled` per-client kwarg.** Observability is configured **process-wide** via `agent_framework.observability` (env var `ENABLE_INSTRUMENTATION` or `disable_instrumentation()` function). See [`observability.md`](observability.md) for the full opt-out and per-process toggle. There is also no `api_version` or `http_client` kwarg — service API version is managed by the Foundry SDK; HTTP transport is fixed.

---

## Lifecycle

`FoundryChatClient` is **NOT itself an async context manager**. The `credential` you pass to it is, and the `Agent` returned by `client.as_agent(...)` is. Cleanup flows from those:

```python
async with AzureCliCredential() as cred:
    client = FoundryChatClient(project_endpoint=..., model=..., credential=cred)
    async with client.as_agent(name="...", instructions="...") as agent:
        result = await agent.run("...")
    # agent's HTTP connections cleaned up here
# credential's token cache cleaned up here
```

If you skip `async with` on the credential or the agent, you will see `Unclosed connector` warnings on shutdown. See [`../../anti-patterns/missing-async-with-cleanup.md`](../../anti-patterns/missing-async-with-cleanup.md).

For multi-agent workflows where you need to enter multiple agents, use `contextlib.AsyncExitStack`:

```python
from contextlib import AsyncExitStack

stack = AsyncExitStack()
cred = await stack.enter_async_context(AzureCliCredential())
client = FoundryChatClient(project_endpoint="...", model="gpt-5-4", credential=cred)
agent1 = await stack.enter_async_context(client.as_agent(name="a1", instructions="..."))
agent2 = await stack.enter_async_context(client.as_agent(name="a2", instructions="..."))
# ... use them ...
await stack.aclose()
```

This is exactly what the parent demo's `_create_agent_factory()` helper does (`src/demo5_workflow_edges.py`).

---

## Hosted tool factories — `client.get_*_tool(...)`

`FoundryChatClient` exposes **15 factory methods** that build hosted-tool config dicts. The dict is passed directly into `tools=[...]` on `client.as_agent(...)`.

| Method | Status | Brief |
|--------|--------|-------|
| `get_a2a_tool(...)` | Experimental | Agent-to-agent connector |
| `get_azure_ai_search_tool(...)` | Stable | Azure AI Search index lookups |
| `get_bing_custom_search_tool(...)` | Stable | Custom Bing search instance |
| `get_bing_grounding_tool(connection_id=..., market=..., count=...)` | Stable | Bing web grounding |
| `get_browser_automation_tool(...)` | Experimental | Playwright-style browser automation |
| `get_code_interpreter_tool()` | Stable | Sandboxed Python execution |
| `get_computer_use_tool(...)` | Experimental | Computer-use API |
| `get_fabric_tool(...)` | Experimental | Microsoft Fabric data |
| `get_file_search_tool(vector_store_ids=..., max_num_results=...)` | Stable | RAG over Foundry vector store |
| `get_image_generation_tool(...)` | Stable | DALL-E / image gen |
| `get_mcp_tool(...)` | Stable | Hosted-side MCP server registration |
| `get_memory_search_tool(...)` | Experimental | Memory search |
| `get_sharepoint_tool(...)` | Experimental | SharePoint document grounding |
| `get_shell_tool(...)` | Experimental **(new in 1.6.0)** | Shell command exec — see [`tools-shell.md`](tools-shell.md) |
| `get_web_search_tool(...)` | Stable | Generic web search (provider-agnostic) |

Each method returns an object whose `.as_dict()` gives you the JSON config Foundry expects. The parent demo pattern is:

```python
tools=[client.get_code_interpreter_tool().as_dict()]
```

> [!NOTE]
> For **Bing grounding specifically**, the parent demos use a slightly different shape — they go through `azure.ai.projects.models.BingGroundingTool` because it exposes `BingGroundingSearchConfiguration` with finer-grained params. See [`tools-hosted.md`](tools-hosted.md#bing-grounding-canonical-pattern).

---

## Example — minimum working client + agent

```python
import asyncio
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async def main() -> None:
    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint="https://acct.services.ai.azure.com/api/projects/proj",
            model="gpt-5-4",
            credential=cred,
        )
        async with client.as_agent(
            name="hello",
            instructions="You are a concise assistant.",
        ) as agent:
            result = await agent.run("Say hello in one short sentence.")
            print(result.text)

asyncio.run(main())
```

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Passing `azure.identity.AzureCliCredential` (sync) | Use `azure.identity.aio.AzureCliCredential` (async). [Anti-pattern](../../anti-patterns/sync-credential-in-async.md) |
| Skipping `async with` on credential/agent | Wrap with `async with` or `AsyncExitStack`. [Anti-pattern](../../anti-patterns/missing-async-with-cleanup.md) |
| Reading `FOUNDRY_MODEL` from Codespaces secrets that are empty | Use the fill-only `.env` loader. [Anti-pattern](../../anti-patterns/empty-env-vars-codespaces.md) |
| Using `client.as_agent` as a plain function (no `async with`) | `as_agent` is an **async context manager factory** — `async with client.as_agent(...) as agent:` |

---

## See also

- [`agents.md`](agents.md) — what to do with the agent returned by `as_agent`
- [`tools-hosted.md`](tools-hosted.md) — full coverage of each `get_*_tool` factory
- [`tools-mcp.md`](tools-mcp.md) — for MCP tools (passed alongside hosted tool dicts)
- [`exceptions.md`](exceptions.md) — what `client.as_agent(...).run()` can raise
- [`../../patterns/canonical-agent-creation.md`](../../patterns/canonical-agent-creation.md) — end-to-end recipe
