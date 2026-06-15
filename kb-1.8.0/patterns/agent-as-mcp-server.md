# Pattern: Agent-as-MCP-Server (Expose Your Agent over MCP)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`, `mcp==1.27.0` (transitively pinned in this template's venv)
> Verified against: upstream sample [`02-agents/mcp/agent_as_mcp_server.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/mcp/agent_as_mcp_server.py) and source [`_agents.py:L1452-L1573`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1452-L1573)
> See also: [API ref — `composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md), [`tools-mcp.md`](../api-reference/1.8.0/tools-mcp.md)

## Goal

Take an existing `Agent` (or `FoundryAgent`) and expose it as a single-tool **MCP server** so external MCP hosts — Claude Desktop, VS Code GitHub Copilot Agents, Cursor, custom MCP clients — can call it over a transport you supply (stdio is the verified default; HTTP/WebSocket transports are user-driven via the returned `Server` object). `WorkflowAgent` is **not** supported here — see the IMPORTANT note below.

## When to use

| Need | This pattern? |
|---|---|
| Let **Claude Desktop / VS Code MCP** invoke your agent | ✅ |
| Expose an agent to a **non-Python** MCP client | ✅ |
| Coordinate one agent with another **in the same Python process** | ❌ → use [`agent-as-tool-handoff.md`](agent-as-tool-handoff.md) |
| Return rich content (images, audio, files) to the host | ⚠️ only text is forwarded — non-text content is **silently dropped** (see Limitations) |

## Prerequisites

```bash
pip install agent-framework-foundry==1.8.0 mcp
```

`mcp` is **not** a hard dependency of `agent-framework-core` — it's lazy-imported and `as_mcp_server()` raises `ModuleNotFoundError` at call time if missing ([`_agents.py:L1480-L1483`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1480-L1483)). The workshop venv pins `mcp==1.27.0` transitively.

> [!IMPORTANT]
> `as_mcp_server` lives on `RawAgent` ([`_agents.py:L1452`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1452)), **not `BaseAgent`**. `Agent` and `FoundryAgent` inherit through `RawAgent`, so the call site is identical. **`WorkflowAgent` does NOT have `as_mcp_server`** — it inherits `BaseAgent` directly ([`_workflows/_agent.py:L52`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L52)). See [class hierarchy in `composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md#class-hierarchy-where-each-method-lives).

## Worked example (stdio transport, production-shaped)

```python
# pattern: agent-as-mcp-server (stdio transport)
# Verified against samples/02-agents/mcp/agent_as_mcp_server.py
# Improvement over sample: wraps agent in `async with` for resource cleanup.

from typing import Annotated

import anyio
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv(override=False)


@tool(approval_mode="never_require")
def get_specials() -> Annotated[str, "Returns the specials from the menu."]:
    return (
        "Special Soup: Clam Chowder\n"
        "Special Salad: Cobb Salad\n"
        "Special Drink: Chai Tea"
    )


@tool(approval_mode="never_require")
def get_item_price(
    menu_item: Annotated[str, "The name of the menu item."],
) -> Annotated[str, "Returns the price of the menu item."]:
    return "$9.99"


async def run() -> None:
    async with AzureCliCredential() as credential:
        # FoundryChatClient is NOT a context manager in 1.8.0; just instantiate.
        client = FoundryChatClient(credential=credential)
        agent = Agent(
            client=client,
            name="RestaurantAgent",
            description="Answer questions about the menu.",
            tools=[get_specials, get_item_price],
        )

        # Production pattern: wrap agent in async with for proper cleanup.
        # The upstream sample omits this — leaves chat-client connections leaked.
        async with agent:
            server = agent.as_mcp_server(
                server_name="restaurant-mcp",
                version="1.0.0",
            )

            # stdio is the verified transport; you may drive any transport
            # supported by the underlying `mcp.server.lowlevel.Server`.
            from mcp.server.stdio import stdio_server

            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )


if __name__ == "__main__":
    anyio.run(run)
```

## Why each piece

| Line | What it does | Why it matters |
|---|---|---|
| `@tool(approval_mode="never_require")` | Marks the function tools as auto-run | ⚠️ This is fine for read-only menu helpers. For write-effecting tools (DB writes, email, billing), use `"always_require"` and wire an approval handler. |
| `agent = Agent(client=..., name=..., description=..., tools=[...])` | Build the agent **before** wrapping it | The MCP server delegates 100% to this agent's `.run()` — instructions, tools, and the chat client are fixed at this point. |
| `async with agent:` | Activates the agent's async context manager | **Critical — the sample omits this.** Without it, the chat client's HTTP session and the credential's token cache leak when the MCP server exits. See [`anti-patterns/missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md). |
| `server = agent.as_mcp_server(server_name=..., version=...)` | Returns `mcp.server.lowlevel.Server[Any]` ([`L1495`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1495)) | The returned server exposes **exactly one tool** — the agent itself, wrapped via `self.as_tool(name=self._get_agent_name())` ([`L1497`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1497)). It does **not** fan out the agent's internal `tools=[...]`. |
| `from mcp.server.stdio import stdio_server` | Local-import the transport | Lazy import keeps the agent module decoupled from any specific transport. Verified path; HTTP/WebSocket transports follow the same `server.run(read, write, init_opts)` shape. |
| `await server.run(read, write, init_opts)` | Hand the streams to MCP's runtime | Blocks until the host disconnects. The MCP runtime handles initialization, capability negotiation, and tool calls. |

## Limitations (must-know)

### Single tool exposed, not a fan-out

The server publishes **one** tool — the agent itself. Internal tools the agent uses (`get_specials`, `get_item_price`) are **not** exposed individually. The MCP client calls `RestaurantAgent("show me the specials")`, and the agent decides internally which tools to invoke ([`L1497`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1497)).

### Text-only content forwarding

When the agent's response contains rich content (images, audio, data, URIs), only `TextContent` items are forwarded back through MCP. Everything else is **silently dropped** with a `logger.warning(...)` ([`_agents.py:L1554-L1564`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1554-L1564)). Do not expose an image-generating agent over MCP and expect the host to receive images.

### Errors wrapped as `McpError(INTERNAL_ERROR, ...)`

Tool-execution failures are wrapped in `McpError(INTERNAL_ERROR, str(exc))` ([`_agents.py:L1544-L1550`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1544-L1550)). The full stack stays on the server side; the host only sees the message string.

### `_get_agent_name()` uses raw `self.name`, not sanitization

The tool exposed to MCP is named via `_get_agent_name()` ([`L1575-L1581`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1575-L1581)) which returns `self.name or "UnnamedAgent"` **raw** — it does *not* run `_sanitize_agent_name`. If `self.name` contains whitespace or punctuation, MCP hosts may reject the tool spec. Use machine-safe agent names (`"RestaurantAgent"`, not `"Restaurant Agent"`).

## MCP host configuration

### Claude Desktop / VS Code GitHub Copilot Agents

Add this to your MCP host config (e.g., `~/.config/Claude/claude_desktop_config.json` on macOS, or VS Code's MCP `settings.json`):

```json
{
    "servers": {
        "restaurant-agent": {
            "command": "uv",
            "args": [
                "--directory=/absolute/path/to/your/project",
                "run",
                "agent_as_mcp_server.py"
            ],
            "env": {
                "FOUNDRY_PROJECT_ENDPOINT": "https://your-project.services.ai.azure.com/api/projects/your-project",
                "FOUNDRY_MODEL": "gpt-5-4"
            }
        }
    }
}
```

(JSON shape verified from the upstream sample's docstring at [`02-agents/mcp/agent_as_mcp_server.py:L18-L35`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/mcp/agent_as_mcp_server.py#L18-L35).)

The host will spawn your script over stdio, send MCP initialization, then call the single tool when the user asks something relevant.

### Custom MCP clients

Any client speaking the MCP protocol over stdio works. If you need HTTP/WebSocket transport, replace `stdio_server()` with the corresponding MCP transport (`mcp.server.sse` / `mcp.server.websocket`) and call `server.run(read, write, init_opts)` the same way.

## Variants

### Server-owned shared resources via `lifespan`

If your MCP server needs to maintain a DB pool or cache that lives for the whole server lifetime (not per-request), pass a `lifespan` callable:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def db_lifespan(server):
    pool = await create_pool(...)
    try:
        yield {"db": pool}
    finally:
        await pool.close()

server = agent.as_mcp_server(
    server_name="restaurant-mcp",
    version="1.0.0",
    lifespan=db_lifespan,
)
```

(`lifespan` signature: [`_agents.py:L1458`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1458).)

> [!NOTE]
> `lifespan` is for resources tied to the **MCP server process** lifecycle. Agent-owned resources (chat client, credential) belong inside `async with agent:` — they are constructed before the server starts and should be released when the server exits.

### Workflow → MCP server is **not** directly supported

`Workflow.as_agent()` returns a `WorkflowAgent` which inherits `BaseAgent` directly ([`_workflows/_agent.py:L52`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L52)), so it does **not** have `as_mcp_server`. To expose a workflow's behavior over MCP, build a regular `Agent` whose tools internally drive the workflow:

```python
# ❌ Will fail: AttributeError — WorkflowAgent has no as_mcp_server
# workflow_agent = my_workflow.as_agent(name="ResearchPipeline")
# server = workflow_agent.as_mcp_server(...)

# ✅ Wrap the workflow in a tool, then expose a regular Agent over MCP
@tool
async def run_pipeline(query: Annotated[str, "research topic"]) -> str:
    result = await my_workflow.run(query)
    return result.output_text

bridge_agent = Agent(client=client, name="research_mcp", tools=[run_pipeline])
async with bridge_agent:
    server = bridge_agent.as_mcp_server(server_name="research-mcp")
```

See [`workflow-as-agent-nesting.md`](workflow-as-agent-nesting.md) for the `as_agent` constraints (especially the `list[Message]` `input_types` requirement).

### Override the exposed tool name

The MCP tool name comes from `self.name` raw. If you cannot rename the agent (because other code depends on it), wrap once:

```python
agent.name = "restaurant_tool"  # machine-safe name for MCP
async with agent:
    server = agent.as_mcp_server()
```

## Common mistakes

### Forgetting `pip install mcp`

```python
# ❌ Wrong — agent-framework-core does NOT depend on mcp
import os; os.system("pip install agent-framework-core")
from agent_framework import Agent  # works
agent = Agent(client=...)
server = agent.as_mcp_server()      # ModuleNotFoundError at THIS line, not at import
```

```python
# ✅ Right — install mcp explicitly
# pip install agent-framework-foundry mcp
from agent_framework import Agent
agent = Agent(client=...)
async with agent:
    server = agent.as_mcp_server()
```

### Skipping `async with agent:` (the sample does this — don't follow it in production)

```python
# ❌ Wrong — leaks chat-client connections on server shutdown
agent = Agent(client=client, name="...", tools=[...])
server = agent.as_mcp_server()
async with stdio_server() as (r, w):
    await server.run(r, w, server.create_initialization_options())
```

```python
# ✅ Right — async with ensures client.__aexit__ runs at shutdown
agent = Agent(client=client, name="...", tools=[...])
async with agent:
    server = agent.as_mcp_server()
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
```

### Expecting image / file output through MCP

```python
# ❌ Wrong — image agent + MCP = silently dropped images
image_agent = Agent(client=client, name="ImageGen", tools=[client.get_image_generation_tool().as_dict()])
async with image_agent:
    server = image_agent.as_mcp_server()
    # Client receives only the agent's text commentary, never the image bytes
```

For rich-content scenarios, use `agent-as-tool-handoff.md` (in-process) or return URLs that the host can fetch.

### Putting agent-owned resources in MCP `lifespan`

```python
# ❌ Wrong — credential + client live in MCP lifespan, but the agent already owns them
@asynccontextmanager
async def bad_lifespan(server):
    async with AzureCliCredential() as cred:
        # FoundryChatClient is NOT a context manager in 1.8.0; just instantiate.
        client = FoundryChatClient(credential=cred)
        agent = Agent(client=client, name="restaurant_tool", tools=[...])
        async with agent:
            yield {"client": client}
```

This conflates the MCP server's resource scope with the agent's. The agent was constructed with `client` already; the lifespan-yielded client is unused. Use `async with agent:` for agent resources, `lifespan` for server-only resources (DB pools, caches not held by the agent).

## Verification

Run the script directly to confirm it launches:

```bash
python agent_as_mcp_server.py
# (waits on stdin for MCP protocol messages — Ctrl+C to exit)
```

Smoke import:

```bash
python -c "import mcp; from mcp.server.lowlevel import Server; from mcp.server.stdio import stdio_server; print('mcp import OK')"
python -c "from agent_framework import Agent; from agent_framework.foundry import FoundryChatClient; print('agent-framework import OK')"
```

End-to-end: register the server in Claude Desktop / VS Code MCP and ask "What are the specials?". You should see the agent's text response routed back through MCP.

## See also

- [API ref — `composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md) — full `as_mcp_server` signature + matrix
- [API ref — `tools-mcp.md`](../api-reference/1.8.0/tools-mcp.md) — the **inverse** direction (consuming MCP servers with `MCPStdioTool`/`MCPStreamableHTTPTool`)
- [Pattern — `agent-as-tool-handoff.md`](agent-as-tool-handoff.md) — in-process handoff alternative
- [Pattern — `workflow-as-agent-nesting.md`](workflow-as-agent-nesting.md) — wrap workflow → agent (note: `WorkflowAgent` cannot itself be exposed via `as_mcp_server` — see the "Workflow → MCP server is **not** directly supported" section above)
- [Anti-pattern — `composition-pitfalls.md`](../anti-patterns/composition-pitfalls.md) — 13 things to avoid
- [Anti-pattern — `missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md) — general lifecycle guidance
