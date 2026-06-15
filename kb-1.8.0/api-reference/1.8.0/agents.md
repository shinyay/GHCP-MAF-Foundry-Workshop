# `Agent` & `FoundryAgent` — the runtime

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: introspection of `agent_framework.Agent` + `agent_framework.foundry.FoundryAgent` + parent demos 1–8

This page covers the two ways to get a callable agent:

| Class | Use when |
|-------|---------|
| **`client.as_agent(...)`** (returns `Agent`) | You define the agent in code — instructions + tools live in your repo. Used by demos 1–6 + 8. |
| **`FoundryAgent(...)`** | You consume a **service-managed agent** that already exists in Foundry (created via portal, AZD, or VS Code Foundry Toolkit). Used by demo 7. Sometimes called "Hosted Agent V2". |

Both expose the same `.run(...)` / streaming surface.

> [!NOTE]
> **1.8.0 NEW — `FoundryAgent(timeout=...)` ([PR #6263](https://github.com/microsoft/agent-framework/pull/6263))**: `FoundryAgent` now accepts a `timeout: float | None = None` constructor kwarg (seconds) that bounds the wait for any service-managed run before the SDK raises a timeout exception. Previously every invocation inherited the underlying HTTP client default.
>
> **1.8.0 NEW — BackgroundAgentsProvider task-lifecycle extension ([PR #6155](https://github.com/microsoft/agent-framework/pull/6155))**: PR #6155 layers new background-task lifecycle types onto the 1.7.0 `BackgroundAgentsProvider` — `BackgroundTaskInfo`, `BackgroundTaskStatus`, `AgentSession`, and `AgentResponse` (all top-level exports of `agent_framework`). Use `create_harness_agent(...)` (the harness factory — there is **no** public `HarnessAgent` class in 1.8.0) together with `BackgroundAgentsProvider(agents=[...])` to offload long-horizon work behind a queue. Still `@experimental(feature_id=ExperimentalFeature.HARNESS)`; see [`../../patterns/harness-agent.md`](../../patterns/harness-agent.md) and [`../../patterns/background-agents.md`](../../patterns/background-agents.md).

---

## `client.as_agent(...)`

### Signature

```python
def as_agent(
    self,
    *,
    id: str | None = None,
    name: str | None = None,
    description: str | None = None,
    instructions: str | None = None,
    tools: ToolTypes | Callable | Sequence[ToolTypes | Callable] | None = None,
    default_options: OptionsCoT | Mapping[str, Any] | None = None,
    context_providers: Sequence[ContextProvider] | None = None,
    middleware: Sequence[MiddlewareTypes] | None = None,
    require_per_service_call_history_persistence: bool = False,
    function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    compaction_strategy: CompactionStrategy | None = None,
    tokenizer: TokenizerProtocol | None = None,
    additional_properties: Mapping[str, Any] | None = None,
) -> Agent[OptionsCoT]:
```

(Verified: [`_clients.py:L564-L580`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_clients.py#L564-L580).)

| Param | Notes |
|-------|-------|
| `id` | Optional unique id. Auto-generated UUID4 if omitted. |
| `name` | Display name (tracing / DevUI). snake_case is conventional. |
| `description` | Free-text description used by orchestrations (handoff). |
| `instructions` | The system prompt for this agent. |
| `tools` | A single tool, a sequence of tools, or `None`. Tools can be Python callables, `@tool`-decorated functions, MCP tools (`MCPStdioTool`/`MCPStreamableHTTPTool`), or hosted-tool dicts from `client.get_*_tool().as_dict()`. |
| `default_options` | TypedDict with per-call chat options applied to every `run(...)`. **This is where `response_format=` lives** — pass `{"response_format": MyPydanticModel}`. See [`structured-output.md`](structured-output.md). |
| `context_providers` | One or more `ContextProvider` instances (incl. `HistoryProvider`, `InMemoryHistoryProvider`, `SkillsProvider`). Run before/after every invocation. See [`sessions.md`](sessions.md). |
| `middleware` | Sequence of middleware to wrap every `run()` invocation. Mix-and-match: each entry is auto-categorized as `AgentMiddleware`, `ChatMiddleware`, or `FunctionMiddleware`. See [`middleware.md`](middleware.md). |
| `require_per_service_call_history_persistence` | When `True`, installs `PerServiceCallHistoryPersistingMiddleware` so providers persist after **each** model call, not just at the end of the agent run. Used for fine-grained audit logs. |
| `compaction_strategy` | A `CompactionStrategy` subclass to truncate / summarise long histories. |
| `tokenizer` | A `TokenizerProtocol` instance for token counting. |

> [!IMPORTANT]
> `response_format=` is **not** a top-level constructor parameter in 1.8.0 — pass it via `default_options={"response_format": MyModel}` or per-call via `options={"response_format": MyModel}`. Pass-1 of this KB documented it as a top-level param; that was incorrect.

`Agent` instances are async context managers — wrap in `async with` so the chat client and MCP tools get cleaned up:

```python
async with client.as_agent(name="x", instructions="...") as agent:
    result = await agent.run("...")
```

(Verified: [`_agents.py:L770-L831`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L770-L831).)

---

## `Agent.run(...)`

### Signature

```python
AgentRunInputs = str | Content | Message | Sequence[str | Content | Message]

def run(
    self,
    messages: AgentRunInputs | None = None,
    *,
    stream: bool = False,
    session: AgentSession | None = None,
    tools: ToolTypes | Callable | Sequence[ToolTypes | Callable] | None = None,
    options: OptionsCoT | ChatOptions | None = None,
    compaction_strategy: CompactionStrategy | None = None,
    tokenizer: TokenizerProtocol | None = None,
    function_invocation_kwargs: Mapping[str, Any] | None = None,
    client_kwargs: Mapping[str, Any] | None = None,
) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
```

(Verified: [`_agents.py:L889-L901`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L889-L901).)

| Return | When |
|--------|------|
| `AgentResponse[T]` (awaitable) | `stream=False` (default). Has `.text`, `.value` (parsed `T` if `response_format` was set), `.messages`, `.user_input_requests`, `.response_id`, `.usage_details`. |
| `ResponseStream[AgentResponseUpdate, AgentResponse[Any]]` | `stream=True`. **Iterate with `async for`** to consume `AgentResponseUpdate` chunks; **`await` the same stream** (or read after the loop) to get the aggregated `AgentResponse`. |

> [!IMPORTANT]
> The 1.8.0 `agent.run()` signature **does not** include `thread=` or `middleware=` parameters. Pass-1 of this KB documented both — that was incorrect. Multi-turn conversation continuity is done via `session=AgentSession(...)` (see [`sessions.md`](sessions.md)); per-call middleware overrides are not supported — register middleware on the agent constructor instead.

> [!IMPORTANT]
> In 1.5.0 the older `Agent.run_stream(...)` method was **removed**. Pass `stream=True` to `run(...)` instead. See [`../../anti-patterns/removed-apis-since-1.0.md`](../../anti-patterns/removed-apis-since-1.0.md).

### `options=` — per-call overrides

```python
await agent.run(
    "Find venues...",
    options={"response_format": MyPydanticModel},  # demo 4 pattern
)
```

Any kwarg the Responses API accepts (`temperature`, `top_p`, `max_output_tokens`, `tool_choice`, `response_format`, etc.) can go through `options=`. Per-call `options` shallow-merges over the agent's `default_options`.

---

## Streaming

```python
stream = agent.run("Plan an event...", stream=True)
async for update in stream:
    if update.text:
        print(update.text, end="", flush=True)
final: AgentResponse = await stream     # final aggregated response after stream completes
```

For workflow-level streaming (executor lifecycle events with `event.type` discrimination), see [`workflows.md`](workflows.md#workflowevent--workfloweventtype).

---

## `AgentResponse` — accessing the result

```python
result = await agent.run("...")

result.text                  # final text the agent produced
result.value                 # parsed Pydantic instance (if response_format was set)
result.messages              # the message list this run produced (assistant turns)
result.user_input_requests   # function_approval_request items (skill-script approval flow)
```

For workflows, executor outputs follow the same shape — see `_print_result_item()` in parent demo `src/demo5_workflow_edges.py` for a robust fallback walker.

---

## `AgentSession` — conversation continuity

Multi-turn conversations in 1.8.0 are driven by `AgentSession`, **not** `AgentThread` (which Pass-1 of this KB documented but is **not** an `agent.run()` parameter). Reuse a session across `run()` calls:

```python
from agent_framework import AgentSession

session = AgentSession()
await agent.run("Hi, I'm planning an event.", session=session)
await agent.run("What's a reasonable budget for 50 people?", session=session)
```

Pass `service_session_id=...` on `AgentSession` to point at a server-managed conversation (e.g., Foundry thread):

```python
session = AgentSession(service_session_id="thread_abc123")
```

For full reference (`SessionContext`, `ContextProvider`, `HistoryProvider`, serialization), see [`sessions.md`](sessions.md).

---

## `FoundryAgent` — connecting to a Hosted Agent V2

```python
from agent_framework.foundry import FoundryAgent

async with AzureCliCredential() as cred:
    async with FoundryAgent(
        project_endpoint="https://acct.services.ai.azure.com/api/projects/proj",
        agent_name="my-hosted-agent",      # name from Foundry portal
        agent_version="v3",                # optional; omit to use latest
        credential=cred,
    ) as agent:
        result = await agent.run("Hello!")
        print(result.text)
```

When to use `FoundryAgent` instead of `client.as_agent(...)`:

| Use `FoundryAgent` | Use `client.as_agent` |
|---|---|
| Agent definition lives in Foundry (portal / AZD-managed) | Agent definition lives in your repo |
| You want centralised RBAC + identity + tracing | You want fully code-driven config |
| Tool config is attached server-side via Toolbox | Tool config is wired client-side |
| You're deploying to production with version pinning | You're developing / iterating locally |

The two are interchangeable from the caller's perspective — both expose `.run(...)`.

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `agent = client.as_agent(...)` without `async with` | Tools / connections never get cleaned up. Wrap in `async with`. |
| Calling `agent.run_stream(...)` | Removed in 1.5.0. Use `agent.run(..., stream=True)`. |
| Passing `thread=` or `middleware=` to `agent.run(...)` | Not parameters in 1.8.0. Use `session=AgentSession(...)` for continuity; register middleware on the constructor. |
| Passing `response_format=MyModel` directly to `as_agent(...)` | Not a top-level constructor param. Pass via `default_options={"response_format": MyModel}` or per-call `options={"response_format": MyModel}`. |
| `isinstance(event, IntermediateEvent)` | The workflow event classes were unified in 1.5.0. Use `event.type == "intermediate"` (workflow streaming). [Anti-pattern](../../anti-patterns/workflow-event-isinstance.md) |
| Re-creating the agent per turn | Lose `session` + warm tool cache. Hold the agent open across turns. |
| Treating `agent.run(stream=True)` return as a coroutine | It returns a `ResponseStream` (sync). Iterate with `async for` or `await` the stream to get the final aggregated response. |

---

## See also

- [`clients.md`](clients.md) — `FoundryChatClient` constructor + factories
- [`middleware.md`](middleware.md) — full middleware reference (Agent/Chat/Function)
- [`sessions.md`](sessions.md) — `AgentSession`, `ContextProvider`, `HistoryProvider`
- [`skills.md`](skills.md) — `SkillsProvider` (a `ContextProvider`)
- [`workflows.md`](workflows.md) — `WorkflowEvent` discriminator (shared with streaming workflows)
- [`structured-output.md`](structured-output.md) — `response_format=`
- [`evaluation.md`](evaluation.md) — ⚠️ EXPERIMENTAL — evaluate agent quality (`evaluate_agent`, `LocalEvaluator`, `FoundryEvals`)
- [`composition-adapters.md`](composition-adapters.md) — `as_tool` / `as_mcp_server` directional matrix (agent → tool / MCP server / workflow executor)
- [`observability.md`](observability.md) — agent-level spans (`invoke_agent <name>`), `AgentTelemetryLayer`, `AGENT_PROVIDER_NAME`
- [`declarative.md`](declarative.md) — ⚠️ BETA — `AgentFactory` builds an `Agent` from YAML
- [`exceptions.md`](exceptions.md) — what `run()` can raise
- [`../../patterns/canonical-agent-creation.md`](../../patterns/canonical-agent-creation.md) — full inline-agent recipe
- [`../../patterns/foundry-toolbox-mcp-http.md`](../../patterns/foundry-toolbox-mcp-http.md) — `FoundryAgent` recipe
- [`../../patterns/agent-evaluation-local.md`](../../patterns/agent-evaluation-local.md) — deterministic agent evaluation
- [`../../patterns/agent-evaluation-foundry.md`](../../patterns/agent-evaluation-foundry.md) — LLM-as-judge agent evaluation
- [`../../patterns/agent-as-tool-handoff.md`](../../patterns/agent-as-tool-handoff.md) — coordinator + specialists via `as_tool()`
- [`../../patterns/agent-as-mcp-server.md`](../../patterns/agent-as-mcp-server.md) — expose your agent over MCP
- [`../../anti-patterns/composition-pitfalls.md`](../../anti-patterns/composition-pitfalls.md) — 13 things to avoid when composing agents
