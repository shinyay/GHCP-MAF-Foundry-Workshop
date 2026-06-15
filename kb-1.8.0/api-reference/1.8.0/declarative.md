# `agent_framework.declarative` — YAML-driven agents and workflows (BETA)

> [!WARNING]
> **Beta package.** `agent-framework-declarative` is shipped as version `1.0.0b260528` and classified as `Development Status :: 4 - Beta` ([`pyproject.toml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/pyproject.toml)). Public APIs may change without semver guarantees. Pin the exact version in `requirements.txt` and budget for migration work between minor versions. This page documents the `1.0.0b260528` surface paired with `agent-framework-core==1.8.0`.

## What this subsystem is

`agent-framework-declarative` lets you describe an agent or a workflow in a YAML file (or `dict`) and instantiate it at runtime via two factory classes. Workflow YAML compiles to the **same** `Executor` graph the imperative `WorkflowBuilder` produces, so checkpointing, visualization, pause/resume, and `WorkflowEvent` semantics all behave identically once the workflow is built — see [`workflows.md`](workflows.md) and [`workflow-internals.md`](workflow-internals.md).

| Capability | Class | YAML | Compiled into |
|---|---|---|---|
| Single agent from YAML | `AgentFactory` | `kind: Prompt` | An `Agent` instance (see [`agents.md`](agents.md)) |
| Workflow from YAML | `WorkflowFactory` | `kind: Workflow` / top-level `actions:` | A `Workflow` whose nodes are `DeclarativeActionExecutor` subclasses |

## Install

Not part of the workshop's default `requirements.txt`. Install separately when you actually need YAML loading:

```bash
pip install 'agent-framework-declarative==1.0.0b260528'
```

Runtime dependencies (per [`pyproject.toml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/pyproject.toml)):

- `agent-framework-core>=1.8.0,<2`
- `httpx>=0.27,<1` (for `DefaultHttpRequestHandler`)
- `powerfx>=0.0.32,<0.0.35; python_version < '3.14'` — Microsoft PowerFx expression language for `=expr` values. **There is no published `powerfx` wheel for Python 3.14**; declarative on 3.14 will fall back / fail at expression evaluation. The workshop venv pins Python 3.12.
- `pyyaml>=6.0,<7.0`

## Public API surface

Re-exported via the lazy stub at [`agent_framework.declarative`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/declarative/__init__.py) (which raises `ModuleNotFoundError` with an install hint if the package isn't installed). The full `__all__` of `agent_framework_declarative` ([`__init__.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/__init__.py)):

| Category | Symbols |
|---|---|
| **Factories** | `AgentFactory`, `WorkflowFactory` |
| **State** | `WorkflowState` |
| **HTTP handlers** | `HttpRequestHandler` (Protocol), `DefaultHttpRequestHandler`, `HttpRequestInfo`, `HttpRequestResult` |
| **MCP handlers** | `MCPToolHandler` (Protocol), `DefaultMCPToolHandler`, `MCPToolInvocation`, `MCPToolResult`, `MCPToolApprovalRequest` |
| **Approval** | `ToolApprovalRequest`, `ToolApprovalResponse` |
| **External input (HITL)** | `ExternalInputRequest`, `ExternalInputResponse`, `AgentExternalInputRequest`, `AgentExternalInputResponse` |
| **Exceptions** | `DeclarativeLoaderError`, `DeclarativeActionError`, `DeclarativeWorkflowError`, `ProviderLookupError` |
| **Provider mapping** | `ProviderTypeMapping` (TypedDict) |
| **Version** | `__version__` (via `importlib.metadata.version("agent_framework_declarative")`) |

> [!NOTE]
> Internal modules (`_loader._safe_mode_context`, `_models.agent_schema_dispatch`, all `_executors_*` and `_declarative_builder`) are **not** public API and may change without notice. The `AgentSchema` / `WorkflowSchema` Pydantic models in `_models.py` are likewise implementation details — use `Factory` methods only.

---

## `AgentFactory` — YAML → `Agent`

Defined at [`_loader.py:L181`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L181).

```python
class AgentFactory:
    def __init__(
        self,
        *,
        client: SupportsChatGetResponse | None = None,
        bindings: Mapping[str, Any] | None = None,
        connections: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        additional_mappings: Mapping[str, ProviderTypeMapping] | None = None,
        default_provider: str = "Foundry",
        safe_mode: bool = True,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None: ...
```

### `safe_mode` (default `True`) — security-critical

> [!IMPORTANT]
> `safe_mode=True` is the default ([`_loader.py:L190`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L190)). In safe mode, **`=Env.*` PowerFx expressions cannot read environment variables** ([`_loader.py:L227-L233`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L227-L233)). The expression silently evaluates to an empty value rather than the env var contents. If a YAML you author requires `=Env.X`, you must explicitly opt in: `AgentFactory(safe_mode=False)`. **Only do this for YAML files you fully trust** — turning off safe mode lets the YAML read every env var in the process.
>
> The recommended pattern for production is to keep `safe_mode=True` and pass env-resolved values through the chat client constructor (`FoundryChatClient` reads `FOUNDRY_PROJECT_ENDPOINT` / `FOUNDRY_MODEL` directly from the environment without going through PowerFx — see [`clients.md`](clients.md)). See [`declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md#2-using-env-without-disabling-safe_mode) for the full anti-pattern.

### Other constructor params

| Param | Meaning | Notes |
|---|---|---|
| `client` | A pre-built `SupportsChatGetResponse` shared by all agents this factory creates | Bypasses provider lookup in YAML when set |
| `bindings` | Function bindings exposed to PowerFx | Useful for custom `=binding.X` references in agent YAML |
| `connections` | Resolves `kind: Reference` connections in YAML | Lets multiple agents share a named connection definition |
| `client_kwargs` | Extra kwargs forwarded to the chat client constructor | E.g. `{"timeout": 30}` |
| `additional_mappings` | Extends the provider type map | Add custom `Provider.ApiType` entries — see below |
| `default_provider` | Used when YAML omits `model.provider` | Default `"Foundry"` ([`_loader.py:L190`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L190)) |
| `env_file_path` | Path to a `.env` to load on init | Loaded via `python-dotenv` |
| `env_file_encoding` | Encoding for the `.env` file | Defaults to `"utf-8"` |

### Methods

All six load methods have sync and async variants:

| Method | Returns | Use when |
|---|---|---|
| `create_agent_from_yaml_path(path)` / `_async` | `Agent` | YAML lives on disk |
| `create_agent_from_yaml(yaml_str)` / `_async` | `Agent` | YAML is a string in memory |
| `create_agent_from_dict(d)` / `_async` | `Agent` | Already-parsed mapping |

The `_async` variants are required when the chat client's construction is async (e.g. some Foundry agent flavors); the sync variants are fine for `OpenAI*` and the default Foundry path.

### Built-in provider type mappings

Defined at [`_loader.py:L54`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L54). Total: **9 providers** built in (extend via `additional_mappings`).

| Provider key | Chat client class | Package |
|---|---|---|
| `AzureOpenAI` | `OpenAIChatClient` | `agent_framework.openai` |
| `AzureOpenAI.Chat` | `OpenAIChatCompletionClient` | `agent_framework.openai` |
| `AzureOpenAI.Responses` | `OpenAIChatClient` | `agent_framework.openai` |
| `Foundry` | `FoundryChatClient` | `agent_framework.foundry` |
| `Foundry.Chat` | `FoundryChatClient` | `agent_framework.foundry` |
| `OpenAI` | `OpenAIChatClient` | `agent_framework.openai` |
| `OpenAI.Chat` | `OpenAIChatCompletionClient` | `agent_framework.openai` |
| `OpenAI.Responses` | `OpenAIChatClient` | `agent_framework.openai` |
| `Anthropic.Chat` | `AnthropicChatClient` | `agent_framework.anthropic` |

> [!NOTE]
> Provider name format is **`Provider.ApiType`** (dot-separated). A common typo is `AzureOpenAIChat` (no dot) which falls through to `ProviderLookupError`. See [`declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md#3-wrong-provider-name).

---

## `WorkflowFactory` — YAML → `Workflow`

Defined at [`_workflows/_factory.py:L40`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_factory.py#L40).

```python
class WorkflowFactory:
    def __init__(
        self,
        *,
        agent_factory: AgentFactory | None = None,
        agents: Mapping[str, SupportsAgentRun | AgentExecutor] | None = None,
        bindings: Mapping[str, Any] | None = None,
        env_file: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        max_iterations: int | None = None,
        http_request_handler: HttpRequestHandler | None = None,
        mcp_tool_handler: MCPToolHandler | None = None,
    ) -> None: ...
```

| Param | Meaning | Notes |
|---|---|---|
| `agent_factory` | Used to materialize agents defined inline in workflow YAML | Defaults to a fresh `AgentFactory(env_file_path=env_file)` if not supplied |
| `agents` | Pre-built agents indexed by name | Looked up when an action is `kind: InvokeAzureAgent` with `agent.name: X` |
| `bindings` | PowerFx bindings + tool-call bindings | |
| `env_file` | `.env` path forwarded to the default `AgentFactory` | |
| `checkpoint_storage` | Enables pause/resume — see [`workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) | |
| `max_iterations` | Overrides YAML `maxTurns` and the core default of 100 supersteps | Workflows with `GotoAction` loops (e.g. `DeepResearch`) typically need a higher cap |
| `http_request_handler` | Required if YAML uses `HttpRequestAction` | Use `DefaultHttpRequestHandler` for dev, **custom handler with allow-list for production** ([`declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md#6-default-handlers-are-ssrf-unsafe)) |
| `mcp_tool_handler` | Required if YAML uses `InvokeMcpTool` | Same SSRF caveats; `DefaultMCPToolHandler` wraps `MCPStreamableHTTPTool` |

### Methods

| Method | Returns | Use when |
|---|---|---|
| `create_workflow_from_yaml_path(path)` | `Workflow` | YAML on disk |
| `create_workflow_from_yaml(yaml_str)` | `Workflow` | YAML in memory |
| `create_workflow_from_definition(d)` | `Workflow` | Parsed dict |
| `register_agent(name, agent) -> WorkflowFactory` | `self` | Add an agent to the lookup after construction; fluent |
| `register_binding(name, func) -> WorkflowFactory` | `self` | Register a callable for use as a PowerFx binding |
| `register_tool(name, func) -> WorkflowFactory` | `self` | Register a Python callable for `InvokeFunctionTool` actions |

> [!IMPORTANT]
> The action `kind: InvokeAzureAgent` is misleadingly named. It invokes **any** registered agent whose `agent.name` matches in YAML — including `OpenAIChatClient`-backed and `FoundryChatClient`-backed agents. The "Azure" suffix is legacy; the dispatcher is provider-agnostic ([`_executors_agents.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_agents.py)).

---

## Action kind catalog (28 total)

YAML actions are dispatched on the `kind:` field. Two routes:

1. **Executor-backed kinds** — looked up in `ALL_ACTION_EXECUTORS` ([`_declarative_builder.py:L52-L62`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py#L52-L62)). 22 kinds.
2. **Builder-only control constructs** — handled inline in `_declarative_builder._build_action(...)` before reaching the executor map; no dedicated executor class. 6 kinds.

> [!WARNING]
> **Unknown `kind:` values are logged at WARNING and silently skipped** ([`_declarative_builder.py:L455-L459`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py#L455-L459)). A typo in `kind` will **not** raise — the action just disappears. Validate against the catalog below and watch the `agent_framework.declarative` logger. See [`declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md#2-unknown-kind-silently-skipped).

> [!IMPORTANT]
> **6 declarative action kinds were removed in 1.8.0** (PR [#6126](https://github.com/microsoft/agent-framework/pull/6126)):
> - `AppendValue` and `EmitEvent` (was in **Basic actions**) — no direct replacement. Use `SendActivity` to emit output; for sequence accumulation, prefer multiple `SetValue` writes or refactor to `EditTableV2`.
> - `Switch` and `Goto` (was in **Builder-only control constructs**) — use `ConditionGroup` (first-match `conditions:` dispatch) and `GotoAction` (canonical name) respectively.
> - `Confirmation` and `WaitForInput` (was in **External input / Human-in-the-loop**) — use `RequestExternalInput` (most general) or `Question` (free-text prompt).
>
> Removed kinds **fail silently** at YAML parse via the same dispatch path noted in the WARNING above ([`_declarative_builder.py:L455-L459`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py#L455-L459)) — the action is dropped without raising. Validate YAML against the post-removal catalog below.

### Basic actions (11)

| `kind` | Purpose | Executor class |
|---|---|---|
| `CreateConversation` | Initialize a fresh `Conversation.*` scope | `CreateConversationExecutor` |
| `SetValue` | Assign a value (literal or `=expr`) to a path | `SetValueExecutor` |
| `SetVariable` | Same as `SetValue`, uses `variable:` key | `SetVariableExecutor` |
| `SetTextVariable` | Assign a string variable | `SetTextVariableExecutor` |
| `SetMultipleVariables` | Bulk assign from a mapping | `SetMultipleVariablesExecutor` |
| `ResetVariable` | Clear a single variable | `ResetVariableExecutor` |
| `ClearAllVariables` | Clear all `Local.*` variables | `ClearAllVariablesExecutor` |
| `SendActivity` | Emit a chat-like output (used in dialog-style flows) | `SendActivityExecutor` |
| `ParseValue` | Parse a string into a typed value | `ParseValueExecutor` |
| `EditTable` | Tabular data mutation (v1) | `EditTableExecutor` |
| `EditTableV2` | Tabular data mutation (v2 — preferred for new YAML) | `EditTableV2Executor` |

Defined in [`_executors_basic.py:L625-L639`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_basic.py#L625-L639).

### Control flow (5 terminators)

| `kind` | Purpose |
|---|---|
| `EndWorkflow` | Terminate workflow, write `Workflow.Outputs.*` |
| `EndDialog` | Alias of `EndWorkflow` ([`_executors_control_flow.py:L552`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_control_flow.py#L552)) |
| `EndConversation` | Terminate the current `Conversation.*` scope without ending the workflow |
| `CancelDialog` | Cancel current dialog block |
| `CancelAllDialogs` | Cancel all dialog blocks |

### Builder-only control constructs (6)

These are **not** in the executor map. The builder rewrites them into branch/loop edges in the compiled `Workflow` graph.

| `kind` | Compiles into | YAML keys |
|---|---|---|
| `If` | Single conditional branch | `condition`, `then` (or `actions` for backward compat), `else` |
| `ConditionGroup` | First-match branch (.NET-style) | `conditions: [{ condition: ..., actions: [...] }, ...]`, `elseActions` |
| `Foreach` | Loop over a collection | `itemsSource` (or `items`/`source`), `actions` |
| `GotoAction` | Unconditional jump | `actionId` |
| `BreakLoop` | Exit nearest `Foreach` | — |
| `ContinueLoop` | Next iteration of nearest `Foreach` | — |

Dispatch in [`_declarative_builder.py:L435-L452`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py#L435-L452). `ConditionGroup` detection via the `conditions:` key at [`L660-L665`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py#L660-L665); `else`/`elseActions`/`default` aliasing at [`L702`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py#L702); Foreach key fallback chain at [`_executors_control_flow.py:L227-L229`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_control_flow.py#L227-L229).

### Agent invocation (1)

| `kind` | Purpose | Notes |
|---|---|---|
| `InvokeAzureAgent` | Look up an agent by `agent.name`, run it on the current conversation | Despite the name, works for **any** registered agent — Foundry, OpenAI, Anthropic. See note above. |

### Tool invocation (1)

| `kind` | Purpose |
|---|---|
| `InvokeFunctionTool` | Call a Python tool registered via `WorkflowFactory.register_tool(...)` |

### HTTP (1)

| `kind` | Purpose | Requires |
|---|---|---|
| `HttpRequestAction` | Make an HTTP call; result goes to a variable | `http_request_handler` ctor param **or build fails** with `DeclarativeWorkflowError` |

### MCP (1)

| `kind` | Purpose | Requires |
|---|---|---|
| `InvokeMcpTool` | Call a tool on an MCP server | `mcp_tool_handler` ctor param **or build fails** with `DeclarativeWorkflowError` |

### External input / Human-in-the-loop (2)

| `kind` | Purpose | Resumes via |
|---|---|---|
| `Question` | Ask a free-text question; pause until external input arrives | `ExternalInputResponse` |
| `RequestExternalInput` | Most general — pass arbitrary `request_info` | `ExternalInputResponse` |

Both pause the workflow at the corresponding superstep; combined with `checkpoint_storage`, they support pause/resume across process restarts. See [`workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) and the HITL section of [`declarative-workflow.md`](../../patterns/declarative-workflow.md#human-in-the-loop-hitl).

---

## Workflow state scopes

`WorkflowState` ([`_workflows/_state.py:L43-L96`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_state.py#L43-L96)) exposes the following dotted-path scopes inside PowerFx expressions and `path:` fields:

| Scope | Direction | Lifetime | Notes |
|---|---|---|---|
| `Workflow.Inputs.*` | **read-only** | workflow run | Initial inputs passed to `workflow.run(inputs_dict)`. Mutation raises `ValueError` ([`_state.py:L237`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_state.py#L237)). |
| `Workflow.Outputs.*` | read/write | workflow run | **Convention for "final" values** (matches .NET / cross-runtime). ⚠️ In Python 1.8.0, `result.get_outputs()` returns **only** values from `ctx.yield_output(...)` (e.g. emitted by `SendActivity` / yielded by `InvokeAzureAgent`) — see [`_workflow.py:L125-L131`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L125-L131). Writing `SetValue → Workflow.Outputs.x` is the right declarative idiom for portability, but to surface the value in `get_outputs()` add a `SendActivity` that references it. |
| `Local.*` | read/write | workflow run | Scratch storage. Not surfaced anywhere unless explicitly yielded. |
| `System.*` | mostly read | workflow run | Framework-provided values, e.g. `System.ConversationId`. |
| `Agent.*` | read | per-agent | Populated by `InvokeAzureAgent` (e.g. `Agent.text` = last response). |
| `Conversation.*` | read/write | conversation scope | Populated by `CreateConversation`; cleared by `EndConversation`. |
| `inputs.*` | **read-only** (alias) | workflow run | Backward-compatible alias for `Workflow.Inputs.*` ([`_state.py:L342-L347`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_state.py#L342-L347)). |

> [!IMPORTANT]
> There is **no `Env.*` scope in workflow state**. `Env.*` is a PowerFx convenience exposed by `AgentFactory` (when `safe_mode=False`), not a workflow variable. Don't write `path: Env.X` — it has no effect. To read environment variables in a workflow, register a binding (`WorkflowFactory.register_binding("env_var", lambda: os.environ["X"])`) or pre-resolve in Python before `workflow.run(...)`.

---

## PowerFx expressions

Values prefixed with `=` are evaluated as [Microsoft PowerFx](https://learn.microsoft.com/power-platform/power-fx/) expressions ([`_powerfx_functions.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_powerfx_functions.py)). The framework registers helper functions and the variable scopes above as PowerFx symbols.

### Syntax traps (full list in [`declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md#8-powerfx-syntax-traps))

| Trap | Wrong | Right |
|---|---|---|
| Equality | `=Local.x == 1` | `=Local.x = 1` (PowerFx uses single `=`) |
| Missing prefix | `Concat(...)` | `=Concat(...)` |
| Quote style | `="hello"` (works) | also `='hello'` (PowerFx accepts both) |
| Python literal | `=None`, `=True` | `=Blank()`, `=true` (PowerFx lowercase booleans) |
| Python 3.14 | — | PowerFx wheel unavailable; `=expr` falls back / fails |

---

## Handler abstractions (for production HTTP / MCP)

### `HttpRequestHandler` (Protocol)

Defined at [`_http_handler.py:L90-L120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_http_handler.py#L90-L120). Single method `send(info) -> HttpRequestResult`:

```python
from agent_framework.declarative import HttpRequestHandler, HttpRequestInfo, HttpRequestResult

class HttpRequestHandler(Protocol):
    async def send(self, info: HttpRequestInfo) -> HttpRequestResult: ...
```

`HttpRequestResult` ([`_http_handler.py:L68-L87`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_http_handler.py#L68-L87)) is a dataclass with **exactly** these fields:

| Field | Type | Notes |
|---|---|---|
| `status_code` | `int` | HTTP status |
| `is_success_status_code` | `bool` | Implementations should set, NOT raise on non-2xx |
| `body` | `str` | Decoded response body |
| `headers` | `dict[str, list[str]]` | Multi-value preserved; **keys must be lowercased** per RFC 7230 §3.2 |

The default `DefaultHttpRequestHandler` wraps `httpx.AsyncClient` and **applies no allow-list, no host filtering, and no auth resolution**. Production deployments should subclass:

```python
from urllib.parse import urlparse

import httpx
from agent_framework.declarative import HttpRequestHandler, HttpRequestInfo, HttpRequestResult

class GuardedHandler:
    ALLOWED_HOSTS = {"api.example.com"}

    def __init__(self) -> None:
        self._client = httpx.AsyncClient()

    async def send(self, info: HttpRequestInfo) -> HttpRequestResult:
        host = urlparse(info.url).hostname
        if host not in self.ALLOWED_HOSTS:
            raise PermissionError(f"Blocked: {host}")
        r = await self._client.request(
            info.method,
            info.url,
            headers=info.headers,
            params=info.query_parameters,
            content=info.body,
        )
        return HttpRequestResult(
            status_code=r.status_code,
            is_success_status_code=r.is_success,
            body=r.text,
            headers={k.lower(): [v] for k, v in r.headers.items()},
        )
```

### `MCPToolHandler` (Protocol)

Defined at [`_mcp_handler.py:L114-L143`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_mcp_handler.py#L114-L143). **Single method only** — `invoke_tool`. Approval is **not** part of this Protocol:

```python
from agent_framework.declarative import MCPToolHandler, MCPToolInvocation, MCPToolResult

class MCPToolHandler(Protocol):
    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult: ...
```

Implementations should return `MCPToolResult(is_error=True, error_message=...)` rather than raising for tool-level failures.

Approval is emitted at the executor level via `ctx.request_info(MCPToolApprovalRequest(...), ToolApprovalResponse)` ([`_executors_mcp.py:L277-L292`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_mcp.py#L277-L292)) and resumed via `workflow.run(responses={request_id: ToolApprovalResponse(approved=True)})` — see [Approval / external-input types](#approval--external-input-types) below.

`DefaultMCPToolHandler` wraps `agent_framework.MCPStreamableHTTPTool` ([`_mcp_handler.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_mcp_handler.py)) — same SSRF caveat applies.

---

## Approval / external-input types

| Type | Direction | Purpose |
|---|---|---|
| `ExternalInputRequest` | engine → caller | Generic pause request from `RequestExternalInput` / `Question` |
| `ExternalInputResponse` | caller → engine | Resume payload for the above |
| `AgentExternalInputRequest` | engine → caller | Pause originating in agent middleware |
| `AgentExternalInputResponse` | caller → engine | Resume for agent middleware |
| `ToolApprovalRequest` | engine → caller | Approve/reject a function-tool call. Fields: `request_id`, `function_name`, `arguments` ([`_executors_tools.py:L55-L72`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_tools.py#L55-L72)) |
| `ToolApprovalResponse` | caller → engine | Decision (`approved: bool`) |
| `MCPToolApprovalRequest` | engine → caller | Approve/reject an MCP tool call. Fields: `request_id`, `tool_name`, `server_url`, `server_label`, `arguments`, `header_names` (sorted; **values omitted** to avoid leaking auth secrets) — [`_executors_mcp.py:L71-L96`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_mcp.py#L71-L96) |

These types are surfaced as `WorkflowEvent` instances with `event.type == "request_info"` (NOT `"intermediate"`; see [`_events.py:L297-L312`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L297-L312)). The runner enters `IDLE_WITH_PENDING_REQUESTS` state and pauses until the caller resumes via:

```python
await workflow.run(responses={event.data.request_id: ExternalInputResponse(value="Alice")})
```

See [`_workflow.py:L247-L255`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L247-L255) for the protocol and [`workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) for the checkpointed flavor.

---

## Exceptions

Defined in [`_workflows/_errors.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_errors.py) and [`_loader.py:L121-L130`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L121-L130).

| Exception | Base | Raised by | Meaning |
|---|---|---|---|
| `DeclarativeLoaderError` | `AgentException` | `AgentFactory.create_*` | YAML parse / schema validation / agent build failure |
| `ProviderLookupError` | `DeclarativeLoaderError` | `AgentFactory` | `model.provider` doesn't match any built-in or `additional_mappings` entry |
| `DeclarativeWorkflowError` | `WorkflowException` | `WorkflowFactory.create_*` (build time) | YAML parse, missing `http_request_handler` for `HttpRequestAction`, missing `mcp_tool_handler` for `InvokeMcpTool`, etc. |
| `DeclarativeActionError` | `WorkflowException` | `*Executor` (run time) | Transport / runtime failure inside an action (e.g. non-2xx HTTP) |

See [`exceptions.md`](exceptions.md) for the core hierarchy these extend.

---

## Implementation notes (not public API)

These appear in source but should **not** be imported by application code:

- `agent_framework_declarative._loader._safe_mode_context` — `ContextVar[bool]` used to pass `safe_mode` down into PowerFx evaluation; private.
- `agent_framework_declarative._models.agent_schema_dispatch(schema)` — dispatcher used by `AgentFactory` to pick the right `AgentSchema` subclass; private.
- `agent_framework_declarative._workflows._declarative_builder.DeclarativeWorkflowBuilder` — internal compiler; use `WorkflowFactory.create_workflow_from_*` instead.
- All `*Executor` classes (`SetValueExecutor`, `InvokeAzureAgentExecutor`, etc.) — instantiated by the builder; do not construct directly.

---

## Version lookup

```python
from agent_framework.declarative import __version__
print(__version__)  # '1.0.0b260528' on this template
```

Falls back to `"0.0.0"` if the package metadata can't be found (e.g. running from a source checkout without install) ([`__init__.py:L27-L30`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/__init__.py#L27-L30)).

---

## See also

- [Pattern — `declarative-agent.md`](../../patterns/declarative-agent.md) — worked YAML agent example
- [Pattern — `declarative-workflow.md`](../../patterns/declarative-workflow.md) — worked YAML workflow + HITL
- [Anti-pattern — `declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md) — 8 WRONG/RIGHT pairs (beta API, unknown kind, SSRF, safe_mode, etc.)
- [API ref — `workflows.md`](workflows.md) — the core `Workflow` / `WorkflowBuilder` that declarative compiles into
- [API ref — `workflow-internals.md`](workflow-internals.md) — `Executor` graph internals
- [API ref — `agents.md`](agents.md) — the `Agent` that `AgentFactory` produces
- [API ref — `packages.md`](packages.md) — package install matrix
- [API ref — `exceptions.md`](exceptions.md) — core exception hierarchy
- [Pattern — `workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) — pause/resume mechanics shared with HITL
- Upstream sources: [package root](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/packages/declarative), [YAML samples](https://github.com/microsoft/agent-framework/tree/python-1.8.0/declarative-agents), [Python samples](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/samples/03-workflows/declarative)
- External: [Microsoft PowerFx docs](https://learn.microsoft.com/power-platform/power-fx/) (expression language used in `=expr` values)
