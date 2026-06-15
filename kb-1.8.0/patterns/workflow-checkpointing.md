# Pattern: Workflow Checkpointing

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_workflows/_checkpoint.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py), [`_workflow.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py)

## Goal

Persist a workflow's full execution state so a long-running or human-in-the-loop workflow can be **paused, durably stored, and resumed later** — including across process restarts.

## When to use

- **Human-in-the-loop**: a workflow emits `request_info` events and the caller may take hours/days to respond.
- **Long-running pipelines**: you want to survive a crash without re-running expensive earlier executors.
- **Multi-tenant scheduling**: a worker can pick up any pending checkpoint from shared storage.

If the workflow always completes within one `await workflow.run(...)` invocation in the same process, you do not need checkpointing.

## Core types

All four are top-level exports of `agent_framework` ([`__init__.py:L219-L223`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/__init__.py#L219-L223)).

| Symbol | Role |
|--------|------|
| `CheckpointStorage` | `Protocol` ([`_checkpoint.py:L119-L189`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L119-L189)). Six async methods: `save`, `load`, `list_checkpoints`, `delete`, `get_latest`, `list_checkpoint_ids`. |
| `InMemoryCheckpointStorage` | Concrete in-process backend for tests and DevUI ([`_checkpoint.py:L192-L236`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L192-L236)). |
| `FileCheckpointStorage` | Concrete file-backed backend ([`_checkpoint.py:L239-L280`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L239-L280)). Uses JSON + base64-encoded pickle for complex Python objects. Configurable allow-list of additional deserialization types. |
| `WorkflowCheckpoint` | `@dataclass` value type with `workflow_name`, `graph_signature_hash`, `checkpoint_id`, `previous_checkpoint_id`, `timestamp`, `messages`, `state`, `pending_request_info_events`, `iteration_count`, `metadata`, `version` ([`_checkpoint.py:L30-L88`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L30-L88)). |

> [!IMPORTANT]
> A checkpoint is **not tied to a specific `Workflow` instance** — only to a workflow *definition*, identified by `workflow_name` and `graph_signature_hash` ([`_checkpoint.py:L37-L42`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L37-L42)). You can rebuild the same workflow in a fresh process and resume the checkpoint.

## Code — pause and resume

```python
from agent_framework import (
    FileCheckpointStorage,
    WorkflowBuilder,
)

storage = FileCheckpointStorage("/var/lib/myapp/checkpoints")

# Build the workflow with a name — checkpoints are keyed on it.
workflow = (
    WorkflowBuilder(
        name="event_planning_v1",      # MUST match across runs to resume
        start_executor=coordinator,
        checkpoint_storage=storage,
        output_from=[booking],
    )
    .add_chain([coordinator, venue, catering, budget, booking])
    .build()
)

# Initial run — checkpoint is written after each superstep.
result = await workflow.run("Plan a 50-person event in Seattle.")
print(result.get_final_state())          # likely IDLE_WITH_PENDING_REQUESTS

# Persist the request_id externally so the caller can satisfy it later
pending = result.get_request_info_events()
for evt in pending:
    save_to_my_queue(evt.request_id, evt.data)
```

**Later, in any process** (possibly after a restart):

```python
# Rebuild the workflow with the SAME name so signatures match.
workflow = (
    WorkflowBuilder(name="event_planning_v1", start_executor=coordinator, output_from=[booking])
    .add_chain([coordinator, venue, catering, budget, booking])
    .build()
)

latest = await storage.get_latest(workflow_name="event_planning_v1")

result = await workflow.run(
    checkpoint_id=latest.checkpoint_id,
    checkpoint_storage=storage,          # required to write new checkpoints
    responses={
        "<request_id_1>": "Seattle Convention Center confirmed.",
        "<request_id_2>": "Vegan catering confirmed.",
    },
)
print(result.get_outputs())
```

## Why each piece

- **`checkpoint_storage` on the builder** seeds `InProcRunnerContext` ([`_workflow_builder.py:L861`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L861)). This is the *default* storage for both initial saves and resumes.
- **`checkpoint_storage` on `workflow.run(...)`** is a **runtime override** — if you want to redirect saves at run-time (e.g., a per-request DB shard) you can pass it again on `run()` ([`_workflow.py:L767-L769`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L767-L769)).
- **`checkpoint_id=...`** resumes from a specific checkpoint. Combine with `responses={request_id: data, ...}` to deliver answers to pending `request_info` events.
- **`message` is mutually exclusive with `checkpoint_id` and `responses`** ([`_workflow.py:L727-L728`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L727-L728)).

### What gets saved

`WorkflowCheckpoint.state` holds **only committed** state (`_pending` writes are dropped — see [`_state.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_state.py)). Per-executor state is stored under the reserved key `_executor_state`.

For custom executors that need to participate in checkpointing, override:

```python
class MyExecutor(Executor):
    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {"my_counter": self._counter}

    async def on_checkpoint_restore(self, data: dict[str, Any]) -> None:
        self._counter = data.get("my_counter", 0)
```

(Verified at [`_workflows/_executor.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_executor.py) — see `Executor` docstring sections on "State Management".)

## `FileCheckpointStorage` security note

By default, `FileCheckpointStorage` only deserializes a built-in safe set of types: primitives, `datetime`, `uuid`, all `agent_framework` internal types, and `openai.types` ([`_checkpoint.py:L247-L260`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_checkpoint.py#L247-L260)). To round-trip your own types, allow-list them:

```python
storage = FileCheckpointStorage(
    "/tmp/checkpoints",
    allowed_checkpoint_types=[
        "my_app.models:Booking",
        "my_app.models:Itinerary",
    ],
)
```

> [!WARNING]
> Never allow-list types from untrusted modules. Pickle deserialization is the standard arbitrary-code-execution vector.

## Production backends

`InMemoryCheckpointStorage` and `FileCheckpointStorage` are first-party, but neither is suitable for **multi-replica production** (in-memory loses on restart; file requires a shared filesystem). For production, prefer:

| Backend | Class | Package | Suitable for |
|---------|-------|---------|--------------|
| **Azure Cosmos DB** | `CosmosCheckpointStorage` | `agent-framework-azure-cosmos` | Multi-region durability, managed identity, audit retention. Partition key `/workflow_name`. See [`../api-reference/1.8.0/packages.md`](../api-reference/1.8.0/packages.md#persistence--memory-packages--capability-matrix). |
| Custom DB (Postgres / DynamoDB / etc.) | Implement `CheckpointStorage` Protocol | — | When you must use an existing operational data store. |

Example — switching `FileCheckpointStorage` for `CosmosCheckpointStorage` is a one-line change:

```python
from agent_framework_azure_cosmos import CosmosCheckpointStorage
from azure.identity.aio import DefaultAzureCredential

async with DefaultAzureCredential() as cred:
    storage = CosmosCheckpointStorage(
        endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
        database_name="workflows",
        container_name="checkpoints",
        credential=cred,
        # Optional: allow custom types into the pickle deserialization allow-list
        allowed_checkpoint_types=["my_app.models:Booking"],
    )

    workflow = (
        WorkflowBuilder(
            name="event_planning_v1",
            start_executor=coordinator,
            checkpoint_storage=storage,
            output_from=[booking],
        )
        .add_chain([coordinator, venue, catering, budget, booking])
        .build()
    )
```

> [!IMPORTANT]
> `CosmosCheckpointStorage` requires the runtime identity to have the **data plane** role `Cosmos DB Built-in Data Contributor` (id `00000000-0000-0000-0000-000000000002`). The container partition key must be `/workflow_name`.

The `allowed_checkpoint_types` allow-list works identically to `FileCheckpointStorage` — same safety rules apply.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Rebuilding the workflow with a different topology (extra/missing edges) but the same `name` and trying to resume | Checkpoint restore checks `graph_signature_hash` and raises if it differs. Bump the workflow name (`event_planning_v2`) when topology changes. |
| Forgetting `name=` on the builder | Defaults to `None`, which means checkpoints can't be looked up by name. Always set `name=` when checkpointing. |
| Passing `message=` together with `checkpoint_id=` or `responses=` | Raises `ValueError`. Pick one entry mode per `run()` call. |
| Using `InMemoryCheckpointStorage` in production | It dies with the process. Use `FileCheckpointStorage` or a custom `CheckpointStorage` implementation against a real DB. |
| Reading `cp.state` and finding only partial data mid-superstep | Checkpoints are written **at superstep boundaries** ([`_runner.py:L92-L97`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_runner.py#L92-L97)) — intra-superstep `_pending` writes never appear. By design. |

## Verification

```python
# Quick smoke: round-trip a checkpoint in-memory.
from agent_framework import InMemoryCheckpointStorage, WorkflowBuilder

storage = InMemoryCheckpointStorage()
wf = WorkflowBuilder(name="smoke", start_executor=my_exec, checkpoint_storage=storage).build()

r1 = await wf.run("hello")
ids = await storage.list_checkpoint_ids(workflow_name="smoke")
assert ids, "no checkpoints written"

latest = await storage.get_latest(workflow_name="smoke")
assert latest.workflow_name == "smoke"
assert latest.graph_signature_hash == wf.graph_signature_hash
```

## See also

- [`../api-reference/1.8.0/workflow-internals.md`](../api-reference/1.8.0/workflow-internals.md) — superstep semantics + State commit boundaries
- [`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md) — `run()` parameter rules
- [`../api-reference/1.8.0/packages.md`](../api-reference/1.8.0/packages.md#persistence--memory-packages--capability-matrix) — persistence package matrix (Cosmos checkpoint backend)
- [`workflow-as-agent-nesting.md`](workflow-as-agent-nesting.md) — checkpoints inside nested workflows
- [`../anti-patterns/workflow-event-isinstance.md`](../anti-patterns/workflow-event-isinstance.md)
- [`../anti-patterns/using-the-wrong-memory-primitive.md`](../anti-patterns/using-the-wrong-memory-primitive.md) — `CheckpointStorage` vs `HistoryProvider`
