# Anti-Pattern: Missing `async with` for Credential / Client / Agent Cleanup

> Status: **Active hazard**
> Affects: 1.0.0 → 1.8.0
> Severity: **Medium** — connection leaks, "Unclosed connector" warnings, slow shutdowns, subprocess zombies (MCP)

## Symptom

At process exit you see:

```
sys:1: ResourceWarning: unclosed <ssl.SSLSocket fd=10, family=AddressFamily.AF_INET, ...>
Unclosed client session
Unclosed connector
RuntimeError: Event loop is closed
```

Or in long-running services: TCP connections accumulate, eventually hitting the OS's ulimit.

For MCP-based agents using `MCPStdioTool`: orphan subprocesses (npx, node) keep running after your script exits.

## Why it's wrong

Agent Framework hands you objects that hold **live resources** (HTTP sessions, token caches, OTel processors, MCP subprocesses). Those resources only release **when the async context manager exits**. Forgetting `async with` means:

- `aiohttp`'s connection pool isn't closed → warnings + leaks.
- `azure.identity.aio` credential's HTTP client keeps sockets open.
- `MCPStdioTool`'s subprocess keeps running until the OS reaps it.
- OTel span batches may not flush → missing traces.

The async context manager pattern is **required**, not optional.

## Wrong code

```python
import asyncio
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async def main():
    cred = AzureCliCredential()                 # ← not in `async with`
    client = FoundryChatClient(
        project_endpoint=..., model=..., credential=cred
    )
    agent = await client.as_agent(...).__aenter__()   # ← bypass async with

    result = await agent.run("hi")
    print(result.text)

    # NO cleanup! Process exit triggers warnings.

asyncio.run(main())
```

## Correct code — Single agent

```python
async def main():
    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=..., model=..., credential=cred
        )
        async with client.as_agent(...) as agent:
            result = await agent.run("hi")
            print(result.text)
    # cred and agent closed cleanly here.
```

## Correct code — Multi-agent workflow (AsyncExitStack)

When you have 3+ agents, nested `async with` becomes unreadable. Use `AsyncExitStack`:

```python
from contextlib import AsyncExitStack

async def main():
    async with AsyncExitStack() as stack:
        cred = await stack.enter_async_context(AzureCliCredential())
        client = FoundryChatClient(
            project_endpoint=..., model=..., credential=cred
        )

        researcher = await stack.enter_async_context(client.as_agent(name="researcher", ...))
        writer = await stack.enter_async_context(client.as_agent(name="writer", ...))
        reviewer = await stack.enter_async_context(client.as_agent(name="reviewer", ...))

        # All 3 agents + cred close in reverse order on exit.
        wf = WorkflowBuilder(start_executor=researcher, output_from=[reviewer])\
            .add_edge(researcher, writer)\
            .add_edge(writer, reviewer)\
            .build()

        result = await wf.run("hi")
```

## Quirks

| Object | Async context manager? | Notes |
|--------|------------------------|-------|
| `azure.identity.aio.AzureCliCredential` | ✅ Yes | Always wrap. |
| `FoundryChatClient` | ❌ No (1.8.0) | The client itself isn't a context manager — its agents and credential are. Don't try `async with FoundryChatClient(...)`. |
| `client.as_agent(...)` | ✅ Yes | Always wrap. |
| `MCPStdioTool` | ✅ Yes (entered automatically by agent) | The agent's context manager handles MCP tool lifecycle for you. Don't enter it twice. |
| `Agent` (created via `Agent(client=...)`) | ✅ Yes | Same shape as `client.as_agent(...)`. |
| `Workflow` (from `WorkflowBuilder.build()`) | ❌ No | The workflow doesn't own resources — its executors (agents) do, and they're managed individually. |

## How to detect

Run your script with the `-W error::ResourceWarning` flag:

```bash
python -W error::ResourceWarning your_script.py
```

This promotes resource warnings to fatal errors so you can't ignore them.

Or grep for the wrong pattern:

```bash
rg "\.as_agent\(" --type py | rg -v "async with"
# Each hit needs review (some may be inside helper functions; check the call site).
```

## See also

- [`sync-credential-in-async.md`](sync-credential-in-async.md)
- [Pattern — `multi-agent-workflow.md`](../patterns/multi-agent-workflow.md) — full AsyncExitStack pattern
- [API ref — `clients.md`](../api-reference/1.8.0/clients.md)
