# Pattern: Local MCP Server via Stdio (sequential-thinking)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: parent demo `src/demo3_hosted_mcp.py`
> See also: [API ref — `tools-mcp.md`](../api-reference/1.8.0/tools-mcp.md#mcpstdiotool)

## Goal

Connect an agent to a **local MCP server** launched as a subprocess (via `npx`, `python`, or any executable). Use this when you want your agent to leverage MCP tools without depending on a remote MCP endpoint.

The canonical example is `@modelcontextprotocol/server-sequential-thinking`, which gives the model a "scratchpad" for step-by-step reasoning before answering.

## When to use

- ✅ You want to add an MCP server's tools to your agent and the server runs as a stdio process.
- ✅ You're running locally / in a dev container with `npx` (or `python` / `node`) available.
- ❌ The MCP server is remote (HTTPS endpoint) → use [`foundry-toolbox-mcp-http.md`](foundry-toolbox-mcp-http.md) or `MCPStreamableHTTPTool` directly.
- ❌ You want Foundry to host the MCP connection → use `client.get_mcp_tool(server_url=...)`.

## Prerequisite — Node.js / npx on PATH

The default dev container in this template has it. To verify:

```bash
which npx && node --version
```

If not present, install Node.js LTS (v20+).

## Code

```python
import asyncio
import os
import shutil
from pathlib import Path

from agent_framework import MCPStdioTool
from agent_framework.foundry import FoundryChatClient
from agent_framework.exceptions import ChatClientInvalidResponseException
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


for k, v in dotenv_values(Path(__file__).resolve().parents[1] / ".env").items():
    if v is not None and not (os.getenv(k) or "").strip():
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _require_command(cmd: str) -> str:
    """Fail fast if a CLI command isn't on PATH (rather than getting opaque FileNotFoundError later)."""
    resolved = shutil.which(cmd)
    if not resolved:
        raise RuntimeError(
            f"Required command not on PATH: {cmd}. "
            "This demo needs Node.js / npx — install it or use the dev container."
        )
    return resolved


async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")
    _require_command("npx")

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=project_endpoint, model=model, credential=cred
        )
        async with client.as_agent(
            name="event_coordinator",
            instructions=(
                "You are an event planner. Use the sequential-thinking tool to break "
                "down the planning into clear steps before answering."
            ),
            tools=[
                MCPStdioTool(
                    name="sequential-thinking",
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
                    load_prompts=False,   # don't auto-inject the server's prompts into instructions
                )
            ],
        ) as agent:
            try:
                result = await agent.run(
                    "Plan a corporate holiday party for 50 people on December 6th, 2026 in Seattle."
                )
            except ChatClientInvalidResponseException as ex:
                if "Failed to resolve model info" in str(ex):
                    raise RuntimeError(
                        "FOUNDRY_MODEL deployment name doesn't exist."
                    ) from ex
                raise
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| `MCPStdioTool(name=..., command=..., args=...)` | Spawns the MCP server as a subprocess and connects over stdio. The runtime enters/exits the tool as an async context manager automatically when the agent starts/stops. |
| `_require_command("npx")` precheck | If npx isn't on PATH, the failure mode is an opaque `FileNotFoundError` from the subprocess. The precheck gives a clear, actionable error. |
| `args=["-y", "@modelcontextprotocol/server-sequential-thinking"]` | `-y` skips the npx confirmation prompt. The package name is the MCP server. |
| `load_prompts=False` | By default `MCPStdioTool` loads any prompts the server advertises into the agent's `instructions`. For `sequential-thinking` these can conflict with your own instructions — opt out. |
| **No** `await agent.cleanup()` | The async context manager (`async with`) handles subprocess shutdown. Manual cleanup is unnecessary and a source of bugs. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| No `_require_command("npx")` precheck | Failures produce opaque `FileNotFoundError`. Always check up front. |
| `MCPStdioTool(command="npx -y @mcp/server")` (all in `command`) | The shell isn't invoked. Pass the args via `args=[...]`. |
| Leaving `load_prompts=True` (default) for `sequential-thinking` | The server's prompts can override your `instructions`. Set `load_prompts=False`. |
| Re-creating `MCPStdioTool` per `agent.run()` call | Spawns a new subprocess every turn. Keep the agent open across turns and the subprocess is reused. |
| Importing `from agent_framework.mcp import ...` | `MCPStdioTool` is exposed at the top level: `from agent_framework import MCPStdioTool`. |

## Verification

```bash
which npx
python path/to/this/script.py
```

Expected: a multi-step plan, with the agent's text reflecting the sequential-thinking tool's reasoning steps.

## See also

- [`tools-mcp.md`](../api-reference/1.8.0/tools-mcp.md) — full `MCPStdioTool` reference
- [`foundry-toolbox-mcp-http.md`](foundry-toolbox-mcp-http.md) — remote MCP variant
- [`error-handling.md`](error-handling.md)
