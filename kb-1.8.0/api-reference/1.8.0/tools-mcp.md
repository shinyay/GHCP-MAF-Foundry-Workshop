# Tools: MCP (Model Context Protocol)

> Status: **Stable** for `MCPStdioTool` / `MCPStreamableHTTPTool`. `MCPWebsocketTool` is **NEW in 1.6.0**.
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: introspection + parent demos `src/demo3_hosted_mcp.py` (stdio), `src/demo7_toolbox.py` (streamable HTTP)

> [!IMPORTANT]
> **Required runtime dependency**: All three MCP tool classes (`MCPStdioTool`,
> `MCPStreamableHTTPTool`, `MCPWebsocketTool`) **require the `mcp` Python package**
> at runtime. It is an **optional extra** of `agent-framework-core` (only included
> with `agent-framework-core[all]`). The class import itself succeeds (no `mcp`
> needed), but the lazy import inside `connect()` will raise
> `ModuleNotFoundError: \`MCPStreamableHTTPTool\` requires \`mcp\`. Please install \`mcp\`.`
> at first tool call.
>
> **Install before runtime**:
> ```bash
> pip install mcp        # minimum requirement (any MCP tool)
> # or for full optional surface:
> pip install "agent-framework-core[all]"
> ```
>
> **Verification recipe** (catch this at implementation time, not at runtime):
> ```bash
> python -c "from mcp.client.streamable_http import streamable_http_client; print('ok')"
> ```

MCP (Model Context Protocol) is an open protocol for connecting LLM agents to tool servers. Agent Framework ships three transports:

| Class | Transport | Use when |
|-------|-----------|---------|
| `MCPStdioTool` | Subprocess stdio (npx / python / docker) | Local MCP server you launch from your process. Demo 3 pattern. |
| `MCPStreamableHTTPTool` | HTTP + SSE streaming | Remote MCP server reachable over HTTPS. Demo 7 pattern (Foundry Toolbox). |
| `MCPWebsocketTool` | WebSocket | **NEW 1.6.0.** Use when the server requires bidirectional streaming. Not yet validated by the parent demos. |

All three are passed to `tools=[...]` as **objects** (not dicts — that's the difference from hosted tools).

---

## `MCPStdioTool`

### Signature

```python
MCPStdioTool(
    name: str,
    command: str,
    *,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike | None = None,
    description: str | None = None,
    approval_mode: ApprovalMode | None = None,    # "never" | "always" | "function" | callable
    allowed_tools: list[str] | None = None,        # restrict which server tools the agent can call
    load_prompts: bool = True,                     # load MCP-server-provided prompts into instructions
    load_resources: bool = True,
    timeout: float | None = None,
)
```

### Example — sequential-thinking server via npx (canonical)

From parent demo `src/demo3_hosted_mcp.py`:

```python
import shutil
from agent_framework import MCPStdioTool

# Precheck — fail fast with a clear message if npx isn't on PATH.
if not shutil.which("npx"):
    raise RuntimeError(
        "MCPStdioTool requires npx. Install Node.js or use the dev container."
    )

tools=[
    MCPStdioTool(
        name="sequential-thinking",
        command="npx",
        load_prompts=False,                        # don't auto-inject server's prompt into instructions
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
    )
]
```

### Lifecycle

`MCPStdioTool` is an **async context manager**. The runtime enters it automatically when you pass it to `tools=[...]` and exits on agent cleanup (i.e. when the `async with client.as_agent(...) as agent:` block exits).

Subprocess lifecycle is handled for you — you don't need to clean up manually.

### `approval_mode`

For tools that take destructive actions (file system writes, shell execution), set `approval_mode`:

| Value | Behavior |
|-------|---------|
| `"never"` | Calls are auto-approved (default for most servers). |
| `"always"` | Every call requires user approval. Pairs with the `UserInputRequiredException` flow. |
| `"function"` | Always approved, but server-side it's marked as a function-style call. |
| Callable `(call) -> bool \| Awaitable[bool]` | Custom predicate. |

---

## `MCPStreamableHTTPTool`

### Signature

```python
MCPStreamableHTTPTool(
    name: str,
    url: str,
    *,
    description: str | None = None,
    headers: dict[str, str] | None = None,             # e.g. auth bearer tokens
    timeout: float | None = None,
    sse_read_timeout: float | None = None,
    terminate_on_close: bool = True,                   # send DELETE on close
    http_client: httpx.AsyncClient | None = None,      # inject your own client (proxies / TLS)
    header_provider: HeaderProvider | None = None,     # dynamic headers per request (e.g. token refresh)
    approval_mode: ApprovalMode | None = None,
    allowed_tools: list[str] | None = None,
    load_prompts: bool = True,
    load_resources: bool = True,
)
```

### Example — Foundry Toolbox over MCP (canonical)

From parent demo `src/demo7_toolbox.py` lines 125-129:

```python
from agent_framework import MCPStreamableHTTPTool

toolbox_url = os.environ["FOUNDRY_TOOLBOX_MCP_URL"]
# Typical URL shape:
#   https://<acct>.services.ai.azure.com/api/projects/<proj>/toolboxes/<name>/mcp

tools=MCPStreamableHTTPTool(
    name="foundry_toolbox",
    description="Tools served by a Foundry Toolbox over MCP",
    url=toolbox_url,
)
```

> [!IMPORTANT]
> In 1.3.0 the previous `select_toolbox_tools()` helper was **removed** (PR #5671). The MCP transport replaces it. Code that imported `from agent_framework.foundry import select_toolbox_tools` fails to import on 1.3.0+. See [`../../anti-patterns/removed-apis-since-1.0.md`](../../anti-patterns/removed-apis-since-1.0.md).

### Dynamic headers (`header_provider`)

When the auth token rotates (e.g. short-lived Foundry tokens), pass a `header_provider` callable instead of static `headers`:

```python
async def get_auth_headers() -> dict[str, str]:
    token = await get_fresh_token()
    return {"Authorization": f"Bearer {token}"}

MCPStreamableHTTPTool(
    name="my-tool",
    url="https://...",
    header_provider=get_auth_headers,  # called per request
)
```

---

## `MCPWebsocketTool` (NEW 1.6.0)

> Status: **Experimental** in this template — not validated by the parent demos.

```python
from agent_framework import MCPWebsocketTool

tools=[MCPWebsocketTool(
    name="ws_server",
    url="wss://my-mcp-ws-server.example.com",
    headers={"Authorization": f"Bearer {token}"},
)]
```

Use when the MCP server you're connecting to requires WebSocket transport (full-duplex). For most production MCP servers HTTP streaming is enough — only reach for this when the server documentation specifically requires it.

---

## Hosted MCP vs client MCP

| | Hosted MCP (Foundry-side) | Client MCP (your-process-side) |
|---|---|---|
| Factory / class | `client.get_mcp_tool(server_url=...)` | `MCPStdioTool(...)` / `MCPStreamableHTTPTool(...)` |
| Where the connection runs | Inside Foundry | Inside your Python process |
| Latency | One Foundry → MCP hop, no client → server hop | Direct from your process |
| Auth | Configured via Foundry connection | You manage headers/tokens |
| Use when | The MCP server is reachable from Foundry (public or private-networked into Foundry) | The MCP server is on your machine (stdio) or only reachable from your process |

You can mix them: a Code Interpreter (hosted) + a `sequential-thinking` MCP (stdio, client-side) in the same `tools=[...]`.

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Forgetting `shutil.which("npx")` precheck for stdio servers | Add the precheck — failures otherwise produce opaque `FileNotFoundError` from the subprocess. |
| Putting `MCPStreamableHTTPTool` inside `client.get_mcp_tool(...)` | Pick one: hosted MCP (dict, factory) or client MCP (object, direct class). Don't nest. |
| Setting `load_prompts=True` for `sequential-thinking` server (default) | The server's prompts can override your `instructions` in unexpected ways. Demos use `load_prompts=False`. |
| Using `select_toolbox_tools()` | **Removed in 1.3.0.** Use `MCPStreamableHTTPTool(url=...)`. |
| Hardcoding the auth token in `headers` | Use `header_provider=` for token refresh. |

---

## Inverse direction: exposing an agent **as** an MCP server

The classes on this page **consume** an existing MCP server (`MCPStdioTool` connects to a server, `MCPStreamableHTTPTool` calls a hosted server). The **inverse** — turning your own agent into an MCP server so other hosts (Claude Desktop, VS Code MCP) can call it — is `RawAgent.as_mcp_server()`.

- [`composition-adapters.md`](composition-adapters.md) — full `as_mcp_server` signature, behavior, and the broader directional matrix
- [`../../patterns/agent-as-mcp-server.md`](../../patterns/agent-as-mcp-server.md) — end-to-end stdio recipe with Claude Desktop / VS Code MCP host config

## See also

- [`tools-hosted.md`](tools-hosted.md#hosted-mcp-model-context-protocol-from-foundry-side) — hosted-side MCP (Foundry calls the server)
- [`clients.md`](clients.md#hosted-tool-factories--clientget__tool) — full factory table including `get_mcp_tool`
- [`../../patterns/local-mcp-stdio.md`](../../patterns/local-mcp-stdio.md) — full sequential-thinking recipe
- [`../../patterns/foundry-toolbox-mcp-http.md`](../../patterns/foundry-toolbox-mcp-http.md) — Toolbox-over-MCP recipe
- [`../../anti-patterns/composition-pitfalls.md`](../../anti-patterns/composition-pitfalls.md) — pitfalls when exposing agents via MCP (text-only forwarding, `mcp` install requirement, lifecycle)
