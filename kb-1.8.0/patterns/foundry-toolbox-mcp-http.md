# Pattern: Foundry Toolbox via MCP Streamable HTTP

> Status: **Experimental** (Foundry Toolbox side is in preview as of Nov 2026)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: parent demo `src/demo7_toolbox.py`
> See also: [API ref — `tools-mcp.md`](../api-reference/1.8.0/tools-mcp.md#mcpstreamablehttptool)

## Goal

Connect an agent to a **Foundry Toolbox** (Microsoft-hosted collection of MCP tools) over the streamable HTTP MCP transport. Use this to leverage pre-built tools without spinning up your own MCP servers.

> [!NOTE]
> **Foundry Toolbox is still in preview**. The MCP endpoint URL format and toolbox names may change. Always check the Foundry portal → Toolboxes for the current list and URLs.

## When to use

- ✅ You want Microsoft-managed tools (e.g., browser automation, code interpretation, custom Foundry toolboxes).
- ✅ Your project has the relevant Toolbox connected via Foundry portal.
- ❌ The MCP server is your own / local → use [`local-mcp-stdio.md`](local-mcp-stdio.md) instead.
- ❌ You need fine-grained tool selection within the toolbox — 1.3.0 removed `select_toolbox_tools`; the toolbox is exposed as a unit now.

## Prerequisite — Toolbox enabled in Foundry

1. Foundry portal → your project → **Toolboxes**.
2. Pick a toolbox (e.g., "Browser Automation Toolbox").
3. Copy the **MCP endpoint URL** (a `https://...projects/.../toolboxes/.../mcp` URL).
4. Add to `.env`:
   ```
   FOUNDRY_TOOLBOX_MCP_URL=https://<project-endpoint>/toolboxes/<name>/mcp
   ```

## Code

```python
import asyncio
import os
from pathlib import Path

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
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


async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")
    toolbox_url = _require_env("FOUNDRY_TOOLBOX_MCP_URL")

    toolbox = MCPStreamableHTTPTool(
        name="foundry-toolbox",
        url=toolbox_url,
        # 1.3.0+: select_toolbox_tools(...) was removed. The toolbox is exposed wholesale.
    )

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=project_endpoint, model=model, credential=cred
        )
        async with client.as_agent(
            name="toolbox_user",
            instructions=(
                "You have access to a Foundry Toolbox. Use its tools to answer the user."
            ),
            tools=[toolbox],
        ) as agent:
            result = await agent.run("Show me the page title of https://example.com")
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| `MCPStreamableHTTPTool(name=..., url=...)` | The 1.3.0+ way to connect to any HTTP-streamable MCP endpoint, including Foundry Toolboxes. |
| **No** `select_toolbox_tools(...)` call | Removed in 1.3.0 (PR #5671). The toolbox now exposes its tools as a single bundle. |
| `name="foundry-toolbox"` | Logical label for tracing / logs. Pick any unique identifier. |
| `MCPStreamableHTTPTool` (not `MCPStdioTool`) | Toolboxes are HTTP endpoints, not subprocesses. |

## Hosted MCP variant (alternative)

If you'd rather have **Foundry itself** broker the MCP connection (so you don't manage credentials in client code), use `client.get_mcp_tool(...)`:

```python
hosted_mcp = client.get_mcp_tool(
    server_label="foundry-toolbox",
    server_url=toolbox_url,
)
```

Trade-off:

| Approach | Pros | Cons |
|---------|------|------|
| `MCPStreamableHTTPTool` (client-side) | Full control, easier debugging, works from anywhere. | You manage MCP auth headers in code. |
| `client.get_mcp_tool(...)` (hosted) | Foundry handles auth + connection. | Requires the toolbox to be reachable from Foundry. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `select_toolbox_tools=[...]` | Removed in 1.3.0. Drop it. |
| Using `MCPStdioTool` with a toolbox URL | Wrong transport. Stdio is for subprocesses. |
| Hardcoding the toolbox URL in code | Use env var; URLs include the project name and may change per environment. |
| Mixing toolbox auth with the chat client's credential | The toolbox auth flows through MCP, not through `FoundryChatClient`. Configure auth headers via `MCPStreamableHTTPTool` if needed. |
| Not handling tool-call failures | Toolbox connectivity can fail. Wrap `agent.run(...)` in try/except and surface a fallback message. |

## Verification

```bash
python path/to/this/script.py
```

Expected: a tool call to the toolbox, then a final answer using the tool's output.

## See also

- [`tools-mcp.md`](../api-reference/1.8.0/tools-mcp.md) — full MCP reference
- [`local-mcp-stdio.md`](local-mcp-stdio.md) — local subprocess variant
- [Microsoft Learn: Foundry Toolboxes](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/toolboxes?view=foundry)
