# Pattern: Workflow Trace Interpretation

> Status: **Stable**
> Verified against: `agent-framework-foundry==1.8.0`, [`observability.py:L2337-L2477`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2337-L2477)
> Pinned: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0)

## Goal

Read a multi-executor workflow trace and understand which spans correspond to which parts of the graph — `WorkflowBuilder`, edges, fan-in joins, agent-as-executor turns.

## When to use

| Scenario | Use this pattern |
|----------|------------------|
| Diagnosing slow paths in a `WorkflowBuilder` graph | ✅ — identify which executor / edge is the bottleneck |
| Debugging unexpected fan-in behavior | ✅ — span links reveal multi-source convergence |
| Sanity-checking that all executors actually ran | ✅ — every `executor.process` should appear once per invocation |
| Single-agent debugging | ❌ — only `chat`/`invoke_agent`/`execute_tool` spans, not a workflow tree |

## Prerequisites

- An OTel exporter wired up — see [`observability-otel.md`](observability-otel.md) or [`observability-azure-monitor.md`](observability-azure-monitor.md).
- A workflow built with `WorkflowBuilder` (not a single-agent setup).

## The workflow span hierarchy

When you call `await workflow.run(...)`, Agent Framework emits this span tree:

```
workflow.run                                       ← root span (one per invocation)
├── executor.process <executor_id>                 ← one per executor invocation; name SUFFIXED with executor_id
│   ├── chat <model>                               ← if the executor is an AgentExecutor
│   │   └── execute_tool <tool>                    ← if the agent called tools
│   └── message.send                               ← one per outbound message (PRODUCER kind)
├── edge_group.process <edge_group_type>           ← one per edge group activation; name SUFFIXED with type
│   └── executor.process <next_executor_id>        ← downstream executor (linked, not nested — see Pattern 3)
│       └── ...
└── ...
```

There is also a build-time span emitted once when you call `.build()`:

```
workflow.build                                     ← emitted once, during WorkflowBuilder.build()
```

### Span name catalog (verified)

> [!IMPORTANT]
> Span names for `executor.process` and `edge_group.process` include a **suffix** (the executor ID or edge group type). When querying by name in a backend, use `startswith` (KQL) / `=~` (regex) instead of exact equality. Verified at [`observability.py:L2400`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2400) and [`observability.py:L2473`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2473).

| Span name pattern | Emitted by | Attributes (verified) |
|------|--------|-----------|
| `workflow.build` | `WorkflowBuilder.build()` ([`_workflow_builder.py:L805,L875-L882`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L805-L882)) | `workflow_builder.name`, `workflow.id`, `workflow.definition` (JSON via `workflow.to_json()`); optional `workflow_builder.description`. Events: `build.started`, `build.completed`, `build.error` (with `build.error.message`, `build.error.type`). |
| `workflow.run` | `Workflow.run(..., stream=True)` ([`_workflow.py:L497-L506`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L497-L506)) | `workflow.id` (always); optional `workflow.name`, `workflow.description`. Events: `workflow.started`, `workflow.completed`, `workflow.error`. |
| `executor.process <executor_id>` | `create_processing_span()` ([`observability.py:L2399-L2409`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2399-L2409)) | `executor.id`, `executor.type`, `message.type` (`"standard"` or `"response"`), `message.payload_type`. Links to source publishing spans for fan-in. |
| `edge_group.process <edge_group_type>` | `create_edge_group_processing_span()` ([`observability.py:L2472-L2476`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2472-L2476)) | `edge_group.type`; optional `edge_group.id`, `message.source_id`, `message.target_id`. Outcome reported via `edge_group.delivery_status` event/attribute (see Pattern 2). Links to source publishing spans. |
| `message.send` | `WorkflowContext.send_message()` ([`_workflow_context.py:L319-L323`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_context.py#L319-L323)) | `message.type` (always); optional `message.destination_executor_id`. Kind = `PRODUCER`. |
| `chat <model>` | `ChatTelemetryLayer` (per-client) | `gen_ai.*` per OTel GenAI semantic conventions; `gen_ai.system="microsoft.agent_framework"`; `gen_ai.provider.name` per client. |
| `invoke_agent <agent>` | `AgentTelemetryLayer` | `gen_ai.agent.name`, `gen_ai.operation.name="invoke_agent"`. |
| `execute_tool <tool>` | function tool layer | `gen_ai.tool.name`, `gen_ai.tool.call.id`. |

> [!NOTE]
> `message.send` does NOT set `message.source_id` or `message.target_id` — those live on the `edge_group.process` span. The send span carries `message.destination_executor_id` (only when a specific target is requested).

---

## Recipe: enable + interpret a workflow trace

```python
# workflow_with_tracing.py
import asyncio

from agent_framework import WorkflowBuilder, AgentExecutor
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import configure_otel_providers
from azure.identity.aio import AzureCliCredential


async def main() -> None:
    configure_otel_providers(enable_console_exporters=True)

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(project_endpoint="...", model="gpt-5-4", credential=cred)
        researcher = client.as_agent(name="researcher", instructions="Research the topic.")
        summarizer = client.as_agent(name="summarizer", instructions="Summarize findings.")

        workflow = (
            WorkflowBuilder(start_executor=researcher, output_from=[summarizer])
            .add_edge(researcher, summarizer)
            .build()
        )
        # On .build() → workflow.build span emitted

        async for event in workflow.run("What is OpenTelemetry?", stream=True):
            # On each run → workflow.run + executor.process + edge_group.process + chat spans
            if event.type == "output":
                print("FINAL:", event.data)


asyncio.run(main())
```

Console output (abridged — span dump per OTel format):

```
[span] workflow.build duration_ms=4.1
[span] workflow.run duration_ms=2340.2
  [span] executor.process researcher duration_ms=920.4
    [span] chat gpt-5-4 duration_ms=915.0 input_tokens=42 output_tokens=180
    [span] message.send duration_ms=0.2
  [span] edge_group.process SingleEdgeGroup duration_ms=0.3 delivery_status=delivered
  [span] executor.process summarizer duration_ms=1410.1
    [span] chat gpt-5-4 duration_ms=1405.0 input_tokens=210 output_tokens=92
```

> [!NOTE]
> The `executor.process <id>` / `edge_group.process <type>` form (with a trailing identifier) is the verified span-name shape produced at [`observability.py:L2400`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2400) and [`L2473`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2473).

---

## Pattern 1: Find which executor is slow

```kql
// App Insights — per-executor p95 latency
// Note: span name has the form "executor.process <executor_id>", so use startswith.
dependencies
| where timestamp > ago(1h)
| where name startswith "executor.process"
| extend executor_id = tostring(customDimensions["executor.id"])
| summarize 
    p50 = percentile(duration, 50),
    p95 = percentile(duration, 95),
    count = count()
  by executor_id
| order by p95 desc
```

> [!NOTE]
> Agent Framework does **not** emit a built-in metric for workflow/executor span duration. If you need PromQL/Grafana dashboards on executor latency, configure an OTel Collector with the [spanmetrics connector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/connector/spanmetricsconnector) to derive a histogram from spans (the metric name will be whatever you configure, not built-in). The `gen_ai.client.operation.duration` metric is for chat clients only, not for workflow/executor spans.

## Pattern 2: Detect dropped messages

Edge groups emit `edge_group.process <type>` spans with a `edge_group.delivery_status` attribute when delivery fails or is filtered. The values come from the `EdgeGroupDeliveryStatus` enum at [`observability.py:L2318-L2326`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2318-L2326):

| Value | Meaning |
|-------|---------|
| `delivered` | Message was delivered to its target executor. |
| `dropped type mismatch` | Target executor's `input_types` does not accept this message type. |
| `dropped target mismatch` | Message had a specific `target_id` that did not match this edge's target. |
| `dropped condition evaluated to false` | An edge condition function rejected the message. |
| `exception` | Delivery raised an exception. |
| `buffered` | Message was buffered (e.g. fan-in waiting for additional sources). |

```kql
// App Insights — count non-delivered edge group outcomes
dependencies
| where timestamp > ago(1h)
| where name startswith "edge_group.process"
| extend status = tostring(customDimensions["edge_group.delivery_status"])
| where isnotempty(status) and status != "delivered"
| summarize count() by status
```

## Pattern 3: Trace fan-in joins via OTel span links

When an executor consumes messages from **multiple** upstream sources (e.g. a fan-in edge group), its `executor.process` span is created with OTel **span links** to each source publishing span instead of (or in addition to) a parent-child edge. This avoids drawing a single misleading "linear cause" arrow when convergence happened.

This is implemented at [`observability.py:L2374-L2397`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2374-L2397) — links are extracted from W3C `traceparent` headers in the inbound messages.

**Trade-off**: span-link visibility is **backend-dependent**.

- [Jaeger ≥ 1.30](https://www.jaegertracing.io/docs/) renders span links as separate arrows in the trace timeline.
- [Tempo / Grafana](https://grafana.com/docs/tempo/latest/) shows links in the span detail panel.
- [Azure Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/distributed-trace-data) **does not** currently expose OTel span links as a queryable column. There is no `customDimensions["span_link_count"]`. To diagnose fan-in in App Insights, look at the `executor.id` attribute and correlate manually against the workflow definition stored on the `workflow.build` span (`workflow.definition`).

## Pattern 4: Wrap a workflow run in an outer business span

You can wrap a workflow invocation in an **outer** span to attach business context (customer ID, tenant, request ID). This adds a parent span above the framework-emitted `workflow.run` — it does NOT modify the existing `workflow.run` span's attributes.

```python
from agent_framework.observability import create_workflow_span

with create_workflow_span(
    name="business.workflow_context",
    attributes={"customer_id": "abc123", "tenant_id": "xyz789"},
) as outer_span:
    # The framework will create its own workflow.run as a child of this span.
    async for event in workflow.run("hello", stream=True):
        if event.type == "output":
            outer_span.set_attribute("output.first_text_len", len(str(event.data)))
```

The resulting hierarchy:

```
business.workflow_context  ← your span (customer_id, tenant_id, custom outcome attrs)
└── workflow.run           ← framework-emitted (workflow.id, workflow.name, ...)
    └── ...
```

These outer-span attributes are queryable:

```kql
dependencies
| where timestamp > ago(1d)
| where name == "business.workflow_context"
| extend customer_id = tostring(customDimensions["customer_id"])
| summarize avg_duration_ms = avg(duration) by customer_id
| order by avg_duration_ms desc
```

> [!WARNING]
> Do **not** use `create_workflow_span(name="workflow.run", ...)` to "enrich" the framework's span. That would create a **second** span named `workflow.run` as the parent of the real one, producing two same-named spans per invocation and confusing trace viewers. Always use a distinct name like `business.workflow_context`. There is no public hook to mutate the framework-emitted `workflow.run` span's attributes.
>
> Source: [`observability.py:L2337-L2349`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2337-L2349) (`create_workflow_span` is a thin wrapper that always starts a new span at the current trace context).

---

## Why each piece

| Piece | Why |
|-------|-----|
| `workflow.build` span | One-shot span emitted by `WorkflowBuilder.build()`. Carries the validated graph as `workflow.definition` (JSON) so you can correlate runtime spans back to the build that produced them. |
| `workflow.run` span | Root span per `run()` invocation. Aggregate metrics roll up here. Has `workflow.id`, optional `workflow.name`, `workflow.description`. |
| `executor.process <id>` span | One per executor invocation. The "unit of work" in trace UIs. Name includes the executor ID; querying by name requires `startswith`. |
| `edge_group.process <type>` span | Captures routing between executors. The `edge_group.delivery_status` attribute reveals whether messages were delivered, dropped (type mismatch / target mismatch / condition false), buffered (waiting on fan-in), or raised. |
| `message.send` span | One per outbound message (PRODUCER kind). Lets you trace specific messages through the DAG via context propagation. |
| Span links on fan-in | Avoids drawing a misleading "single linear cause" when multiple upstreams converge. Visibility depends on backend (see Pattern 3). |
| `create_workflow_span(...)` | Public helper to add a **parent** business-context span above `workflow.run`. Does NOT mutate the framework-emitted span. |

## Common mistakes

| Mistake | Correction |
|---------|-----------|
| Querying `name == "executor.process"` | Use `name startswith "executor.process"` — the executor ID is appended (`executor.process my_executor_id`). |
| Looking for `executor.input_type` attribute | Real attributes are `message.type` (`"standard"` or `"response"`) and `message.payload_type` (the data type name). |
| Looking for `message.source_id` / `message.target_id` on `message.send` | Those live on `edge_group.process <type>` (only when set). `message.send` has `message.type` and optional `message.destination_executor_id`. |
| Expecting `edge_group.delivery_status` values like `OK`/`DROPPED`/`FAILED` | Real values are lowercase strings: `delivered`, `dropped type mismatch`, `dropped target mismatch`, `dropped condition evaluated to false`, `exception`, `buffered`. |
| Expecting one `executor.process` span per executor in the DAG | One per **invocation** — an executor that runs 3 times produces 3 spans. |
| Looking for the missing parent of a join executor's span | It has OTel **span links** instead of (or in addition to) one parent. Whether those are queryable depends on backend (see Pattern 3). |
| Using `create_workflow_span(name="workflow.run", ...)` to enrich the root span | This creates a **second** `workflow.run` span as a parent of the real one. Use a distinct name like `business.workflow_context`. There is no public hook to mutate the framework-emitted `workflow.run` span. |
| Adding `span.set_attribute(...)` inside an executor that calls `as_agent` | The current span there is the agent's `invoke_agent` span, not the executor span. Use the outer-span recipe (Pattern 4) for workflow-level context. |
| Hoping `workflow.build` span tells you which executors will run | It carries `workflow.definition` (the graph JSON) — that tells you the static graph. Use `executor.process <id>` spans from the actual run to see what ran. |
| Adding tons of custom attributes to chat-level spans (one per token) | Attribute cardinality blowup. Keep custom attributes at the outer-business-span granularity. |

## Verification

After running a workflow with tracing on, look for this hierarchy in your trace viewer:

```
workflow.run
├── executor.process <start_id>
│   ├── chat <model>           ← only if executor uses an agent
│   └── message.send
├── edge_group.process <type>
└── executor.process <next_id>
    └── ...
```

If `workflow.run` appears but no child `executor.process <...>` spans → your workflow built but raised before invoking the first executor. Check the `workflow.error` event on `workflow.run`.

If `executor.process <id>` spans appear but no `chat`/`invoke_agent` children → the executor is non-agent (`FunctionExecutor`, custom subclass). Spans are normal; inspect the executor type via the `executor.type` attribute.

If `edge_group.process <type>` shows `edge_group.delivery_status="dropped condition evaluated to false"` → an edge condition filtered out the message. Check your edge filter logic.

## See also

- [`../api-reference/1.8.0/observability.md`](../api-reference/1.8.0/observability.md) — full API surface
- [`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md) — `WorkflowBuilder` API
- [`../api-reference/1.8.0/workflow-internals.md`](../api-reference/1.8.0/workflow-internals.md) — runner/executor/edge internals (PR-A deep-dive)
- [`observability-otel.md`](observability-otel.md) — OTLP / console exporter setup
- [`observability-azure-monitor.md`](observability-azure-monitor.md) — App Insights setup with KQL queries
- Upstream source: [`observability.py:L2337-L2477`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2337-L2477) (workflow span helpers)
