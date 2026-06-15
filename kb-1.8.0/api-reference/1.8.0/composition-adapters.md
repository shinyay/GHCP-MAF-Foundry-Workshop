# Composition Adapters: Agent ↔ Tool ↔ MCP Server ↔ Workflow

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_agents.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py), [`_workflows/_workflow.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py), [`_workflows/_workflow_builder.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py), [`_workflows/_agent_executor.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent_executor.py)

Agent Framework exposes a small set of **directional adapters** that let the three first-class abstractions — `Agent`, `Workflow`, `FunctionTool` — be reshaped into one another's API surface. They look "reciprocal" at first glance, but the matrix is **directional**: only three explicit `.as_*()` adapters exist, and several apparent inverses (`tool.as_agent()`, `mcp_server.as_agent()`) are not real APIs.

This page is the authoritative matrix. The two end-to-end recipes live in:

- [`patterns/agent-as-tool-handoff.md`](../../patterns/agent-as-tool-handoff.md) — coordinator + specialists via `as_tool()`
- [`patterns/agent-as-mcp-server.md`](../../patterns/agent-as-mcp-server.md) — expose an agent over MCP via `as_mcp_server()`
- [`patterns/workflow-as-agent-nesting.md`](../../patterns/workflow-as-agent-nesting.md) — wrap a workflow as a single `WorkflowAgent`

For pitfalls, see [`anti-patterns/composition-pitfalls.md`](../../anti-patterns/composition-pitfalls.md).

---

## Directional matrix

Every conversion is a method on the source object — not a free function — and the matrix is asymmetric. The cell legend is:

- ✅ **Public adapter** — a documented `.as_*()` method exists and returns the target shape.
- ⚠️ **Consumption only** — the target shape accepts the source as an input, but no conversion creates a new instance.
- ❌ **Unsupported** — no public adapter; do not write code that assumes one exists.

| From ↓ \ To → | **Agent** | **Workflow / Executor** | **FunctionTool** | **MCP Server** |
|---|---|---|---|---|
| **Agent** | — (same kind) | ✅ `AgentExecutor(agent, ...)` or auto-wrap via [`_maybe_wrap_agent`](workflows.md#agent-auto-wrapping) when passed to `WorkflowBuilder.add_edge()` ([`_workflow_builder.py:L189-L226`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L189-L226)) | ✅ [`BaseAgent.as_tool(...)`](#agentas_tool---function-tool) ([`_agents.py:L478-L572`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L478-L572)) | ✅ [`RawAgent.as_mcp_server(...)`](#rawagentas_mcp_server---mcp-server) ([`_agents.py:L1452-L1573`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1452-L1573)) |
| **Workflow** | ✅ [`Workflow.as_agent(...)`](#workflowas_agent---workflowagent) → `WorkflowAgent` ([`_workflow.py:L1091-L1132`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L1091-L1132)) | — (same kind) | ⚠️ Compose `Workflow.as_agent(...).as_tool(...)` — `WorkflowAgent` inherits `BaseAgent.as_tool` | ❌ Not supported. `WorkflowAgent` inherits **`BaseAgent` only** ([`_workflows/_agent.py:L52`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L52)), so `as_mcp_server` is **not inherited**. Wrap the workflow inside a regular `Agent`-backed tool if MCP exposure is required. |
| **FunctionTool** | ⚠️ Pass in `Agent(tools=[my_tool])` — **consumption only**, no instance is created | ⚠️ No adapter; wrap in an agent first, then add to the workflow | — (same kind) | ❌ No adapter; wrap in an agent first |
| **MCP tool** (`MCPStdioTool` / `MCPStreamableHTTPTool` / `MCPWebsocketTool`) | ⚠️ Pass in `Agent(tools=[my_mcp_tool])` — **consumption only** | ⚠️ Wrap an agent that holds the MCP tool, then add to the workflow | ❌ Not a converted `FunctionTool` (different concrete class — see [`tools-mcp.md`](tools-mcp.md)) | ❌ MCP tools **consume** an MCP server; they do not turn into one |
| **Workflow Executor** | ❌ No adapter | — (same kind) | ❌ No adapter | ❌ No adapter |

**Quick rules:**

1. Only **agents** can become tools or MCP servers (`BaseAgent.as_tool`, `RawAgent.as_mcp_server`).
2. Only **workflows** can become agents (`Workflow.as_agent`); the reverse needs `WorkflowBuilder`.
3. Tools and MCP servers are **terminal targets** — they are consumed by agents, not converted back.
4. `WorkflowBuilder` does the **agent → executor** wrapping internally when you pass an agent to `add_edge`; you rarely need to construct `AgentExecutor` by hand.

---

## Class hierarchy: where each method lives

Adapter methods are spread across the base-class chain. Calling `Agent.as_mcp_server(...)` works because of inheritance, but the **attribution matters** when reading the source.

```text
BaseAgent          ← as_tool() lives here          (_agents.py:L314, method at L478)
  ├─ RawAgent      ← as_mcp_server() lives here    (_agents.py:L578, method at L1452)
  │    ├─ Agent    ← inherits both                  (_agents.py:L1584)
  │    └─ RawFoundryAgent
  │         └─ FoundryAgent ← inherits both         (agent_framework_foundry)
  └─ WorkflowAgent ← inherits as_tool ONLY          (_workflows/_agent.py:L52)
                     (does NOT inherit as_mcp_server)
```

| Class | `as_tool()` | `as_mcp_server()` | Where defined |
|---|---|---|---|
| `BaseAgent` | ✅ owns | ❌ | [`_agents.py:L314`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L314) |
| `RawAgent` | ✅ inherits | ✅ owns | [`_agents.py:L578`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L578) |
| `Agent` | ✅ inherits | ✅ inherits | [`_agents.py:L1584`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1584) |
| `FoundryAgent` | ✅ inherits | ✅ inherits | upstream `agent_framework_foundry/_agent.py` |
| `WorkflowAgent` | ✅ inherits | ❌ **NOT inherited** — `WorkflowAgent(BaseAgent)` skips `RawAgent` | [`_workflows/_agent.py:L52`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L52) |

> [!NOTE]
> `Agent` and `FoundryAgent` runtime behavior for `as_tool` / `as_mcp_server` is **inherited from `RawAgent`** but only the OpenAI-backed sample (`samples/02-agents/tools/agent_as_tool_with_session_propagation.py`) is verified end-to-end in upstream. Foundry-specific service-session interaction is not separately validated in this template — treat with the same caveat as any inherited-but-not-tested code path.

---

## `Agent.as_tool(...)` — Agent → FunctionTool

Wrap any `BaseAgent` as a `FunctionTool` so another agent can call it like a normal tool. This is the **handoff** primitive: the LLM in the parent agent decides when (and whether) to delegate.

### Signature

[`_agents.py:L478-L572`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L478-L572).

```python
def as_tool(
    self,
    *,
    name: str | None = None,
    description: str | None = None,
    arg_name: str = "task",
    arg_description: str | None = None,
    approval_mode: Literal["always_require", "never_require"] = "never_require",
    stream_callback: Callable[[AgentResponseUpdate], Awaitable[None] | None] | None = None,
    propagate_session: bool = False,
) -> FunctionTool: ...
```

### Parameters

| Parameter | Default | Behavior |
|---|---|---|
| `name` | `None` → `_sanitize_agent_name(self.name)` ([`L527`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L527)) | Tool name. If both this and `self.name` are `None`, raises `ValueError("Agent tool name cannot be None")` ([`L528-L529`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L528-L529)). |
| `description` | `None` → `self.description or ""` ([`L530`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L530)) | Tool description shown to the parent LLM. |
| `arg_name` | `"task"` | Name of the single string argument the parent LLM passes. |
| `arg_description` | `None` → `f"Task for {tool_name}"` ([`L531`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L531)) | Argument description shown to the parent LLM. |
| `approval_mode` | `"never_require"` ([`L485`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L485)) | Whether the parent must approve before each call. **Use `"always_require"` in production** when the sub-agent has write effects. |
| `stream_callback` | `None` | If set, wired into the sub-agent's stream via `stream.with_transform_hook(stream_callback)` ([`L552-L559`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L552-L559)). |
| `propagate_session` | `False` ([`L487`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L487)) | If `True`, forwards the parent's `ctx.session` to the sub-agent so both share `session_id` and `state` ([`L555`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L555)). |

### Behavior

1. **Type guard.** Raises `TypeError` if `self` doesn't implement `SupportsAgentRun` ([`L524-L525`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L524-L525)).
2. **Always streams internally.** The wrapper always calls `self.run(..., stream=True)` then `await stream.get_final_response()` ([`L552-L560`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L552-L560)) — `stream_callback` is the user-visible hook.
3. **Re-raises `UserInputRequiredException`.** If the sub-agent's final response contains `user_input_requests`, the wrapper raises `UserInputRequiredException` at the tool boundary ([`L561-L562`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L561-L562)); the parent must handle it.
4. **Input schema.** The returned tool exposes a single required string property `{arg_name}` ([`L533-L543`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L533-L543)).

### Name sanitization

`_sanitize_agent_name` ([`_agents.py:L129-L163`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L129-L163)) replaces every non-`[a-zA-Z0-9_]` character with `_`, collapses runs, strips leading/trailing `_`, and falls back to `"agent"` if the result is empty. **Different display names can collide** to the same tool name:

| `self.name` | Auto-derived tool name |
|---|---|
| `"Research Agent"` | `"Research_Agent"` |
| `"Research-Agent"` | `"Research_Agent"` |
| `"Research.Agent"` | `"Research_Agent"` |
| `"  Research   Agent  "` | `"Research_Agent"` |
| `"!!!"` | `"agent"` |
| `"2nd-helper"` | `"_2nd_helper"` (prefixed because leading digit) |

For production tool names (especially when multiple sub-agents are registered with the same parent), **always pass an explicit `name=` argument** — see [`anti-patterns/composition-pitfalls.md#name-sanitization-collisions`](../../anti-patterns/composition-pitfalls.md#4-tool-name-collisions-from-sanitization).

### Minimal example

```python
from agent_framework import Agent

research = Agent(client=client, name="ResearchAgent", description="Researches a topic.")

# Default settings: independent session, never_require approval
research_tool = research.as_tool()

# Production-ready: explicit stable name, approval gate, shared session
research_tool = research.as_tool(
    name="research",
    description="Researches a topic and returns a 2-sentence summary.",
    arg_name="query",
    arg_description="The research question",
    approval_mode="always_require",
    propagate_session=True,
)

coordinator = Agent(client=client, name="CoordinatorAgent", tools=[research_tool])
```

For the full coordinator + specialist recipe, see [`patterns/agent-as-tool-handoff.md`](../../patterns/agent-as-tool-handoff.md).

---

## `RawAgent.as_mcp_server(...)` — Agent → MCP Server

Expose an agent as a single-tool **MCP server** so external MCP hosts (Claude Desktop, VS Code MCP, Cursor, custom MCP clients) can call it over a transport you supply.

> [!IMPORTANT]
> This method lives on **`RawAgent`** ([`_agents.py:L1452`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1452)), **not** `BaseAgent`. `BaseAgent` only owns `as_tool`. `Agent` and `FoundryAgent` inherit through `RawAgent`, so the call site looks identical — but it is a `RawAgent` method. **`WorkflowAgent` inherits `BaseAgent` directly** ([`_workflows/_agent.py:L52`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L52)) and does **not** have `as_mcp_server` — see [§ "What is *not* supported"](#what-is-not-supported) below.

### Signature

[`_agents.py:L1452-L1573`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1452-L1573).

```python
def as_mcp_server(
    self,
    *,
    server_name: str = "Agent",
    version: str | None = None,
    instructions: str | None = None,
    lifespan: Callable[[Server[Any]], AbstractAsyncContextManager[Any]] | None = None,
    **kwargs: Any,
) -> Server[Any]: ...
```

### Parameters

| Parameter | Default | Behavior |
|---|---|---|
| `server_name` | `"Agent"` ([`L1455`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1455)) | The MCP server name shown to clients. |
| `version` | `None` | Optional server version string passed to MCP `Server(...)`. |
| `instructions` | `None` | Optional server-level instructions (different from agent instructions). |
| `lifespan` | `None` ([`L1458, L1490-L1491`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1458)) | Async context manager called by MCP runtime on server start/stop. Use for **shared resources** (DB pools, cache clients) that the MCP server itself owns. |
| `**kwargs` | `{}` ([`L1492-L1493`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1492-L1493)) | Extra keyword arguments forwarded into `Server(**kwargs)`. |

### Returns

`Server[Any]` from `mcp.server.lowlevel` ([`L1495`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1495)). You drive the transport yourself — typically `mcp.server.stdio.stdio_server` (verified in the upstream sample), but the framework imposes no transport.

### Behavior

1. **Lazy import of `mcp`.** Raises `ModuleNotFoundError("`mcp` is required to use `Agent.as_mcp_server()`. Please install `mcp`.")` at call time if the `mcp` package is missing ([`L1480-L1483`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1480-L1483)). It is **not** a hard dependency of `agent-framework-core` — install it explicitly. The workshop venv pins `mcp==1.27.0` transitively (verified via `pip show mcp`).
2. **Exposes exactly one MCP tool.** The agent itself is wrapped via `self.as_tool(name=self._get_agent_name())` ([`L1497`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1497)) — there is no fan-out of the agent's internal tools. Clients see one tool whose name comes from `_get_agent_name()` ([`L1575-L1581`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1575-L1581)) — which returns `self.name or "UnnamedAgent"` **raw** (not `_sanitize_agent_name`). MCP hosts may reject names with whitespace/punctuation.
3. **Text-only content forwarding.** When the wrapped agent returns rich content (images, audio, data, URIs), only `TextContent` items are forwarded; everything else is **silently dropped** with `logger.warning(...)` ([`_agents.py:L1554-L1564`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1554-L1564)). Plan around this — do not expose an image-generating agent over MCP and expect clients to receive images.
4. **Error wrapping.** Tool execution errors are wrapped in `McpError(INTERNAL_ERROR, ...)` ([`L1544-L1550`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1544-L1550)) — the stack trace is preserved on the server side, but clients only see the message.
5. **`lifespan` for server-owned resources only.** The MCP `lifespan` parameter manages resources tied to the **server's** lifecycle (one start/stop per process). For agent-owned resources (chat client, credential), use `async with agent:` around `server.run(...)` — see the pattern page.

### Minimal example

```python
import anyio
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

async def main() -> None:
    agent = Agent(
        client=OpenAIChatClient(),
        name="RestaurantAgent",
        description="Answer questions about the menu.",
    )

    # Production pattern: wrap in async with for agent cleanup
    async with agent:
        server = agent.as_mcp_server(server_name="restaurant-mcp", version="1.0.0")

        # Drive your chosen transport (stdio shown; HTTP/WebSocket would differ)
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    anyio.run(main)
```

For the full Claude Desktop / VS Code MCP host configuration, see [`patterns/agent-as-mcp-server.md`](../../patterns/agent-as-mcp-server.md).

> [!WARNING]
> The upstream sample [`agent_as_mcp_server.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/mcp/agent_as_mcp_server.py) does **not** wrap the agent in `async with`. That is sample brevity — production code that leaves out `async with agent:` will leak chat-client connections and credentials at server shutdown. See [`anti-patterns/composition-pitfalls.md#mcp-server-without-agent-lifecycle`](../../anti-patterns/composition-pitfalls.md#6-mcp-server-without-agent-lifecycle).

---

## `Workflow.as_agent(...)` — Workflow → WorkflowAgent

Wrap an entire `Workflow` as a single `WorkflowAgent` that satisfies the `SupportsAgentRun` protocol. The returned agent can be passed to **another** workflow or registered as a tool via `as_tool` — but **not** exposed over MCP, because `WorkflowAgent` inherits from `BaseAgent` directly (skipping `RawAgent`), so `as_mcp_server` is not available.

### Signature

[`_workflows/_workflow.py:L1091-L1132`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L1091-L1132).

```python
def as_agent(
    self,
    name: str | None = None,
    *,
    description: str | None = None,
    context_providers: Sequence[ContextProvider] | None = None,
    **kwargs: Any,
) -> WorkflowAgent: ...
```

### Critical precondition

`WorkflowAgent.__init__` ([`_workflows/_agent.py:L120-L121`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L120-L121)) validates that the workflow's **start executor** declares `list[Message]` in its `input_types`. If not, construction fails:

```text
ValueError: Workflow's start executor cannot handle list[Message]
```

This is because `WorkflowAgent._normalize_messages` converts agent-facing inputs (`str`, `Message`, `list[str | Message]`) into `list[Message]` before handing them to the workflow ([docstring at `_workflow.py:L1101-L1106`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L1101-L1106)). A workflow whose entry point expects a custom domain type (`MyJobSpec`, `dict`) cannot be `as_agent()`'d without a normalizing executor at the front.

> See [`patterns/workflow-as-agent-nesting.md`](../../patterns/workflow-as-agent-nesting.md) for the full nested-workflow recipe and the input-type contract.

---

## Agent → Workflow executor: `_maybe_wrap_agent`

`WorkflowBuilder.add_edge(source, target)` accepts either an `Executor` or any `SupportsAgentRun`. When you pass an agent, the builder transparently wraps it via `_maybe_wrap_agent` ([`_workflow_builder.py:L189-L226`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L189-L226)) — this is the "agent → executor" direction in the matrix.

### Identity-based deduplication

```python
agent_instance_id = str(id(candidate))
existing = self._agent_wrappers.get(agent_instance_id)
if existing is not None:
    return existing                                   # reuse same wrapper
```

[`_workflow_builder.py:L209-L213`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L209-L213).

- **Same agent object** reused across edges → **same `AgentExecutor`** → shared `_cache`, `_session`, `_full_conversation`.
- **Different agent objects** that resolve to the **same executor id** (via `resolve_agent_id`) → `ValueError("Duplicate executor ID ...")` ([`L215-L219`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L215-L219)).

When you need two independent positions for the same logical agent in the workflow, create two distinct `Agent(...)` instances or two explicit `AgentExecutor(...)` wrappers — do not reuse the same object. See [`anti-patterns/composition-pitfalls.md#expecting-independent-state-from-reused-agent`](../../anti-patterns/composition-pitfalls.md#12-expecting-independent-state-from-reused-agent).

### `AgentExecutor` `context_mode`

When `_maybe_wrap_agent` constructs the wrapper it uses defaults; if you instantiate `AgentExecutor` directly, you can tune how prior messages are propagated into each run ([`_workflows/_agent_executor.py:L142-L185`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent_executor.py#L142-L185)):

| `context_mode` | Behavior |
|---|---|
| `"full"` (default) | Append the full conversation (all prior messages + latest agent response) to the cache. |
| `"last_agent"` | Provide only the messages from the latest agent response. |
| `"custom"` | Use the `context_filter: Callable[[list[Message]], list[Message]]` to select which messages reach the agent. **Required** when mode is `"custom"` — else `ValueError("context_filter must be provided when context_mode is set to 'custom'.")` ([`L184-L185`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent_executor.py#L184-L185)). |

The default of `"full"` is the safest for short pipelines but **leaks all prior context** to downstream agents — including system instructions and earlier-user PII. For privacy-sensitive handoffs use `"last_agent"` or `"custom"` — see [`anti-patterns/composition-pitfalls.md#default-context-mode-full-for-sensitive-handoffs`](../../anti-patterns/composition-pitfalls.md#9-default-context_mode-full-for-sensitive-handoffs).

---

## Decision guide: which adapter for which problem?

| You need | Use | Why not the alternatives? |
|---|---|---|
| **One LLM decides** at runtime whether/when to delegate to a specialist | `agent.as_tool()` in a coordinator | `WorkflowBuilder` runs every executor in defined order — no choice. |
| **Deterministic** pipeline of specialist agents (research → write → review) | `WorkflowBuilder` with `add_edge` | `as_tool` makes delegation non-deterministic. |
| Expose your agent so **external processes / hosts** (Claude Desktop, VS Code, custom MCP client) can call it | `agent.as_mcp_server()` | `as_tool` is in-process only. |
| Re-use an existing workflow as a building block inside a **different** workflow | `Workflow.as_agent()` + `AgentExecutor` or `WorkflowExecutor` | Workflows are not directly composable; `as_agent` is the bridge. |
| Hand a workflow to **another agent as a tool** (LLM-decided invocation of a whole pipeline) | `Workflow.as_agent().as_tool()` | `WorkflowExecutor` is for workflow-in-workflow; tools are for agent-in-agent. |
| Two independent positions for the same logical agent in a workflow | Two distinct `Agent(...)` instances OR two explicit `AgentExecutor(...)` | `_maybe_wrap_agent` dedupes by `id()` — reusing one object shares state. |

---

## What is *not* supported

To avoid hallucinated APIs in generated code, this section lists conversions Copilot must **not** invent:

- ❌ `FunctionTool.as_agent()` — no such method. Wrap the tool in an `Agent(tools=[tool])`.
- ❌ `MCPStdioTool.as_agent()` / `MCPStreamableHTTPTool.as_agent()` — MCP tools are consumed by agents, not the other way around.
- ❌ `FunctionTool.as_mcp_server()` — no such method. Wrap in an agent first.
- ❌ `AgentExecutor.as_agent()` — executors are workflow-internal; if you have an agent reference, use it directly.
- ❌ `BaseAgent.as_mcp_server()` — exists only on `RawAgent` and subclasses (`Agent`, `FoundryAgent`). `WorkflowAgent` inherits `BaseAgent` directly and does **not** have this method. A custom subclass of `BaseAgent` would have to inherit from `RawAgent` instead.
- ❌ `WorkflowAgent.as_mcp_server()` — `WorkflowAgent(BaseAgent)` skips `RawAgent`; `as_mcp_server` is not inherited. To expose a workflow over MCP, build an `Agent` (or `FoundryAgent`) that internally calls the workflow as a tool.
- ❌ `as_tool(stream=False)` — no `stream` parameter; the wrapper always runs the sub-agent with `stream=True` internally ([`L552-L554`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L552-L554)). Use `stream_callback` to observe.
- ❌ Cycle detection in `WorkflowBuilder` — there is **no construction-time guard** against `A → B → A` cycles or self-as-tool delegation. Avoid via design review.

---

## See also

- [`patterns/agent-as-tool-handoff.md`](../../patterns/agent-as-tool-handoff.md) — coordinator + research-agent with `propagate_session=True`
- [`patterns/agent-as-mcp-server.md`](../../patterns/agent-as-mcp-server.md) — expose agent over MCP stdio, Claude Desktop config
- [`patterns/workflow-as-agent-nesting.md`](../../patterns/workflow-as-agent-nesting.md) — nested workflows via `as_agent()`
- [`patterns/multi-agent-workflow.md`](../../patterns/multi-agent-workflow.md) — `WorkflowBuilder` with `add_edge` (the deterministic alternative to `as_tool` handoff)
- [`anti-patterns/composition-pitfalls.md`](../../anti-patterns/composition-pitfalls.md) — 13 WRONG / RIGHT pairs covering every adapter on this page
- [`api-reference/1.8.0/agents.md`](agents.md) — `Agent` / `RawAgent` core API
- [`api-reference/1.8.0/tools-mcp.md`](tools-mcp.md) — `MCPStdioTool` / `MCPStreamableHTTPTool` / `MCPWebsocketTool` (the inverse direction: consuming MCP servers, not exposing one)
- [`api-reference/1.8.0/workflows.md`](workflows.md) — `WorkflowBuilder`, `Workflow`, `WorkflowEvent`

Upstream sources verified at commit `950673b` ([`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0)):

- [`_agents.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py): `_sanitize_agent_name`, `BaseAgent`, `RawAgent`, `Agent`, `as_tool`, `as_mcp_server`, `_get_agent_name`
- [`_workflows/_workflow.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py): `Workflow.as_agent`
- [`_workflows/_agent.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py): `WorkflowAgent`
- [`_workflows/_workflow_builder.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py): `_maybe_wrap_agent`
- [`_workflows/_agent_executor.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent_executor.py): `AgentExecutor` `context_mode`
- Samples: [`02-agents/tools/agent_as_tool_with_session_propagation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/tools/agent_as_tool_with_session_propagation.py), [`02-agents/mcp/agent_as_mcp_server.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/mcp/agent_as_mcp_server.py)
