# Workflows: `WorkflowBuilder`, `Workflow`, `WorkflowEvent`

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) (commit `950673b`)
> Source dive: `python/packages/core/agent_framework/_workflows/`

A **workflow** chains executors (custom `Executor` subclasses, plain functions, or `Agent` instances) into a directed graph. The runtime drives them with a **Pregel-style superstep loop**, streams events, and surfaces designated outputs to the caller.

The 1.8.0 workflow API has four key pieces:

1. **`WorkflowBuilder`** — declare nodes + edges + output designation, then `.build()`.
2. **`Workflow.run(...)`** — execute, with `stream=True` returning a `ResponseStream[WorkflowEvent, WorkflowRunResult]`.
3. **`WorkflowEvent`** — single unified generic class with an `event.type` `Literal` discriminator (18 types in 1.8.0).
4. **`WorkflowRunResult`** — a `list[WorkflowEvent]` subclass with helpers like `.get_outputs()`, `.get_final_state()`, `.status_timeline()`.

---

## `WorkflowBuilder`

### Constructor

[`_workflow_builder.py:L89-L142`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L89-L142)

```python
WorkflowBuilder(
    max_iterations: int = 100,                       # DEFAULT_MAX_ITERATIONS
    name: str | None = None,
    description: str | None = None,
    *,
    start_executor: Executor | SupportsAgentRun,     # required (kwarg-only)
    checkpoint_storage: CheckpointStorage | None = None,
    output_from: list[Executor | SupportsAgentRun] | Literal["all"] | None = ...,
    intermediate_output_from: (
        list[Executor | SupportsAgentRun] | Literal["all", "all_other"] | None
    ) = ...,
    # Deprecated alias kept for back-compat (emits DeprecationWarning):
    output_executors: list[Executor | SupportsAgentRun] | None = ...,
)
```

> [!IMPORTANT]
> **`output_executors=` is deprecated in 1.6.0.** Use `output_from=` (verified at [`_workflow_builder.py:L141-L142`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L141-L142)).
> `start_executor` is **constructor-only and required**. The older `register_agent()` / `set_start_executor()` methods were removed in 1.0 GA.

### Output-designation modes

The builder supports three modes for labelling executor yields:

| Mode | How to invoke | What `ctx.yield_output(...)` produces |
|------|---------------|---------------------------------------|
| **Omitted (compat)** | Neither `output_from` nor `intermediate_output_from` set | Every yield emits `event.type == "output"`. Issues a `DeprecationWarning` at `.build()`-time — explicit designation will be required in a future version ([`_workflow_builder.py:L815-L823`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L815-L823)). |
| **All terminal** | `output_from="all"` | All output-capable executors yield as `"output"`. |
| **Explicit lists** | `output_from=[exec_a]`, `intermediate_output_from=[exec_b]` (or `"all_other"`) | Listed executors yield `"output"` / `"intermediate"` respectively. Unlisted executor yields are **hidden** from caller-facing events. |

Validation rules ([`_workflow_builder.py:L684-L723`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L684-L723)):
- Explicit mode must include at least one executor across the two lists.
- Same executor cannot appear in both lists.
- No duplicates within either list.

### Edge-building methods

All return `Self` for chaining. Verified in [`_workflow_builder.py:L309-L616`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L309-L616).

| Method | Signature | Use for |
|--------|-----------|---------|
| `.add_edge(source, target, *, condition=None)` | Single edge A → B with optional `EdgeCondition` predicate (sync or async `(data) -> bool`). | Sequential pipeline. |
| `.add_fan_out_edges(source, targets, selection_func=None)` | A → [B, C, …]. Optional `selection_func(data) -> list[str]` picks which subset of targets receives the message. | Parallel branch. |
| `.add_fan_in_edges(sources, target)` | [A, B, …] → C. Target receives a **list** aggregated from all sources (no `mode=` parameter — aggregation is automatic). | Synchronized join. |
| `.add_chain(executors)` | `add_edge` pairwise across the sequence. Cycles are not allowed. | Linear pipeline shorthand. |
| `.add_switch_case_edge_group(source, cases)` | `cases` is a list of `Case(condition=..., target=...)` and an optional terminal `Default(target=...)`. Mutually-exclusive routing. | If/elif/else routing. |
| `.add_multi_selection_edge_group(source, targets, selection_func)` | Like fan-out but the user-provided `selection_func` decides which targets actually fire. | Custom dispatch. |
| `.build()` | Validates the graph and returns an immutable `Workflow`. | Final step. |

### Auto-wrapping agents

Anything passed as a source/target that satisfies `SupportsAgentRun` (e.g., `client.as_agent(...)`) is **auto-wrapped into an `AgentExecutor`** via `_maybe_wrap_agent` ([`_workflow_builder.py:L189-L226`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L189-L226)). The executor id used in events is `resolve_agent_id(agent)`.

### Canonical example

```python
from agent_framework import WorkflowBuilder, Case, Default

workflow = (
    WorkflowBuilder(
        name="Event Planning Workflow",
        description="Plan, scope, and book an event end-to-end.",
        max_iterations=30,
        start_executor=coordinator,
        output_from=[booking],                    # only booking's yield is type='output'
        intermediate_output_from="all_other",     # every other yield is type='intermediate'
    )
    .add_edge(coordinator, venue)
    .add_edge(venue, catering)
    .add_switch_case_edge_group(
        catering,
        [
            Case(condition=lambda d: d.budget > 50000, target=budget_analyst),
            Default(target=booking),
        ],
    )
    .add_edge(budget_analyst, booking)
    .build()
)
```

---

## `Workflow.run(...)`

### Signature

[`_workflow.py:L653-L725`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L653-L725) — there are two `@overload`s plus the implementation:

```python
def run(
    self,
    message: Any | None = None,
    *,
    stream: bool = False,
    responses: Mapping[str, Any] | None = None,
    checkpoint_id: str | None = None,
    checkpoint_storage: CheckpointStorage | None = None,
    include_status_events: bool = False,              # non-streaming only
    function_invocation_kwargs: Mapping[str, Any] | None = None,
    client_kwargs: Mapping[str, Any] | None = None,
) -> ResponseStream[WorkflowEvent, WorkflowRunResult] | Awaitable[WorkflowRunResult]:
```

> [!IMPORTANT]
> - The parameter is named **`message`**, not `input`.
> - `Workflow.run_stream(...)` was **removed in 1.5.0**. Use `workflow.run(..., stream=True)` instead.
> - Returns `ResponseStream[WorkflowEvent, WorkflowRunResult]` when `stream=True` — iterate for events, then call `.get_final_response()` for the `WorkflowRunResult`.
> - Returns `Awaitable[WorkflowRunResult]` when `stream=False` — `await` it directly.

### Mutually-exclusive parameter rules

`_validate_run_params` ([`_workflow.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py)) enforces:

- `message` is **mutually exclusive** with both `checkpoint_id` and `responses`.
- `responses` + `checkpoint_id` **can** be combined (restore checkpoint, then deliver responses to pending `request_info` events).
- A fresh-message run is rejected if any in-flight executor messages remain from a prior run. Recovery requires checkpoint resume ([`_workflow.py:L782-L789`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L782-L789)).

### Non-streaming

```python
result: WorkflowRunResult = await workflow.run("Plan a 50-person event in Seattle.")
for output in result.get_outputs():
    print(output)
```

### Streaming (canonical pattern)

```python
stream = workflow.run("Plan a 50-person event in Seattle.", stream=True)

async for event in stream:
    if event.type == "intermediate":
        print(f"[{event.executor_id}] {event.data}", end="", flush=True)
    elif event.type == "output":
        print(f"\n[FINAL from {event.executor_id}]: {event.data}")
    elif event.type == "request_info":
        print(f"[HITL] request_id={event.request_id} from {event.source_executor_id}")
    elif event.type == "executor_failed":
        print(f"[!] {event.executor_id}: {event.details.error_type}: {event.details.message}")
    elif event.type == "failed":
        print(f"[!] WORKFLOW FAILED: {event.details.error_type}: {event.details.message}")

result: WorkflowRunResult = await stream.get_final_response()
print(f"Final state: {result.get_final_state()}")  # WorkflowRunState
```

---

## `WorkflowRunResult`

`list[WorkflowEvent]` subclass — verified at [`_workflow.py:L101-L165`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L101-L165).

| Method | Returns | Notes |
|--------|---------|-------|
| `result.get_outputs()` | `list[Any]` | All payloads where `event.type == "output"`. |
| `result.get_intermediate_outputs()` | `list[Any]` | All payloads where `event.type == "intermediate"`. |
| `result.get_request_info_events()` | `list[WorkflowEvent]` | All `type == "request_info"` events (pending HITL prompts). |
| `result.get_final_state()` | `WorkflowRunState` | Last status event's `.state`. Raises `RuntimeError` if no status events were emitted. |
| `result.status_timeline()` | `list[WorkflowEvent]` | Control-plane status events only (data-plane events stay in the list itself). |

> [!WARNING]
> There is **no `result.output` scalar attribute** — `get_outputs()` returns a list (could be empty in progress-only / intermediate-only workflows).

---

## `WorkflowEvent` & the 18 event types

[`_events.py:L102-L130`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L102-L130) — `WorkflowEventType` is a `Literal[...]` alias (not an `Enum`), exported as `agent_framework.WorkflowEventType`.

| `event.type` | Fired when | Key fields |
|--------------|-----------|------------|
| `"started"` | Workflow run began | `event.data is None` |
| `"status"` | Run state changed | `event.state: WorkflowRunState` |
| `"failed"` | Workflow terminated with error | `event.details: WorkflowErrorDetails` |
| `"output"` | Designated executor's `ctx.yield_output(...)` | `event.executor_id`, `event.data` |
| `"intermediate"` | Non-terminal `ctx.yield_output(...)` | `event.executor_id`, `event.data` |
| `"data"` | **DEPRECATED alias** for `"intermediate"` | Same as above |
| `"request_info"` | Executor called `ctx.request_info(...)` for HITL | `event.request_id`, `event.source_executor_id` |
| `"warning"` | User code emitted a warning | `event.data: str` |
| `"error"` | User code raised a non-fatal error | `event.data: Exception` |
| `"superstep_started"` | Pregel superstep N began | `event.iteration: int` |
| `"superstep_completed"` | Pregel superstep N finished | `event.iteration: int` |
| `"executor_invoked"` | Executor handler about to run | `event.executor_id`, `event.data` |
| `"executor_completed"` | Executor handler finished | `event.executor_id`, `event.data` |
| `"executor_failed"` | Executor handler raised | `event.executor_id`, `event.details: WorkflowErrorDetails` |
| `"executor_bypassed"` | Executor skipped via cache hit on replay | `event.executor_id`, `event.data` |
| `"group_chat"` | Group-chat orchestration event | `event.data: GroupChatRequestSentEvent \| GroupChatResponseReceivedEvent` |
| `"handoff_sent"` | Handoff routing event | `event.data: HandoffSentEvent` |
| `"magentic_orchestrator"` | Magentic orchestrator event | `event.data: MagenticOrchestratorEvent` |

### Common fields

Every `WorkflowEvent[DataT]` exposes:

| Field | Type | Notes |
|-------|------|-------|
| `event.type` | One of the 18 literals above | Discriminator |
| `event.origin` | `WorkflowEventSource` enum (`FRAMEWORK` / `EXECUTOR`) | Who emitted it. [`_events.py:L26-L35`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L26-L35) |
| `event.data` | `DataT` | Payload, shape varies by type |
| `event.executor_id` | `str \| None` | Set for executor-scoped events |
| `event.details` | `WorkflowErrorDetails \| None` | Set for `failed` / `executor_failed` |

### `WorkflowErrorDetails`

Dataclass at [`_events.py:L70-L99`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L70-L99):

```python
@dataclass
class WorkflowErrorDetails:
    error_type: str           # e.g. "ValueError"
    message: str
    traceback: str | None
    executor_id: str | None   # which executor blew up (None for workflow-level failed)
    extra: dict[str, Any]     # serialization-safe extras
```

> [!IMPORTANT]
> Pass-1 KB referenced `event.error`, `event.output`, `event.content`. **None of those attributes exist** on `WorkflowEvent`. Use `event.data` for payloads and `event.details` for error info. See [`../../anti-patterns/workflow-event-isinstance.md`](../../anti-patterns/workflow-event-isinstance.md).

### `WorkflowRunState` enum

[`_events.py:L58-L67`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L58-L67):

`STARTED`, `IN_PROGRESS`, `IN_PROGRESS_PENDING_REQUESTS`, `IDLE`, `IDLE_WITH_PENDING_REQUESTS`, `FAILED`, `CANCELLED`.

---

## `Executor` & `WorkflowContext`

[`_executor.py:L30-L200`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_executor.py#L30-L200)

Executors discover their handlers via two decorators:

### `@handler` (class-based)

```python
from agent_framework import Executor, WorkflowContext, handler

class Summarizer(Executor):
    @handler
    async def summarize(self, message: str, ctx: WorkflowContext[str, str]) -> None:
        partial = message[:200]
        await ctx.send_message(partial)        # downstream message
        await ctx.yield_output(partial)        # workflow-level output
```

Handler signatures are validated at `__init__`. Each executor must have at least one `@handler` method.

### `@executor` (function-based)

[`_function_executor.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_function_executor.py), exported as `agent_framework.executor`:

```python
from agent_framework import executor

@executor(id="upper")
async def to_upper(text: str, ctx: WorkflowContext[str]) -> None:
    await ctx.send_message(text.upper())
```

### `WorkflowContext` type system

Three context variants drive handler capabilities ([`_executor.py:L105-L138`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_executor.py#L105-L138)):

| Annotation | Handler may call | Purpose |
|-----------|------------------|---------|
| `WorkflowContext` | side effects only | Logging / sinks |
| `WorkflowContext[OutT]` | `ctx.send_message(OutT)` | Mid-graph processor |
| `WorkflowContext[OutT, W_OutT]` | `ctx.send_message(OutT)` + `ctx.yield_output(W_OutT)` | Output-emitting executor |

`ctx.request_info(...)` is available on all variants — it bubbles up a `request_info` event for the caller to satisfy via `responses=` on a follow-up `workflow.run(...)`.

---

## Runtime model — Pregel supersteps

[`_runner.py:L78-L120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_runner.py#L78-L120)

The workflow runs in **discrete supersteps**, not message-by-message:

1. **Superstep 0** (pre-loop) — start executor processes the initial message.
2. **Superstep N** — every executor with pending messages runs concurrently. New messages are queued for superstep N+1.
3. **Convergence** — when no pending messages remain, the loop ends and the workflow becomes `IDLE`.
4. **Bound** — `max_iterations` (default 100) caps the number of supersteps; exceeding it raises `WorkflowConvergenceException`.

Each superstep emits `superstep_started` and `superstep_completed` events. See [`workflow-internals.md`](workflow-internals.md) for the full runtime breakdown.

---

## Functional / decorator-style workflows

In addition to the builder API, 1.8.0 ships a functional construction style via `agent_framework.workflow` (lowercase, decorator) and `FunctionalWorkflow` / `FunctionalWorkflowAgent` ([`_workflows/_functional.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_functional.py)). Use it for inline, single-file workflows; use `WorkflowBuilder` when you need full edge control, checkpointing, or visualization.

---

## Symbol cheat sheet (re-exported from `agent_framework`)

Verified via `_workflows/_*` imports in [`agent_framework/__init__.py:L212-L284`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/__init__.py#L212-L284).

- **Construction**: `WorkflowBuilder`, `Workflow`, `workflow` (decorator), `FunctionalWorkflow`
- **Execution**: `WorkflowRunResult`, `Runner`
- **Events**: `WorkflowEvent`, `WorkflowEventType`, `WorkflowEventSource`, `WorkflowRunState`, `WorkflowErrorDetails`
- **Executors**: `Executor`, `handler`, `executor`, `FunctionExecutor`, `AgentExecutor`, `AgentExecutorRequest`, `AgentExecutorResponse`, `WorkflowExecutor`, `SubWorkflowRequestMessage`, `SubWorkflowResponseMessage`, `WorkflowAgent`
- **Edges**: `Edge`, `EdgeCondition`, `SingleEdgeGroup`, `FanInEdgeGroup`, `FanOutEdgeGroup`, `SwitchCaseEdgeGroup`, `SwitchCaseEdgeGroupCase`, `SwitchCaseEdgeGroupDefault`, `Case`, `Default`
- **Context**: `WorkflowContext`, `WorkflowMessage`
- **Checkpointing**: `WorkflowCheckpoint`, `CheckpointStorage` (from `agent_framework.workflows`)
- **Validation/Viz**: `WorkflowValidationError`, `EdgeDuplicationError`, `validate_workflow_graph`, `WorkflowViz`
- **Request/response**: `response_handler` (decorator on the `RequestInfoMixin`)
- **Exceptions**: `WorkflowException`, `WorkflowCheckpointException`, `WorkflowConvergenceException`, `WorkflowRunnerException`

---

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| `isinstance(event, IntermediateEvent)` | Use `event.type == "intermediate"`. The unified `WorkflowEvent` has no per-type subclasses. |
| Reading `event.output` / `event.error` / `event.content` | None of those exist. Use `event.data` (payload) or `event.details` (errors). |
| `output_executors=[...]` in new code | Deprecated. Use `output_from=[...]`. |
| `result.output` | Doesn't exist. Use `result.get_outputs()` (returns list). |
| Passing `mode="all"` to `add_fan_in_edges` | No such parameter — aggregation is always full-batch. The target receives a `list`. |
| Calling `add_fan_out` / `add_switch_case` / `add_handoff` on the builder | Method names are `add_fan_out_edges` / `add_switch_case_edge_group` / no built-in `add_handoff` (handoffs come from `agent_framework.orchestrations`). |
| Forgetting `start_executor=` at construction | Required kwarg-only — there is no `set_start_executor()`. |
| Calling `workflow.run_stream(...)` | Removed in 1.5.0. Use `workflow.run(..., stream=True)`. |
| Building without `output_from` or `intermediate_output_from` | Triggers `DeprecationWarning` — explicit designation will become mandatory. |

---

## See also

- [`workflow-internals.md`](workflow-internals.md) — Pregel runtime, `Runner`, `State`, `EdgeRunner`
- [`agents.md`](agents.md) — agents wrapped as executors
- [`evaluation.md`](evaluation.md) — ⚠️ EXPERIMENTAL — evaluate workflow quality (`evaluate_workflow`, per-agent breakdown)
- [`exceptions.md`](exceptions.md) — what `.run()` raises
- [`../../patterns/multi-agent-workflow.md`](../../patterns/multi-agent-workflow.md) — end-to-end recipe
- [`../../patterns/streaming-output.md`](../../patterns/streaming-output.md) — `stream=True` loop in detail
- [`../../patterns/workflow-checkpointing.md`](../../patterns/workflow-checkpointing.md) — checkpoint flow
- [`../../patterns/workflow-as-agent-nesting.md`](../../patterns/workflow-as-agent-nesting.md) — `workflow.as_agent()` and nested workflows
- [`../../patterns/workflow-evaluation.md`](../../patterns/workflow-evaluation.md) — per-sub-agent scoring with `evaluate_workflow`
- [`composition-adapters.md`](composition-adapters.md) — `Workflow.as_agent`, `_maybe_wrap_agent`, `context_mode`, full directional matrix
- [`observability.md`](observability.md) — `workflow_tracer`, `create_workflow_span`, span hierarchy (`workflow.run` → `executor.process` → `edge_group.process` → `message.send`)
- [`../../patterns/observability-workflow-tracing.md`](../../patterns/observability-workflow-tracing.md) — interpreting workflow span trees + fan-in span links
- [`declarative.md`](declarative.md) — ⚠️ BETA — `WorkflowFactory` builds the same `Workflow` graph from YAML
- [`../../anti-patterns/workflow-event-isinstance.md`](../../anti-patterns/workflow-event-isinstance.md)
- [`../../anti-patterns/eval-as-test-substitute.md`](../../anti-patterns/eval-as-test-substitute.md) — EVALS-as-CI-gate misuse
- [`../../anti-patterns/composition-pitfalls.md`](../../anti-patterns/composition-pitfalls.md) — `Workflow.as_agent` input-types validation, `context_mode="full"` leak, duplicate-agent dedupe pitfalls
