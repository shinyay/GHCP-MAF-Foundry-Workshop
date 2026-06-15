# Tools: Hosted (Bing, Code Interpreter, File Search, Image Generation, …)

> Status: see per-tool tags below
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: introspection of `FoundryChatClient.get_*_tool()` factories + parent demos `src/demo2_web_search.py`, `src/demo5_workflow_edges.py`, `src/demo8_rag.py`

Hosted tools run **inside Foundry**, not in your Python process. You get them by:

1. Calling a factory on the client: `client.get_<name>_tool(...)`.
2. Passing the returned object **directly** into `tools=[...]` on `client.as_agent(...)`, or calling `.as_dict()` first.
3. (Both forms work: upstream samples pass the SDK object directly; the parent workshop demos in this repo call `.as_dict()`. Either is accepted by `Agent`.)

The Foundry client exposes **14 hosted-tool factories** (5 stable, 9 experimental — 2 `FOUNDRY_TOOLS`, 7 `FOUNDRY_PREVIEW_TOOLS`; see the stability map at the bottom of this page), plus one **inherited** factory from the OpenAI base class: `get_shell_tool`, which is documented separately in [`tools-shell.md`](tools-shell.md). See [`clients.md`](clients.md#hosted-tool-factories--clientget__tool) for the full table.

> [!IMPORTANT]
> Several factories in this page are decorated with `@experimental(...)` and will emit `FutureWarning` at runtime. The stability tier (FOUNDRY_TOOLS vs FOUNDRY_PREVIEW_TOOLS), what the warnings mean, and how to filter them are documented in **[`feature-stages.md`](feature-stages.md)**. Read that page before reaching for any experimental factory in production.

This page covers the **four most-used** in detail (Bing grounding, Code Interpreter, File Search, Image Generation) and lists the others with their `@experimental` tier tags.

---

## Bing grounding (canonical pattern)

> Status: Recipe A — **No Agent Framework experimental warning** (uses `azure.ai.projects` SDK objects directly); backend/service stability is governed by the Azure AI Projects / Foundry Bing Grounding docs.
> Status: Recipe B — **Experimental** (`get_bing_grounding_tool` is `@experimental(FOUNDRY_TOOLS)`; see [`feature-stages.md`](feature-stages.md)).
> Verified against: parent demo `src/demo2_web_search.py` lines 80-105, `src/demo5_workflow_edges.py` lines 232-248; upstream [`foundry/_chat_client.py:L461`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L461)

There are **two ways** to wire Bing grounding. Both work in 1.8.0. **Prefer Recipe A in this template** — it doesn't go through an `@experimental` factory and matches the parent demos verbatim.

### Recipe A — `BingGroundingTool` (no framework warning, recommended)

```python
from azure.ai.projects.models import (
    BingGroundingSearchConfiguration,
    BingGroundingSearchToolParameters,
    BingGroundingTool,
)

def _build_bing_grounding_tool() -> dict:
    connection_id = (os.getenv("BING_CONNECTION_ID")
                     or os.getenv("BING_PROJECT_CONNECTION_ID") or "").strip()
    if not connection_id:
        raise RuntimeError(
            "Hosted Bing grounding requires BING_CONNECTION_ID. "
            "Set it to the full ARM resource ID of a Bing.Grounding connection."
        )
    cfg = BingGroundingSearchConfiguration()
    cfg.project_connection_id = connection_id
    cfg.market = "en-US"
    cfg.count = 5
    return BingGroundingTool(
        bing_grounding=BingGroundingSearchToolParameters(search_configurations=[cfg])
    ).as_dict()
```

Then:

```python
tools=[_build_bing_grounding_tool()]
```

### Recipe B — `client.get_bing_grounding_tool(...)` (newer surface, **experimental**)

```python
import warnings
from agent_framework import ExperimentalFeature

# Newer factory surface — but @experimental(FOUNDRY_TOOLS).
# This call emits FutureWarning unless filtered. See feature-stages.md.
tools=[client.get_bing_grounding_tool(
    connection_id=os.environ["BING_CONNECTION_ID"],
    market="en-US",
    count=5,
)]
```

Both produce the same Foundry payload. Use Recipe A in this template (matches the parent demos verbatim and does not surface the Agent Framework experimental warning; backend behavior is the same either way and is governed by the Azure Bing Grounding service).

### Where the connection_id comes from

1. In the Foundry portal, open your project → **Connected resources** → **Add Bing Search**.
2. Choose "Grounding with Bing Search" SKU (this is the only one that supports grounding).
3. Copy the **project connection ID** (an ARM resource ID like `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<acct>/projects/<proj>/connections/<conn>`).
4. Set it as `BING_CONNECTION_ID` in `.env`.

---

## Code Interpreter

> Status: **Stable**
> Verified against: parent demo `src/demo5_workflow_edges.py` line 342; upstream [`foundry/_chat_client.py:L343`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L343)

```python
# Direct object form (upstream samples) — preferred:
tools=[client.get_code_interpreter_tool()]

# Dict form (parent workshop demos) — also works:
tools=[client.get_code_interpreter_tool().as_dict()]
```

That's it — no config needed. The model gets a sandboxed Python environment with the usual data-science stack (numpy, pandas, matplotlib, scipy). When the model wants to do arithmetic or generate a chart, it calls this tool.

Tracing: code-interpreter calls show up as `gen_ai.tool.name == "code_interpreter"` in OpenTelemetry spans.

---

## File Search (Foundry vector store → RAG)

> Status: **Stable**
> Verified against: parent demo `src/demo8_rag.py` lines 173-194

```python
file_search_tool = client.get_file_search_tool(
    vector_store_ids=["vs_abc123", "vs_def456"],  # 1+ Foundry vector stores
    max_num_results=5,                            # snippets per query
)

async with client.as_agent(
    name="rag_specialist",
    instructions=(
        "Use the file_search tool to ground every claim in the indexed documents. "
        "If the documents don't answer a question, say so explicitly."
    ),
    tools=[file_search_tool],
) as agent:
    result = await agent.run("Summarize the venue contract constraints.")
```

### Where the vector store comes from

1. Foundry portal → your project → **Data + indexes** → **Create vector store**.
2. Upload files (PDFs, docx, md).
3. Copy the vector store ID (looks like `vs_<base64>`).
4. Set `FOUNDRY_VECTOR_STORE_IDS=vs_abc123` (comma-separated for multiple).

### Tuning

| Param | Effect |
|-------|--------|
| `vector_store_ids` | Which corpora to search. You can attach more than one. |
| `max_num_results` | Snippets returned per call. Default 5; raise for higher recall, lower for cost. |

> [!NOTE]
> File Search returns **passages with citations** that the model can quote. Always instruct the agent to cite source documents when grounding (see the example instruction above).

---

## Image Generation

> Status: **Stable**
> Source: [`foundry/_chat_client.py:L584`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L584)

```python
tools=[client.get_image_generation_tool()]   # or .as_dict()
```

When the model wants to produce an image, it calls this tool. The result comes back as a URL / data URI in the `AgentResponse.messages` content.

Note: not all model deployments support image generation tool-calls. Check the model card in Foundry.

---

## Azure AI Search

> Status: **Experimental** (`get_azure_ai_search_tool` is `@experimental(FOUNDRY_TOOLS)` — see [`feature-stages.md`](feature-stages.md)).
> Verified against: upstream [`foundry/_chat_client.py:L689`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L689)

```python
# Emits FutureWarning on first use. Filter via the recipes in feature-stages.md.
tools=[client.get_azure_ai_search_tool(
    connection_id="<arm-id-of-azure-ai-search-connection>",
    index_name="my-index",
)]
```

Use when your knowledge base is in **Azure AI Search** (vector or hybrid) rather than a Foundry-managed vector store. The connection is set up in the Foundry portal under "Connected resources".

---

## Generic web search

> Status: **Stable**
> Source: [`foundry/_chat_client.py:L397`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L397)

```python
tools=[client.get_web_search_tool()]
```

Provider-agnostic. Foundry picks the configured web-search backend. Use `get_bing_grounding_tool` instead if you specifically want Bing-grounded citations.

---

## Hosted MCP (model-context-protocol from Foundry side)

> Status: **Stable**
> Source: [`foundry/_chat_client.py:L625`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L625)

```python
tools=[client.get_mcp_tool(
    server_label="my-server",
    server_url="https://my-mcp-server.example.com",
    headers={"Authorization": "Bearer ..."},
)]
```

This is the **hosted-side** MCP tool — Foundry connects to the MCP server. For **client-side** MCP (your process opens the connection), see [`tools-mcp.md`](tools-mcp.md).

---

## Foundry factory stability map (1.8.0)

This is the authoritative tier list. Stability tags come from the `@experimental(...)` decorator on each factory in [`foundry/_chat_client.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py). See [`feature-stages.md`](feature-stages.md) for what `FOUNDRY_TOOLS` and `FOUNDRY_PREVIEW_TOOLS` mean and how to filter the warnings.

### ✅ Stable (no `@experimental` decorator)

| Factory | Source | Use for |
|---|---|---|
| `get_code_interpreter_tool()` | [`:L343`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L343) | Sandboxed Python (numpy / pandas / matplotlib). |
| `get_file_search_tool(vector_store_ids, ...)` | [`:L366`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L366) | RAG over Foundry vector stores. |
| `get_web_search_tool()` | [`:L397`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L397) | Provider-agnostic web search. |
| `get_image_generation_tool()` | [`:L584`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L584) | DALL-E-style image generation. |
| `get_mcp_tool(server_label, server_url, ...)` | [`:L625`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L625) | Foundry-side MCP (server reached from Foundry). |

### ⚠️ Experimental — `FOUNDRY_TOOLS` tier

These will surface in Foundry GA but the **signature is not yet locked**. Pin your Foundry SDK and Foundry runtime version when deploying these.

| Factory | Source |
|---|---|
| `get_bing_grounding_tool(connection_id, ...)` | [`:L461`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L461) |
| `get_azure_ai_search_tool(connection_id, index_name, ...)` | [`:L689`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L689) |

### 🧪 Experimental — `FOUNDRY_PREVIEW_TOOLS` tier (preview features)

These are **preview features** in Foundry itself, not just preview SDK surfaces — the backend behavior is also evolving. Treat as proof-of-concept only.

| Factory | Source |
|---|---|
| `get_bing_custom_search_tool(...)` | [`:L522`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L522) |
| `get_sharepoint_tool(...)` | [`:L733`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L733) |
| `get_fabric_tool(...)` | [`:L757`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L757) |
| `get_memory_search_tool(...)` | [`:L781`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L781) |
| `get_computer_use_tool(...)` | [`:L815`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L815) |
| `get_browser_automation_tool(...)` | [`:L843`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L843) |
| `get_a2a_tool(...)` | [`:L867`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_chat_client.py#L867) |

### Inherited from `OpenAIChatClient` (separate page)

| Factory | Source | Status |
|---|---|---|
| `get_shell_tool(func=None, ...)` | [`openai/_chat_client.py:L1083`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/openai/agent_framework_openai/_chat_client.py#L1083) | **Stable** factory. Hosted (no func) is OpenAI-Responses-supported; local function-backed variants use the alpha `agent-framework-tools` wheel. See [`tools-shell.md`](tools-shell.md). |

For each experimental factory: read its docstring with `help(client.get_<name>_tool)` for the current signature. Read **[`feature-stages.md`](feature-stages.md)** first to understand the warning model and to set up appropriate filters.

---

## Mixing hosted, MCP, and function tools

You can freely combine them in a single `tools=[...]` — direct objects and dicts can coexist:

```python
tools=[
    # Function tool
    my_function,
    # Hosted tools — direct object form (upstream-preferred)
    client.get_code_interpreter_tool(),
    # Hosted tools — dict form via .as_dict() (used by parent workshop demos)
    _build_bing_grounding_tool(),
    # MCP tools (object, not dict)
    MCPStdioTool(name="seq", command="npx", args=["-y", "@modelcontextprotocol/server-sequential-thinking"]),
]
```

The model sees all of them in its tool catalog and picks based on the user query + instructions.

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Using `HostedWebSearchTool` / `HostedCodeInterpreterTool` classes | **Removed in 1.0 GA.** Use `get_*_tool()` factories. [Anti-pattern](../../anti-patterns/removed-apis-since-1.0.md) |
| Setting `BING_CONNECTION_ID` to the "Bing Search v7" SKU instead of "Grounding with Bing Search" | Only the grounding SKU works with `BingGroundingTool`. |
| Forgetting `FOUNDRY_VECTOR_STORE_IDS` empty-string handling in Codespaces | Use the fill-only `.env` loader. [Anti-pattern](../../anti-patterns/empty-env-vars-codespaces.md) |
| Blanket-suppressing `FutureWarning` to silence experimental factories | Filter by **message regex** instead — see [`feature-stages.md`](feature-stages.md). Global suppression hides every framework deprecation, not just the one you wanted. |
| Assuming `get_bing_grounding_tool` / `get_azure_ai_search_tool` are stable | They're `@experimental(FOUNDRY_TOOLS)`. Either pin tightly or use the SDK-direct form (Bing Recipe A). |

---

## See also

- [`feature-stages.md`](feature-stages.md) — stability tiers (`FOUNDRY_TOOLS`, `FOUNDRY_PREVIEW_TOOLS`) and warning-filtering recipes
- [`clients.md`](clients.md) — `FoundryChatClient` + full factory list
- [`tools-mcp.md`](tools-mcp.md) — client-side MCP
- [`tools-shell.md`](tools-shell.md) — hosted shell + `LocalShellTool` / `DockerShellTool` (1.6.0)
- [`../../patterns/hosted-bing-search.md`](../../patterns/hosted-bing-search.md)
- [`../../patterns/rag-with-file-search.md`](../../patterns/rag-with-file-search.md)
