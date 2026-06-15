# Anti-Pattern: Using APIs Removed Since 1.0 GA

> Status: **Active hazard** (especially for code copy-pasted from old docs / blog posts)
> Affects: any code originally written against pre-1.0 betas or 1.0-1.4 versions
> Severity: **High** — `ImportError` or `AttributeError` at module load

## Symptom

```
ImportError: cannot import name 'HostedWebSearchTool' from 'agent_framework'
AttributeError: 'Agent' object has no attribute 'run_stream'
AttributeError: 'WorkflowBuilder' object has no attribute 'register_agent'
ImportError: cannot import name 'ServiceResponseException' from 'agent_framework.exceptions'
```

## Why it's wrong

The 1.0 GA → 1.8.0 path removed many APIs that survived through the betas. Online docs / blog posts written before mid-2026 often reference them. Always check the **removed APIs** table before copying code from external sources.

## Removed APIs cheat-sheet

| Removed (year of removal) | Use instead | Reason |
|---------------------------|-------------|--------|
| `HostedWebSearchTool` (1.0 GA) | `client.get_web_search_tool(...)` or `client.get_bing_grounding_tool(...)` | Hosted tools became factory methods |
| `HostedCodeInterpreterTool` (1.0 GA) | `client.get_code_interpreter_tool(...)` | Same |
| `HostedFileSearchTool` (1.0 GA) | `client.get_file_search_tool(vector_store_ids=[...])` | Same |
| `Agent.run_stream(...)` (1.5.0) | `Agent.run(..., stream=True)` | Unified streaming on one method |
| `Workflow.run_stream(...)` (1.5.0) | `Workflow.run(..., stream=True)` | Same |
| `WorkflowBuilder.register_agent(...)` (1.5.0) | Constructor: `WorkflowBuilder(start_executor=..., output_from=[...])` | Builder is constructor-driven |
| `WorkflowBuilder.set_start_executor(...)` (1.5.0) | Same as above | Same |
| `select_toolbox_tools(...)` (1.3.0) | Drop the call; `MCPStreamableHTTPTool` exposes whole toolbox | Toolbox is now atomic |
| `ServiceResponseException` (1.0 GA) | `ChatClientInvalidResponseException` or `AgentInvalidResponseException` | New exception hierarchy |
| `ExecutorCompletedEvent`, `WorkflowOutputEvent`, etc. (1.5.0) | `event.type == "executor_completed"` / `"output"` discriminator | Unified `WorkflowEvent` class |
| `agent_framework.ai.chat.ChatHistory` (1.0 GA) | `agent_framework.ChatHistory` (top-level export) | Module reshuffle |
| `agent_framework.tools.FunctionTool` (1.0 GA) | Plain Python function or `@tool` decorator | Implicit tool generation |

> [!NOTE]
> Older migration snippets may mention `output_executors=` as the constructor replacement.
> In 1.8.0, use `output_from=` instead; `output_executors=` is only a deprecated compatibility alias. See [`workflows.md`](../api-reference/1.8.0/workflows.md#workflowbuilder).

## Wrong code → Correct code

### 1. Hosted Bing search

```python
# WRONG (pre-1.0 beta)
from agent_framework import HostedWebSearchTool
bing = HostedWebSearchTool(connection_id=cid)
```

```python
# CORRECT (1.8.0)
bing = client.get_bing_grounding_tool(connection_id=cid)
# OR: see hosted-bing-search.md for the BingGroundingTool variant.
```

### 2. Streaming

```python
# WRONG
async for chunk in agent.run_stream("hello"):
    print(chunk)
```

```python
# CORRECT
async for chunk in agent.run("hello", stream=True):
    print(chunk)
```

### 3. WorkflowBuilder

```python
# WRONG
wb = WorkflowBuilder()
wb.register_agent(researcher).register_agent(writer)
wb.set_start_executor(researcher)
wf = wb.build()
```

```python
# CORRECT
wf = (
    WorkflowBuilder(
        start_executor=researcher,
        output_from=[writer],
    )
    .add_edge(researcher, writer)
    .build()
)
```

### 4. Workflow events

```python
# WRONG (1.4 and earlier)
from agent_framework.workflows import ExecutorCompletedEvent, WorkflowOutputEvent
async for event in wf.run("hi"):
    if isinstance(event, ExecutorCompletedEvent): ...
    elif isinstance(event, WorkflowOutputEvent): ...
```

```python
# CORRECT (1.5+)
async for event in wf.run("hi", stream=True):
    if event.type == "executor_completed": ...
    elif event.type == "output": ...
```

### 5. Exception catching

```python
# WRONG
from agent_framework.exceptions import ServiceResponseException
try:
    await agent.run(...)
except ServiceResponseException:
    ...
```

```python
# CORRECT
from agent_framework.exceptions import ChatClientInvalidResponseException
try:
    await agent.run(...)
except ChatClientInvalidResponseException:
    ...
```

## How to detect

```bash
# Scan your repo for removed APIs:
rg "HostedWebSearchTool|HostedCodeInterpreterTool|HostedFileSearchTool|run_stream\(|register_agent\(|set_start_executor\(|select_toolbox_tools|ServiceResponseException|ExecutorCompletedEvent|WorkflowOutputEvent" --type py
```

Any hit is a removed API. Migrate it using the table above.

## See also

- [`from-1.5-to-1.6.md`](../migration-guides/from-1.5-to-1.6.md)
- [`cumulative-since-1.0.md`](../migration-guides/cumulative-since-1.0.md)
- [`workflow-event-isinstance.md`](workflow-event-isinstance.md)
- [API ref index](../api-reference/1.8.0/index.md)
