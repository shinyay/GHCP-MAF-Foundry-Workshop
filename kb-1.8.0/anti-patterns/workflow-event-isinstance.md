# Anti-Pattern: Discriminating Workflow Events with `isinstance` (and fabricated attributes)

> Status: **Active hazard** for code originally written against 1.4 or earlier
> Affects: 1.5.0+ (the unification PR)
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_workflows/_events.py:L102-L143`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L102-L143)
> Severity: **High** — silent fall-through; your handler never matches anything

## Symptom

You upgraded from 1.4 to 1.5 or 1.6, and now your workflow event loop **never enters any branch**, or you get an `ImportError` for an event class:

```python
async for event in wf.run("hi", stream=True):
    if isinstance(event, ExecutorCompletedEvent):     # ← always False
        print("done")
    elif isinstance(event, WorkflowOutputEvent):
        final = event.output                          # ← AttributeError if it ever fired
```

Or:
```
ImportError: cannot import name 'ExecutorCompletedEvent' from 'agent_framework'
```

## Why it's wrong

Before 1.5.0, each event kind was a separate class (`ExecutorCompletedEvent`, `WorkflowOutputEvent`, `WorkflowFailedEvent`, …) and you discriminated with `isinstance`.

In 1.5.0+, all events were **unified into a single generic `WorkflowEvent[DataT]` class** with a `type: Literal[...]` discriminator. The old classes were **removed** (not just deprecated — gone). Verified at [`_events.py:L146-L168`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L146-L168).

Common follow-on mistakes:
- `event.output` — does not exist; payloads live on `event.data`.
- `event.error` — does not exist; error info lives on `event.details: WorkflowErrorDetails`.
- `event.content` — does not exist anywhere on `WorkflowEvent`.

## Wrong code

```python
from agent_framework import (        # ← these symbols are GONE
    ExecutorCompletedEvent,
    WorkflowOutputEvent,
    WorkflowFailedEvent,
    WorkflowIntermediateEvent,
)

async for event in wf.run("hi", stream=True):
    if isinstance(event, ExecutorCompletedEvent):
        print(f"{event.executor_id} done -> {event.output}")    # ← .output doesn't exist
    elif isinstance(event, WorkflowOutputEvent):
        print(f"final: {event.output}")                          # ← .output doesn't exist
    elif isinstance(event, WorkflowFailedEvent):
        raise event.error                                        # ← .error doesn't exist
```

## Correct code (1.5+ / 1.7 canonical)

```python
async for event in wf.run("hi", stream=True):
    t = event.type
    if t == "intermediate":
        print(event.data, end="", flush=True)
    elif t == "data":
        # deprecated alias still emitted by some 1.5 servers — treat same as intermediate
        print(event.data, end="", flush=True)
    elif t == "executor_completed":
        print(f"\n[{event.executor_id} done] -> {event.data}")
    elif t == "executor_failed":
        d = event.details                      # WorkflowErrorDetails
        print(f"[!] {event.executor_id} {d.error_type}: {d.message}")
    elif t == "output":
        final = event.data
    elif t == "failed":
        d = event.details
        raise RuntimeError(f"Workflow failed: {d.error_type}: {d.message}")
    elif t == "request_info":
        print(f"[HITL] request_id={event.request_id} from {event.source_executor_id}")
    elif t == "status":
        print(f"[state] {event.state}")        # WorkflowRunState
    else:
        # Forward-compat: don't silently swallow unknown event types.
        print(f"[unknown event type: {t}]", flush=True)
```

## Authoritative attribute reference (1.8.0)

From [`_events.py:L102-L130`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L102-L130). **There are 18 event types, not 7** — the Pass-1 KB undercounted.

| `event.type` | Use these attributes |
|--------------|---------------------|
| `"started"` | `event.data is None` |
| `"status"` | `event.state: WorkflowRunState` |
| `"failed"` | `event.details: WorkflowErrorDetails` |
| `"output"` | `event.executor_id`, `event.data` |
| `"intermediate"` | `event.executor_id`, `event.data` |
| `"data"` | **DEPRECATED** alias for `"intermediate"`; same attributes |
| `"request_info"` | `event.request_id`, `event.source_executor_id` |
| `"warning"` | `event.data: str` |
| `"error"` | `event.data: Exception` |
| `"superstep_started"` | `event.iteration: int` |
| `"superstep_completed"` | `event.iteration: int` |
| `"executor_invoked"` | `event.executor_id`, `event.data` |
| `"executor_completed"` | `event.executor_id`, `event.data` |
| `"executor_failed"` | `event.executor_id`, `event.details: WorkflowErrorDetails` |
| `"executor_bypassed"` | `event.executor_id`, `event.data` |
| `"group_chat"` | `event.data: GroupChatRequestSentEvent \| GroupChatResponseReceivedEvent` |
| `"handoff_sent"` | `event.data: HandoffSentEvent` |
| `"magentic_orchestrator"` | `event.data: MagenticOrchestratorEvent` |

Every event also has `event.origin: WorkflowEventSource` (`FRAMEWORK` or `EXECUTOR`) — see [`_events.py:L26-L35`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L26-L35).

> [!IMPORTANT]
> Use `event.data` for typed payloads and `event.details: WorkflowErrorDetails` (with `.error_type`, `.message`, `.traceback`, `.executor_id`, `.extra`) for error info. **There is no `.output`, `.error`, or `.content` attribute** on `WorkflowEvent`.

## Bonus anti-pattern — `WorkflowEvent.emit(...)` is deprecated

The free-form `WorkflowEvent.emit(...)` factory is deprecated in 1.6.0 ([`_events.py:L281-L294`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L281-L294)). Use the typed factories (`WorkflowEvent.started()`, `WorkflowEvent.status(state)`, `WorkflowEvent.failed(details)`, `WorkflowEvent.warning(...)`, `WorkflowEvent.error(...)`, `WorkflowEvent.request_info(...)`, `WorkflowEvent.superstep_*`, `WorkflowEvent.executor_*`) instead. Custom executors should normally let the framework emit lifecycle events and only call `ctx.yield_output(...)` for data.

## Why the unification?

Single class = easier to:
- Add event types in minor versions without breaking imports
- Serialize/deserialize across process boundaries (one schema)
- Subclass for custom workflow engines

The `Generic[DataT]` parameter lets callers narrow payload types where useful.

## How to detect

```bash
# Find code that imports the removed classes:
rg "(Executor(Completed|Invoked|Failed|Bypassed)|Workflow(Output|Failed|Intermediate|Started|Status))Event" --type py

# Find isinstance checks against workflow events:
rg "isinstance\(\s*\w+\s*,\s*(Executor|Workflow)\w*Event" --type py

# Find fabricated attribute access on events:
rg "event\.(output|error|content)\b" --type py
```

Each hit needs migration to `event.type == "..."` plus the correct attribute from the table above.

## See also

- [`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md) — full event-type table with citations
- [`../api-reference/1.8.0/workflow-internals.md`](../api-reference/1.8.0/workflow-internals.md) — Pregel supersteps and the `Runner`
- [`../patterns/multi-agent-workflow.md`](../patterns/multi-agent-workflow.md)
- [`../patterns/streaming-output.md`](../patterns/streaming-output.md)
- [`removed-apis-since-1.0.md`](removed-apis-since-1.0.md)
- [`../migration-guides/from-1.5-to-1.6.md`](../migration-guides/from-1.5-to-1.6.md)
