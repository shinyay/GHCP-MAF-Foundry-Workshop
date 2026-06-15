# Workflow Internals: Runner, State, Edges, Validation, Viz

> Status: **Stable** (internal subsystem reference)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) (commit `950673b`)
> Source dive: `python/packages/core/agent_framework/_workflows/`

This page documents the **runtime model** of `Workflow` — the Pregel-style superstep loop, the `State` two-phase commit, the edge-group dispatchers, and the visualizer. Use it when you need to reason about ordering, recovery, or concurrency — not for everyday workflow authoring (start with [`workflows.md`](workflows.md)).

> [!NOTE]
> This page describes the **runtime semantics** that hold across all `Workflow` instances. Most of the symbols on this page (`Runner`, `State`, edge groups, `validate_workflow_graph`, `WorkflowViz`) are publicly re-exported from `agent_framework`, but typical user code only touches `WorkflowBuilder` and `Workflow.run(...)`.

---

## The Pregel superstep model

`Runner` ([`_runner.py:L30-L120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_runner.py#L30-L120)) is exactly what its docstring claims: *"A class to run a workflow in Pregel supersteps."*

### Phase order

1. **Superstep 0 (pre-loop)** — when `workflow.run(message, ...)` is called with an initial message, the start executor processes that message **outside** the main loop. The first checkpoint (if `checkpoint_storage` is configured) is created at the end of superstep 0 ([`_runner.py:L92-L97`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_runner.py#L92-L97)).
2. **Superstep N (`N ≥ 1`)** — every executor with pending messages runs concurrently. Each executor emits zero or more `send_message` (downstream messages, queued for superstep N+1) and `yield_output` calls (data-plane events).
3. **Event yielding** — the runner runs each iteration as an `asyncio.Task` and polls `_ctx.next_event()` with a 50 ms timeout so events stream *during* the superstep rather than only at boundaries ([`_runner.py:L99-L120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_runner.py#L99-L120)).
4. **Convergence** — when no executor has pending messages at the start of a superstep, the loop exits and the workflow becomes `IDLE`.
5. **Bound** — `max_iterations` (default `100`, defined as `DEFAULT_MAX_ITERATIONS` in [`_const.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_const.py)) caps the loop; exceeding it raises `WorkflowConvergenceException`.

### Boundary events

- `superstep_started` (with `event.iteration`) is emitted at the top of every iteration.
- `superstep_completed` is emitted at the bottom.

These are how clients track progress without inspecting individual executor messages.

---

## `State` and the two-phase commit

[`_state.py:L1-L127`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_state.py)

`State` is workflow-scoped key/value storage shared across executors. Its core property is **superstep atomicity**: writes during a superstep do not become visible to other executors until the superstep ends.

| Method | Effect |
|--------|--------|
| `state.set(key, value)` | Writes to `_pending` (visible only to the writing executor). |
| `state.get(key)` | Reads committed value (or pending if same executor). |
| `state.has(key)` / `state.delete(key)` / `state.clear()` | Pending-aware operations. |
| `state.commit()` | Flushes `_pending` into committed state. Framework calls this at superstep boundaries. |
| `state.discard()` | Rolls back `_pending`. Framework calls this on superstep failure. |
| `state.export_state()` / `state.import_state(...)` | Used by checkpointing to serialize/restore. |

> [!IMPORTANT]
> Keys with an underscore prefix (e.g., `_executor_state`) are **reserved for the framework**. Do not write to them from user code.

The `_DeleteSentinel` pattern ([`_state.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_state.py)) lets `delete()` participate in the same two-phase commit as `set()`.

---

## Edge groups

All edge-building methods on `WorkflowBuilder` create one of these `EdgeGroup` subclasses ([`_edge.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_edge.py)), each with a matching `EdgeRunner` ([`_edge_runner.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_edge_runner.py)) that knows how to deliver messages.

| Class | Builder method | Semantics |
|-------|---------------|-----------|
| `SingleEdgeGroup` | `add_edge` | One source → one target, optional `EdgeCondition`. |
| `FanOutEdgeGroup` | `add_fan_out_edges` | One source → many targets; optional `selection_func(data) -> list[str]`. |
| `FanInEdgeGroup` | `add_fan_in_edges` | Many sources → one target. Target handler receives an aggregated `list`. |
| `SwitchCaseEdgeGroup` | `add_switch_case_edge_group` | Mutually-exclusive routing using `Case(condition=..., target=...)` plus an optional `Default(target=...)`. |
| `InternalEdgeGroup` | (framework-internal) | Routes framework-emitted messages (e.g., orchestration internals). |

### `EdgeCondition` signature

[`_edge.py:L19-L22`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_edge.py#L19-L22):

```python
EdgeCondition: TypeAlias = Callable[[Any], bool | Awaitable[bool]]
```

Conditions can be sync or async. The serialized graph stores only the function's `__name__` ([`_edge.py:L27-L72`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_edge.py#L27-L72)); cross-process restore swaps in a `_missing_callable` shim that fails loudly when invoked.

---

## Validation

`validate_workflow_graph(edge_groups, executors, start_executor, output_ids, intermediate_ids)` ([`_validation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_validation.py)) is called from `WorkflowBuilder.build()` ([`_workflow_builder.py:L850-L856`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L850-L856)).

Failure modes raise `WorkflowValidationError` subclasses:

- **`EdgeDuplicationError`** — the same `(source, target, condition_name)` appears twice.
- **Type-compatibility errors** — a source declares `WorkflowContext[X]` and the downstream handler can't accept `X`.
- **Graph-connectivity errors** — orphaned executors (referenced in no edge group), unreachable nodes, or output-designated executors missing from the graph.

The `ValidationTypeEnum` discriminates failure category (graph / type / output).

---

## `WorkflowRunResult` (recap)

`list[WorkflowEvent]` subclass at [`_workflow.py:L101-L165`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L101-L165). The list itself contains data-plane events (`output`, `intermediate`, `request_info`, `executor_*`). The control plane is held separately in `_status_events` and surfaced through `status_timeline()` and `get_final_state()`.

> [!WARNING]
> `get_final_state()` raises `RuntimeError("Final state is unknown because no status event was emitted")` if you ran the workflow in a way that produced no status events. The default entry points always emit them, so this only fires in custom-runner scenarios.

---

## Workflow serialization

`Workflow.to_dict()` / `Workflow.to_json()` ([`_workflow.py:L373-L411`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L373-L411)) produce a JSON-ready definition: `name`, `id`, `start_executor_id`, `max_iterations`, `edge_groups` (each `EdgeGroup` is `DictConvertible`), `executors` (recursively, including nested `WorkflowExecutor.workflow`), `output_executors`, `intermediate_executors`, and optional `description`.

This is used by:
- OpenTelemetry spans (the full `to_json()` is attached as `OtelAttr.WORKFLOW_DEFINITION`).
- DevUI rendering.
- Checkpoint signature comparison via `Workflow.graph_signature` / `graph_signature_hash`.

---

## Visualizer (`WorkflowViz`)

[`_viz.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_viz.py) provides Mermaid and DOT renderings:

```python
from agent_framework import WorkflowViz

viz = WorkflowViz(workflow)
print(viz.to_mermaid())
viz.to_dot()        # Graphviz DOT
viz.export(format="svg")
```

DevUI uses this under the hood. The output is purely structural (executors as nodes, edge groups as edges) — runtime state is not depicted.

---

## Accessors on the built `Workflow`

[`_workflow.py:L413-L450`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L413-L450):

| Accessor | Notes |
|---------|-------|
| `workflow.get_start_executor()` | The wrapped start executor instance. |
| `workflow.get_output_executors()` | Designated outputs; in omitted-selection mode returns *all* executors. |
| `workflow.get_intermediate_executors()` | Designated intermediates only. |
| `workflow.is_terminal_executor(executor_id)` | `True` if that executor's yields are labeled `type="output"`. |
| `workflow.id` | Per-instance UUID (not stable across re-builds — use `workflow.name` for that). |
| `workflow.graph_signature` / `graph_signature_hash` | Used to validate checkpoint compatibility. |

---

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Mutating shared `state` from inside a handler and expecting *peer* executors in the same superstep to see it | Two-phase commit hides pending writes until the boundary. Design for one-superstep latency or use explicit messages. |
| Calling `workflow.run(...)` a second time concurrently from the same `Workflow` instance | `Workflow._ensure_not_running` raises `RuntimeError("Workflow is already running…")`. Build separate instances or `await` the first call. |
| `max_iterations` set too low for a loop or HITL pattern | `WorkflowConvergenceException`. Raise the limit or refactor to use checkpoints + responses. |
| Writing to underscore-prefix state keys | Reserved for the framework (e.g., `_executor_state`). Conflicts with checkpointing. |
| Calling `workflow.to_json()` on a workflow containing non-serializable callable edge conditions across processes | Conditions persist by `__name__` only; the loading side gets a `_missing_callable` shim that raises on invocation. Restore the original callable on the loader side. |

---

## See also

- [`workflows.md`](workflows.md) — the developer-facing builder + run API
- [`../../patterns/workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) — durable resume across processes
- [`../../patterns/workflow-as-agent-nesting.md`](../../patterns/workflow-as-agent-nesting.md) — `workflow.as_agent()` and `WorkflowExecutor`
- [`declarative.md`](declarative.md) — ⚠️ BETA — `WorkflowFactory` compiles YAML into this **same** `Workflow` / `Runner` graph via internal `DeclarativeWorkflowBuilder` (one `ActionExecutor` per action `kind:`). Anything documented here applies to declaratively-loaded workflows too.
- [`exceptions.md`](exceptions.md) — `WorkflowException` hierarchy
