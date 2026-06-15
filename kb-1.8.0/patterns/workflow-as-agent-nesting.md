# Pattern: Nesting Workflows — `Workflow.as_agent()` and `WorkflowExecutor`

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_workflows/_agent.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py), [`_workflows/_workflow_executor.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_executor.py), [`_workflows/_events.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py)

## Goal

Compose workflows hierarchically — use one workflow as a building block inside another or expose a workflow as an `Agent` to anything that consumes the agent contract (other workflows, tool servers, the DevUI, MCP, etc.).

1.8.0 ships **two** composition primitives:

1. **`Workflow.as_agent(...)`** — wrap a workflow as a `WorkflowAgent` (a `BaseAgent` subclass). Use this when the consumer expects an `Agent`.
2. **`WorkflowExecutor`** — wrap a workflow as an `Executor` inside a parent workflow. Use this when the consumer is another workflow.

## When to use

| Need | Use |
|------|-----|
| Expose a multi-step planner workflow as a single agent that another workflow's `add_edge(..., planner_agent)` consumes | `workflow.as_agent(...)` |
| Drop a sub-workflow into a parent workflow and route its outputs to a sibling executor | `WorkflowExecutor(workflow=...)` |
| Forward only the meaningful events (output, intermediate, request_info) and hide the sub-workflow's executor bookkeeping | Either — both auto-filter using `AGENT_FORWARDED_EVENT_TYPES` |

## Cross-boundary event forwarding

`AGENT_FORWARDED_EVENT_TYPES` ([`_events.py:L138-L143`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_events.py#L138-L143)):

```python
AGENT_FORWARDED_EVENT_TYPES: frozenset[str] = frozenset({
    "output",
    "intermediate",
    "data",          # deprecated alias for intermediate
    "request_info",
})
```

**Only these four event types cross the `workflow.as_agent()` boundary.** Lifecycle (`started`, `status`, `failed`), diagnostics (`warning`, `error`), executor bookkeeping (`executor_*`, `superstep_*`), and orchestration internals (`group_chat`, `handoff_sent`, `magentic_orchestrator`) stay **inside** the workflow. Callers of the wrapping `WorkflowAgent` see a clean agent-response stream.

`WorkflowAgent.__init__` enforces the same expectation in its docstring ([`_agent.py:L105-L109`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L105-L109)): only `output` and `request_info` events are converted to agent responses.

---

## Option 1 — `Workflow.as_agent(...)`

Signature at [`_workflow.py:L1091-L1106`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L1091-L1106):

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

### Code

```python
from agent_framework import WorkflowBuilder
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

# Inner workflow: a multi-step research pipeline
research_workflow = (
    WorkflowBuilder(
        name="research_v1",
        start_executor=query_classifier,
        output_from=[summarizer],
    )
    .add_chain([query_classifier, retriever, ranker, summarizer])
    .build()
)

# Expose it as an Agent
research_agent = research_workflow.as_agent(
    name="ResearchAgent",
    description="Multi-step retrieval + ranking + summarization.",
)

# Outer workflow consumes it like any agent
async with AzureCliCredential() as cred:
    inner_client = FoundryChatClient(
        project_endpoint="https://...services.ai.azure.com/api/projects/...",
        model="gpt-5-4",
        credential=cred,
    )
    async with inner_client.as_agent(name="Coordinator", instructions="You triage work.") as coordinator:
        outer = (
            WorkflowBuilder(
                name="outer_v1",
                start_executor=coordinator,
                output_from=[research_agent],
            )
            .add_edge(coordinator, research_agent)
            .build()
        )

        result = await outer.run("How safe is rural travel in Iceland in March?")
        print(result.get_outputs())
```

### What the caller sees

The wrapping `WorkflowAgent` returns standard `AgentResponse` / `AgentResponseUpdate` objects ([`_agent.py:L22-L31`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L22-L31)). It also exposes a synthetic tool `request_info` (constant `WorkflowAgent.REQUEST_INFO_FUNCTION_NAME` at [`_agent.py:L56`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L56)) that an LLM caller can invoke to deliver responses to pending `request_info` events — i.e., the workflow's HITL handshake is exposed as a tool call.

---

## Option 2 — `WorkflowExecutor`

[`_workflow_executor.py:L103-L150`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_executor.py#L103-L150).

### Code

```python
from agent_framework import Executor, WorkflowBuilder, WorkflowExecutor

sub_workflow = (
    WorkflowBuilder(name="enrichment_v1", start_executor=normalizer, output_from=[enricher])
    .add_chain([normalizer, lookup, enricher])
    .build()
)

# Wrap as an Executor; messages flow in and (by default) flow back via send_message
sub_executor = WorkflowExecutor(
    workflow=sub_workflow,
    id="enrichment",
    allow_direct_output=False,    # default — outputs become messages in the parent graph
)

parent = (
    WorkflowBuilder(
        name="parent_v1",
        start_executor=intake,
        output_from=[reporter],
    )
    .add_edge(intake, sub_executor)
    .add_edge(sub_executor, reporter)
    .build()
)
```

### `allow_direct_output` semantics

Documented at [`_workflow_executor.py:L127-L145`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_executor.py#L127-L145):

| `allow_direct_output` | Effect |
|----------------------|--------|
| `False` (default) | Sub-workflow `yield_output(x)` → parent receives `x` as a downstream `send_message`. Use when the sub-workflow is one stage of the parent's pipeline. |
| `True` | Sub-workflow `yield_output(x)` → parent emits `x` as a top-level workflow output. Use when the sub-workflow's result *is* the parent's result. |

### Request/response coordination

If the sub-workflow emits a `request_info` event, `WorkflowExecutor`:

1. Wraps it in a `SubWorkflowRequestMessage(source_event=..., executor_id=self.id)` ([`_workflow_executor.py:L72-L87`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_executor.py#L72-L87)) and sends it upstream.
2. A parent-workflow executor with a matching `@handler` intercepts the request, calls `request.create_response(data=...)` (which type-checks against `source_event.response_type`), and sends the `SubWorkflowResponseMessage` back to `target_id=request.executor_id` ([`_workflow_executor.py:L88-L100`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_executor.py#L88-L100)).
3. `WorkflowExecutor` accumulates responses until `expected_response_count` is reached, then resumes the sub-workflow. State is held in the `ExecutionContext` dataclass ([`_workflow_executor.py:L37-L55`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_executor.py#L37-L55)).

### Intercepting requests in the parent

```python
from agent_framework import Executor, WorkflowContext, handler, SubWorkflowRequestMessage

class PolicyGate(Executor):
    @handler
    async def gate(
        self,
        request: SubWorkflowRequestMessage,
        ctx: WorkflowContext,
    ) -> None:
        if self.is_allowed(request.source_event.data):
            response = request.create_response(data=True)
            await ctx.send_message(response, target_id=request.executor_id)
        else:
            # Forward upstream so the workflow-level caller can answer
            await ctx.request_info(
                request.source_event,
                response_type=request.source_event.response_type,
            )
```

(Adapted from [`_executor.py:L88-L103`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_executor.py#L88-L103).)

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Expecting `executor_completed` events from the sub-workflow to show up in the parent agent caller | They don't — only `AGENT_FORWARDED_EVENT_TYPES` cross the boundary. Filter inside the sub-workflow first or subscribe to the inner workflow's events directly. |
| Passing `output_from=[]` (empty) to the inner workflow | The wrapping `WorkflowAgent` will receive no agent responses — it surfaces only `output` events. Set `output_from=[<the final executor>]`. |
| Using `WorkflowExecutor(workflow=..., allow_direct_output=True)` and then also routing the executor's output to a downstream executor | Mutually inconsistent — when `allow_direct_output=True`, the sub-workflow output bypasses message routing. Pick one mode. |
| Sub-workflow `request_info` arrives but parent has no `@handler` for `SubWorkflowRequestMessage` | Sub-workflow stalls. Either register an interceptor or forward the request upstream with `ctx.request_info(...)`. |
| Reusing the same `Workflow` instance inside multiple `WorkflowExecutor` wrappers concurrently | `Workflow._ensure_not_running` raises. Build a fresh `Workflow` per `WorkflowExecutor`. |

## Verification

```python
# A minimal "as_agent" round-trip
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from typing_extensions import Never

class Echo(Executor):
    @handler
    async def echo(self, msg: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(f"echo: {msg}")

inner = WorkflowBuilder(name="echo_v1", start_executor=Echo(id="echo"), output_from="all").build()
agent = inner.as_agent(name="EchoAgent")

resp = await agent.run("hi")
assert resp.messages[0].text.startswith("echo: hi")
```

## See also

- [`../api-reference/1.8.0/composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md) — full directional matrix (`as_tool` / `as_mcp_server` / `as_agent` / `_maybe_wrap_agent`)
- [`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md) — full builder + run API
- [`../api-reference/1.8.0/workflow-internals.md`](../api-reference/1.8.0/workflow-internals.md) — runtime semantics
- [`workflow-checkpointing.md`](workflow-checkpointing.md) — durable resume
- [`agent-as-tool-handoff.md`](agent-as-tool-handoff.md) — wrap a `WorkflowAgent` as a tool for LLM-decided delegation
- [`agent-as-mcp-server.md`](agent-as-mcp-server.md) — expose a regular `Agent` (or `FoundryAgent`) over MCP; `WorkflowAgent` itself is **not** supported because it inherits `BaseAgent` directly and lacks `as_mcp_server` — wrap the workflow inside a regular `Agent`-backed tool instead
- [`../anti-patterns/composition-pitfalls.md`](../anti-patterns/composition-pitfalls.md) — `Workflow.as_agent` `list[Message]` requirement, `context_mode` leakage, duplicate-agent dedupe
- [`../anti-patterns/workflow-event-isinstance.md`](../anti-patterns/workflow-event-isinstance.md)
