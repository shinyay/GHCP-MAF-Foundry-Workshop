# Migration Guide: Cumulative Changes Since 1.0 GA

> Covers 1.0.0 → 1.6.0 (Jan 2026 RC1 era → May 2026 stable)
> Use this when migrating long-lived code that hasn't been touched in many minor versions.

## TL;DR — high-impact change matrix

| Version | High-impact change | Severity |
|---------|-------------------|----------|
| 1.0 GA | Hosted tool classes removed → use `client.get_*_tool(...)` factories | **High** |
| 1.0 GA | Exception hierarchy reorganized → use `AgentFrameworkException` family | **High** |
| 1.0 GA | `agent_framework.tools.FunctionTool` removed → use plain Python funcs | Medium |
| 1.3.0 | `select_toolbox_tools()` removed → use `MCPStreamableHTTPTool(url=...)` | **High** |
| 1.4.0 | DevUI `serve()` defaults tightened (auth ON, host=127.0.0.1) | **High** for shared deployments |
| 1.5.0 | `run_stream()` removed → use `run(stream=True)` | **High** |
| 1.5.0 | `WorkflowBuilder.register_agent()` / `.set_start_executor()` removed → constructor args | **High** |
| 1.5.0 | Workflow events unified to single `WorkflowEvent` class with `type` | **High** |
| 1.5.0 | `"data"` event type became deprecated alias for `"intermediate"` | Cosmetic |
| 1.6.0 | Instrumentation default ON | **Behavior change** |
| 1.6.0 | `opentelemetry-sdk` no longer a hard dep | Dep change |
| 1.6.0 | `client.get_shell_tool(...)` added (experimental, security-sensitive) | Additive |
| 1.7.0 | Declarative `AppendValue`/`EmitEvent`/`Confirmation`/`WaitForInput` removed; `Switch`/`Goto` renamed to `ConditionGroup`/`GotoAction` (PR #6126) | **High** for declarative-beta users |
| 1.7.0 | `TodoProvider` tool names renamed (`add_todos` → `todos_add`, etc., PR #6107) | **Silent breaker** |
| 1.7.0 | `AgentModeProvider` tool names renamed (`set_mode` → `mode_set`, PR #6071) | **Silent breaker** |
| 1.7.0 | `create_harness_agent` + `DEFAULT_HARNESS_INSTRUCTIONS` (PR #6041) | Additive (experimental) |
| 1.7.0 | `BackgroundAgentsProvider` for fan-out (PR #6069) | Additive (experimental) |
| 1.7.0 | `to_prompt_agent(agent)` Foundry helper (PR #5959) | Additive (experimental) |
| 1.7.0 | `ContextWindowCompactionStrategy` (PR #6041) | Additive |

---

## 1.0 GA: Hosted tool classes removed

**Before:**
```python
from agent_framework import HostedWebSearchTool, HostedCodeInterpreterTool, HostedFileSearchTool
bing = HostedWebSearchTool(connection_id=cid)
code = HostedCodeInterpreterTool()
files = HostedFileSearchTool(vector_store_ids=[vs])
```

**After (1.0+):**
```python
bing = client.get_bing_grounding_tool(connection_id=cid)
code = client.get_code_interpreter_tool()
files = client.get_file_search_tool(vector_store_ids=[vs])
```

The standalone classes were replaced by factory methods on `FoundryChatClient` (and other chat clients). Factories ensure the tool is correctly registered with the hosting runtime.

See [`tools-hosted.md`](../api-reference/1.8.0/tools-hosted.md).

---

## 1.0 GA: Exception hierarchy reorganization

**Removed:**
- `ServiceResponseException`
- Some `*Error` aliases

**Added (replacement):**
```
AgentFrameworkException
├── ChatClientException
│   ├── ChatClientInvalidResponseException
│   └── ChatClientRateLimitException
├── AgentException
│   ├── AgentInvalidResponseException
│   └── AgentExecutionException
├── ToolException
│   ├── ToolExecutionException
│   └── ToolDescriptionException
└── WorkflowException
```

**Migration:**
```python
# WRONG (pre-1.0)
except ServiceResponseException as ex: ...

# CORRECT (1.0+)
except ChatClientInvalidResponseException as ex: ...
```

See [`exceptions.md`](../api-reference/1.8.0/exceptions.md) and [`../patterns/error-handling.md`](../patterns/error-handling.md).

---

## 1.0 GA: Plain functions replace `FunctionTool`

**Before:**
```python
from agent_framework.tools import FunctionTool
weather_tool = FunctionTool(name="get_weather", description="...", function=get_weather)
```

**After (1.0+):**
```python
from typing import Annotated

def get_weather(city: Annotated[str, "City name"]) -> str:
    """Return weather for a city."""
    return ...

# Pass the bare function:
async with client.as_agent(..., tools=[get_weather]) as agent: ...
```

The framework uses type hints + docstring to generate the schema automatically. No wrapper class needed.

See [`tools-function.md`](../api-reference/1.8.0/tools-function.md).

---

## 1.3.0: Foundry Toolbox API change

**Before:**
```python
from agent_framework.tools import select_toolbox_tools
toolbox = select_toolbox_tools(client, toolbox_name="x", tools=["a", "b"])
```

**After (1.3+):**
```python
from agent_framework import MCPStreamableHTTPTool
toolbox = MCPStreamableHTTPTool(
    name="x",
    url="https://<project-endpoint>/toolboxes/x/mcp",
)
# Toolbox is exposed atomically; you can't pre-select tools.
```

See [`../patterns/foundry-toolbox-mcp-http.md`](../patterns/foundry-toolbox-mcp-http.md).

---

## 1.4.0: DevUI default tightening (PR #5740)

`agent-framework-devui` `serve()` defaults changed:

| Param | Pre-1.4 default | 1.4+ default |
|-------|----------------|--------------|
| `host` | `'0.0.0.0'` (any) | `'127.0.0.1'` (loopback only) |
| `auth_enabled` | `False` | `True` |
| `cors_origins` | `['*']` | `[]` |

**Migration for workshop use (Codespaces port-forward, classroom):**

```python
serve(
    entities=[agent],
    host="0.0.0.0",
    auth_enabled=False,
    cors_origins=["*"],
)
```

**Migration for production:** the new defaults are correct — no change needed. See [`../anti-patterns/devui-production-defaults.md`](../anti-patterns/devui-production-defaults.md).

---

## 1.5.0: Streaming unification

**Before:**
```python
async for chunk in agent.run_stream("hi"): ...
async for event in workflow.run_stream("hi"): ...
```

**After (1.5+):**
```python
async for chunk in agent.run("hi", stream=True): ...
async for event in workflow.run("hi", stream=True): ...
```

`run_stream()` methods removed entirely. See [`../patterns/streaming-output.md`](../patterns/streaming-output.md).

---

## 1.5.0: `WorkflowBuilder` API change

**Before:**
```python
wb = WorkflowBuilder()
wb.register_agent(a)
wb.register_agent(b)
wb.set_start_executor(a)
wb.add_edge(a, b)
wf = wb.build()
```

**After (modern 1.6.0):**
```python
wf = (
    WorkflowBuilder(start_executor=a, output_from=[b])
    .add_edge(a, b)
    .build()
)
```

`register_agent` and `set_start_executor` were removed. In 1.6.0, use constructor-only `start_executor=` plus explicit `output_from=`.

See [`../patterns/multi-agent-workflow.md`](../patterns/multi-agent-workflow.md).

---

## 1.5.0: Workflow event unification

**Before:**
```python
from agent_framework.workflows import (
    ExecutorCompletedEvent, WorkflowOutputEvent, WorkflowFailedEvent,
)
async for event in wf.run("hi"):
    if isinstance(event, ExecutorCompletedEvent): ...
    elif isinstance(event, WorkflowOutputEvent): ...
```

**After (1.5+):**
```python
async for event in wf.run("hi", stream=True):
    t = event.type    # Literal["intermediate", "data", "executor_invoked", ...]
    if t == "executor_completed": ...
    elif t == "output": ...
    elif t == "failed": ...
```

The discriminator classes were removed. See [`../anti-patterns/workflow-event-isinstance.md`](../anti-patterns/workflow-event-isinstance.md).

---

## 1.6.0: Instrumentation + dep changes

Covered separately in [`from-1.5-to-1.6.md`](from-1.5-to-1.6.md).

Summary:
- Instrumentation default = ON.
- `opentelemetry-sdk` removed from hard deps.
- New experimental factories (a2a, browser, computer use, fabric, memory search, sharepoint, shell, bing custom search).

---

## 1.7.0: Declarative breakers + experimental harness/background/prompt-agent

Covered in detail in [`from-1.6-to-1.7.md`](from-1.6-to-1.7.md).

Summary:
- **Declarative beta breaking changes (PR #6126)** — `AppendValue`, `EmitEvent`, `Confirmation`, `WaitForInput` removed; `Switch` → `ConditionGroup`; `Goto` → `GotoAction`. Affects users of `agent-framework-declarative` beta; stable `agent-framework-foundry==1.8.0` callers unaffected unless they consume declarative YAML/JSON.
- **Provider tool-name renames (silent breakers)** — `TodoProvider` (PR #6107): `add_todos`→`todos_add`, `remove_todos`→`todos_remove`, etc. (5 renames). `AgentModeProvider` (PR #6071): `set_mode`→`mode_set`, `get_mode`→`mode_get`. Hosted-tool allow-lists / eval rubrics / audit logs referencing old names need updates.
- **NEW experimental APIs**:
  - `create_harness_agent(...)` + `DEFAULT_HARNESS_INSTRUCTIONS` (PR #6041) — see [`../patterns/harness-agent.md`](../patterns/harness-agent.md).
  - `BackgroundAgentsProvider` for non-blocking fan-out (PR #6069) — see [`../patterns/background-agents.md`](../patterns/background-agents.md).
  - `to_prompt_agent(agent)` Foundry helper (PR #5959) — see [`../patterns/foundry-prompt-agent.md`](../patterns/foundry-prompt-agent.md).
- **NEW stable additive**: `ContextWindowCompactionStrategy` joins the 6 existing compaction strategies (PR #6041) — see [`../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy`](../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy).
- **Bug fixes**: Foundry `default_headers` propagation (PR #6040); `@experimental` warning attribution (PR #5996); `Foreach` exit-edge wiring (PR #6050); DevUI streaming memory growth (PR #6038).
- **Dependencies**: floor bumps only (`agent-framework-core>=1.7.0`, `agent-framework-openai>=1.7.0`); no new transitive deps for core/foundry.

---

## Full validation script (run after any major upgrade)

```bash
# 1. Clean install
pip install --upgrade --force-reinstall agent-framework-foundry==1.8.0

# 2. Compile-check all your code
python3 -m compileall -q src/ templates/

# 3. Scan for removed APIs (Python symbols)
rg "HostedWebSearchTool|HostedCodeInterpreterTool|HostedFileSearchTool|run_stream\(|register_agent\(|set_start_executor\(|select_toolbox_tools|ServiceResponseException|ExecutorCompletedEvent|WorkflowOutputEvent|FunctionTool|AppendValue|EmitEvent|\bConfirmation\b|WaitForInput" --type py

# 3b. Audit callers for renamed provider tool names (1.7.0 silent breakers — these are tool-name strings, not symbols)
rg "\"add_todos\"|\"remove_todos\"|\"update_todos\"|\"list_todos\"|\"clear_todos\"|\"set_mode\"|\"get_mode\"" --type py

# 4. Verify the canonical pattern still works
python -c "
import asyncio
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async def smoke():
    async with AzureCliCredential() as cred:
        client = FoundryChatClient(project_endpoint='https://...', model='gpt-5-4', credential=cred)
        async with client.as_agent(name='smoke', instructions='Reply OK.') as agent:
            result = await agent.run('Say OK.')
            print(result.text)

asyncio.run(smoke())
"
```

If step 3 returns hits, migrate using the relevant section above.

## See also

- [`from-1.6-to-1.7.md`](from-1.6-to-1.7.md) — latest delta in detail
- [`from-1.5-to-1.6.md`](from-1.5-to-1.6.md) — prior delta (historical)
- [`../anti-patterns/removed-apis-since-1.0.md`](../anti-patterns/removed-apis-since-1.0.md) — quick removed-API cheat sheet
- [Microsoft Agent Framework releases](https://github.com/microsoft/agent-framework/releases)
