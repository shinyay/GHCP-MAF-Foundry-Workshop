# Pattern: Azure Monitor / App Insights End-to-End

> Status: **Stable** core API; depends on `azure-monitor-opentelemetry` external package.
> Verified against: `agent-framework-foundry==1.8.0`, source docstring [`observability.py:L1229-L1240`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1229-L1240)
> Pinned: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0)

## Goal

Ship Agent Framework telemetry (spans + metrics + logs) to **Azure Application Insights** via `azure-monitor-opentelemetry`, then query agent behavior with KQL.

## When to use

| Scenario | Use this pattern |
|----------|------------------|
| Production agent deployment to Azure | ✅ |
| Hybrid (Azure-hosted compute + on-prem observability) | ❌ — use [`observability-otel.md`](observability-otel.md) with OTLP collector |
| Local debugging only | ❌ — use [`observability-otel.md`](observability-otel.md) with console exporter |

## Prerequisites

```bash
pip install agent-framework-foundry==1.8.0
pip install azure-monitor-opentelemetry>=1.6.0   # brings in opentelemetry-sdk transitively
```

An Application Insights workspace and its connection string:
```bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=https://.../;..."
```

## The supported recipe

The Agent Framework source docstring ([`observability.py:L1229-L1240`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1229-L1240)) prescribes this exact pattern:

```python
# azure_monitor_observability.py
import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import enable_sensitive_telemetry
from azure.identity.aio import AzureCliCredential
from azure.monitor.opentelemetry import configure_azure_monitor


def setup_observability() -> None:
    # 1. Azure Monitor registers TracerProvider, MeterProvider, LoggerProvider
    #    AND their App Insights exporters. Do this ONCE at startup.
    cs = os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
    configure_azure_monitor(connection_string=cs)

    # 2. Optional: opt-in to sensitive-data capture (prompts/completions/tool args).
    #    Skip in production unless your App Insights workspace is privacy-reviewed.
    if os.environ.get("ENABLE_SENSITIVE_DATA", "").lower() in ("true", "1"):
        enable_sensitive_telemetry()


async def main() -> None:
    setup_observability()

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=cred,
        )
        async with client.as_agent(
            name="customer-support",
            instructions="Answer customer questions politely.",
        ) as agent:
            result = await agent.run("How do I reset my password?")
            print(result.text)


asyncio.run(main())
```

> [!IMPORTANT]
> Do **NOT** call `configure_otel_providers()` after `configure_azure_monitor()` (or vice versa). The OTel SDK keeps only ONE global `TracerProvider`/`MeterProvider`/`LoggerProvider` per process; the [`opentelemetry-sdk` overrides override-warning](https://opentelemetry-python.readthedocs.io/en/latest/api/trace.html#opentelemetry.trace.set_tracer_provider) when a second `set_tracer_provider()` is called. Whichever call wins, the other's exporters silently stop firing. If you need to add additional exporters/processors to the Azure Monitor provider, configure them through the OTel SDK directly on the active provider (e.g. `trace.get_tracer_provider().add_span_processor(...)`) — do not call a second provider-setup function.

## Why each piece

| Piece | Why |
|-------|-----|
| `configure_azure_monitor(connection_string=cs)` | Registers Azure Monitor's `TracerProvider`/`MeterProvider`/`LoggerProvider` with App Insights exporters globally. Agent Framework's default-on instrumentation picks them up automatically (no `configure_otel_providers()` needed). |
| `enable_sensitive_telemetry()` (optional) | Sets `OBSERVABILITY_SETTINGS.enable_sensitive_data = True` so chat spans emit `gen_ai.user.message`, `gen_ai.assistant.message`, etc. events with prompt/completion bodies. |
| `os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]` | Fail fast if not set. Don't fall back to defaults — accidentally pointing production traces at a dev workspace is worse than failing to start. |
| `setup_observability()` BEFORE `FoundryChatClient(...)` | Provider must be registered before any chat client emits its first span. (Spans emitted before setup go to the NoOp tracer and are lost.) |

## Verification

Run the script, then in the Azure portal **Application Insights → Logs**:

```kql
// 1. Confirm agent runs are arriving (spans land in `dependencies`)
dependencies
| where timestamp > ago(15m)
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| extend agent_name = tostring(customDimensions["gen_ai.agent.name"])
| project timestamp, name, duration, agent_name
| top 20 by timestamp desc
```

You should see one row per `agent.run()` call, with `name` starting with `invoke_agent`.

> [!NOTE]
> Azure Monitor's [OpenTelemetry exporter](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-add-modify) maps OTel spans → the `dependencies` table (or `requests` for the inbound root span on web apps). The `traces` table is for **logs**, not spans. If you're querying span attributes, always use `dependencies` (or `requests` when applicable).

## Useful KQL queries

### Per-agent latency (p50/p95/p99)

```kql
dependencies
| where timestamp > ago(1h)
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| extend agent_name = tostring(customDimensions["gen_ai.agent.name"])
| summarize 
    p50_ms = percentile(duration, 50),
    p95_ms = percentile(duration, 95),
    p99_ms = percentile(duration, 99),
    count = count()
  by agent_name
| order by count desc
```

### Token cost per conversation

> [!IMPORTANT]
> Chat spans only carry `gen_ai.conversation.id` when the caller explicitly supplies a `conversation_id=` (or `thread_id=`) on the chat options, OR when wrapped by an agent layer that propagates `ctx.session.service_session_id` into options. Bare `agent.run("hello")` against a stateless client typically produces chat spans **without** this attribute, so the query below will discard them. For those flows, group by `operation_Id` (the trace ID) instead. Verified at [`observability.py:L2071,L2104`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2071).

```kql
// Token cost per conversation (requires conversation_id on the chat span)
dependencies
| where timestamp > ago(1d)
| where customDimensions["gen_ai.operation.name"] == "chat"
| extend 
    conversation_id = tostring(customDimensions["gen_ai.conversation.id"]),
    input_tokens   = toint(customDimensions["gen_ai.usage.input_tokens"]),
    output_tokens  = toint(customDimensions["gen_ai.usage.output_tokens"]),
    model          = tostring(customDimensions["gen_ai.request.model"])
| where isnotempty(conversation_id)
| summarize 
    total_input  = sum(input_tokens),
    total_output = sum(output_tokens),
    requests     = count(),
    models       = make_set(model)
  by conversation_id
| order by total_output + total_input desc
| take 20
```

If `conversation_id` is empty for your scenario, group by `operation_Id` (= trace ID) for per-trace rollup:

```kql
// Token cost per trace (no conversation_id required)
dependencies
| where timestamp > ago(1d)
| where customDimensions["gen_ai.operation.name"] == "chat"
| extend 
    input_tokens  = toint(customDimensions["gen_ai.usage.input_tokens"]),
    output_tokens = toint(customDimensions["gen_ai.usage.output_tokens"]),
    model         = tostring(customDimensions["gen_ai.request.model"])
| summarize 
    total_input  = sum(input_tokens),
    total_output = sum(output_tokens),
    requests     = count(),
    models       = make_set(model)
  by operation_Id
| order by total_output + total_input desc
| take 20
```

### Tool error rate

```kql
dependencies
| where timestamp > ago(1h)
| where customDimensions["gen_ai.operation.name"] == "execute_tool"
| extend tool_name = tostring(customDimensions["gen_ai.tool.name"])
| summarize 
    total = count(),
    errors = countif(success == false),
    error_rate_pct = 100.0 * countif(success == false) / count()
  by tool_name
| where total > 5
| order by error_rate_pct desc
```

### Per-model token usage trend

```kql
customMetrics
| where timestamp > ago(7d)
| where name == "gen_ai.client.token.usage"
| extend 
    model      = tostring(customDimensions["gen_ai.request.model"]),
    token_type = tostring(customDimensions["gen_ai.token.type"])
| summarize total_tokens = sum(value) by bin(timestamp, 1h), model, token_type
| render timechart
```

### Failed agent runs

```kql
dependencies
| where timestamp > ago(1h)
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| where success == false
| project 
    timestamp, 
    agent_name = customDimensions["gen_ai.agent.name"],
    operation_name = customDimensions["gen_ai.operation.name"],
    error_type = tostring(customDimensions["error.type"]),
    duration_ms = duration
| top 50 by timestamp desc
```

## Configuration options

### Sampling

Azure Monitor SDK sampling is set via `configure_azure_monitor`:

```python
configure_azure_monitor(
    connection_string=cs,
    sampling_ratio=0.1,   # 10% of traces
)
```

When sampling, beware that long agent runs that span many minutes may have parent/child spans split across sampling decisions. Use **tail sampling** at the collector level (not head sampling at the source) if you need accurate failure capture.

### Resource attributes

`configure_azure_monitor()` builds its own resource from standard OTel env vars:

```bash
export OTEL_SERVICE_NAME=customer-support-bot
export OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production,team=ml-platform,region=eastus
```

These appear as `cloud_RoleName` and additional `customDimensions` in App Insights.

### Live Metrics

```python
configure_azure_monitor(
    connection_string=cs,
    enable_live_metrics=True,
)
```

Enables the App Insights **Live Metrics** view for real-time CPU/memory/RPS without sampling delay.

## Common mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Calling `configure_otel_providers()` after `configure_azure_monitor()` | Some signals (often metrics) silently stop flowing to App Insights | Pick one entry point only. Azure Monitor is the global config; Agent Framework piggybacks on it via default-on instrumentation. |
| Setting `enable_sensitive_data=True` in production | PII / customer data in App Insights | Default to `False`; gate behind explicit env var for dev/staging. |
| `setup_observability()` called AFTER first agent.run() | First few spans missing | Call setup BEFORE constructing any chat client or agent. |
| Forgetting `APPLICATIONINSIGHTS_CONNECTION_STRING` | Silently no telemetry (Azure Monitor's exporters become no-ops) | Fail fast: `os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]` (KeyError if missing) instead of `os.environ.get(...)`. |
| Pointing at the wrong App Insights workspace via stale env var | Traces show up in unrelated workspace | Explicitly inject connection string from your secret manager / managed identity, never from inherited env vars. |
| Using `configure_otel_providers(enable_sensitive_telemetry=True)` | `TypeError` / fabricated kwarg | The kwarg is `enable_sensitive_data=True`. Or use the standalone `enable_sensitive_telemetry()` function. |

## Variants

### With managed identity (no connection string in env)

```python
from azure.identity.aio import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor

# Use AAD instead of an instrumentation key
configure_azure_monitor(
    connection_string="InstrumentationKey=...;...",  # still required for endpoint resolution
    credential=DefaultAzureCredential(),
)
```

See the [Azure Monitor docs](https://learn.microsoft.com/azure/azure-monitor/app/azure-ad-authentication) for the full managed-identity pattern.

### Filtered metric views

```python
from agent_framework.observability import create_metric_views
from azure.monitor.opentelemetry import configure_azure_monitor

# Drop everything except agent_framework.* and gen_ai.*
configure_azure_monitor(
    connection_string=cs,
    views=create_metric_views(),
)
```

`configure_azure_monitor` accepts `views=` to filter metric instruments. Use `create_metric_views()` from Agent Framework to get sensible defaults.

## See also

- [`../api-reference/1.8.0/observability.md`](../api-reference/1.8.0/observability.md) — full API surface, sticky-disable, span/metric catalog
- [`observability-otel.md`](observability-otel.md) — vendor-agnostic OTLP recipe (alternative)
- [`observability-workflow-tracing.md`](observability-workflow-tracing.md) — interpreting workflow/executor spans in App Insights
- [`../anti-patterns/instrumentation-implicit-on-1.6.md`](../anti-patterns/instrumentation-implicit-on-1.6.md) — surprise modes after upgrading to 1.6
- [Azure Monitor OpenTelemetry distro docs](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- Upstream source: [`observability.py:L1229-L1240`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1229-L1240) (Azure Monitor recipe in docstring)
