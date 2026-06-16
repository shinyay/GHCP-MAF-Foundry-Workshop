# Observability (OpenTelemetry)

> Status: **Stable** core surface — **1.6.0 BREAKING**: instrumentation default ON (PR #5865) + `opentelemetry-sdk` no longer a hard dependency.
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: `inspect.signature(configure_otel_providers)`, `inspect.signature(FoundryChatClient.__init__)`, parent demo `src/demo3_hosted_mcp.py` lines 84-118 (custom `SpanExporter`), upstream [`observability.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py) (2477 LOC) and [`_telemetry.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_telemetry.py) (134 LOC).

Agent Framework emits OpenTelemetry **spans**, **metrics**, and **log events** for chat client requests, agent runs, tool calls, embedding requests, and workflow execution. You can ship them to any OTel backend (Azure Monitor / App Insights, Jaeger, OTLP collector, console, custom exporter).

> [!IMPORTANT]
> All telemetry conforms to the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). Attribute names like `gen_ai.operation.name`, `gen_ai.usage.input_tokens`, etc. follow that spec. Workflow-specific attributes (`workflow.*`, `executor.*`, `edge_group.*`, `message.*`) and `agent_framework.*` are framework extensions.

> [!NOTE]
> **1.8.0 FIX — Safe dataclass serialization in span attributes ([PR #6026](https://github.com/microsoft/agent-framework/pull/6026))**: Span attribute serialization previously threw `TypeError` (and silently dropped the surrounding span on some exporters) when a tool argument or workflow message contained a non-JSON-native dataclass containing fields like `datetime`, `Enum`, `Decimal`, or another dataclass. 1.8.0 routes dataclasses through a defensive `asdict`-plus-fallback `repr` path so attribute capture never raises. Sensitive-payload behavior is unchanged — enable with `enable_sensitive_telemetry()`.

---

## 1.6.0 BREAKING changes

| Change | Impact | Migration |
|--------|--------|-----------|
| **Instrumentation default ON** ([PR #5865](https://github.com/microsoft/agent-framework/pull/5865)) | `ENABLE_INSTRUMENTATION` env var now defaults to `True`. The framework emits spans/metrics from agent runs and chat clients whether you configured an exporter or not. If no exporter is configured, spans are still **created** by the framework but go to the NoOp tracer (silently dropped — no perceptible overhead). | Opt-out: call `disable_instrumentation()` once at process start (see [Sticky disable](#sticky-disable-semantics)). There is **no per-client `instrumentation_enabled=` kwarg** on `FoundryChatClient` — that does not exist on chat clients. (DevUI `serve(instrumentation_enabled=...)` is unrelated; see [`devui.md`](devui.md).) |
| **`opentelemetry-sdk` is no longer a hard dependency** | If you used SDK classes (`SpanExporter`, `SimpleSpanProcessor`, etc.) without installing the SDK explicitly, imports now fail. Calling `configure_otel_providers()` without `opentelemetry-sdk` installed raises `ModuleNotFoundError` with an install hint. | `pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc` if you need to register your own providers. This repo pins `opentelemetry-sdk` explicitly in `requirements.txt` so it always works. |
| **New helpers** | `enable_sensitive_telemetry()`, `enable_instrumentation(force=True)`, `disable_instrumentation()` (sticky), `create_resource()`, `create_metric_views()`, `workflow_tracer()`, `create_workflow_span()`. | See sections below. The previous `enable_instrumentation(enable_sensitive_data=True)` kwarg still works but `enable_sensitive_telemetry()` is the preferred shortcut. |

---

## Public API surface

All from `agent_framework.observability` ([verified by introspection](#how-this-page-was-verified)):

### Control functions

| Symbol | Purpose |
|--------|---------|
| `configure_otel_providers(*, enable_sensitive_data=None, enable_console_exporters=None, exporters=None, views=None, vs_code_extension_port=None, env_file_path=None, env_file_encoding=None)` | One-call setup of OTel `TracerProvider` + `MeterProvider` + `LoggerProvider` with your exporters. **Call once** at startup. ([source L1122-L1298](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1122-L1298)) |
| `enable_instrumentation(*, enable_sensitive_data=None, force=False)` | Programmatically enable; respects sticky disable unless `force=True`. ([L1086-L1120](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1086-L1120)) |
| `enable_sensitive_telemetry(*, force=False)` | Shortcut: enable instrumentation **and** capture prompts/completions/tool args in span attributes. ([L1029-L1059](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1029-L1059)) |
| `disable_instrumentation()` | **Sticky** — sets `_user_disabled=True`. Subsequent re-enables are no-ops unless called with `force=True`. ([L1060-L1085](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1060-L1085)) |

### Settings

| Symbol | Purpose |
|--------|---------|
| `ObservabilitySettings` | `pydantic_settings.BaseSettings` subclass. Reads env vars at construction time. ([L637-L901](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L637-L901)) |
| `OBSERVABILITY_SETTINGS` | Module-level singleton. Read `OBSERVABILITY_SETTINGS.enable_instrumentation`, `.enable_sensitive_data`, `.enable_console_exporters` to introspect state. ([L1007](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1007)) |

> [!NOTE]
> There is **no `is_instrumentation_enabled()` function**. To check state, read `OBSERVABILITY_SETTINGS.enable_instrumentation` directly. (Earlier versions of this KB cited a fabricated helper — it never existed.)

### Provider helpers (require `opentelemetry-sdk`)

| Symbol | Purpose |
|--------|---------|
| `create_resource(service_name=None, service_version=None, env_file_path=None, env_file_encoding=None, **attributes)` | Build an OTel `Resource` from env vars (`OTEL_SERVICE_NAME`, `OTEL_SERVICE_VERSION`, `OTEL_RESOURCE_ATTRIBUTES`) merged with explicit attributes. Returns `Resource`. ([L534-L609](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L534-L609)) |
| `create_metric_views()` | Returns the 3 default `View` objects: `View("agent_framework*")`, `View("gen_ai*")`, `View("*", aggregation=DropAggregation())` — i.e. only Agent Framework + GenAI metrics, drop everything else. ([L611-L626](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L611-L626)) |
| `get_tracer(instrumenting_module_name="agent_framework", instrumenting_library_version=..., schema_url=None, attributes=None)` | Thin wrapper over `opentelemetry.trace.get_tracer(...)`. Returns whatever the globally-configured `TracerProvider` returns — does **not** check `OBSERVABILITY_SETTINGS`. ([L904-L952](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L904-L952)) |
| `get_meter(name="agent_framework", version=..., schema_url=None, attributes=None)` | Thin wrapper over `opentelemetry.metrics.get_meter(...)`. Same behavior as `get_tracer` — not gated by `OBSERVABILITY_SETTINGS`. ([L955+](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L955)) |
| `workflow_tracer()` | Tracer used by workflow internals. **This** is the helper that gates on `OBSERVABILITY_SETTINGS.ENABLED` and returns `trace.NoOpTracer()` when disabled. ([L2337-L2340](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2337-L2340)) |

> [!NOTE]
> `disable_instrumentation()` short-circuits Agent Framework's own telemetry capture (the `ChatTelemetryLayer` / `AgentTelemetryLayer` / `workflow_tracer`). It does NOT make `get_tracer()` / `get_meter()` return no-ops — those continue to return whatever the globally-configured OTel providers return. If you call `get_tracer()` and create your own spans directly, they will still be exported.

### Workflow span helpers

| Symbol | Purpose |
|--------|---------|
| `create_workflow_span(name, attributes=None, kind=SpanKind.INTERNAL)` | Open a `workflow.*` span. Used internally by `Workflow.run` / `Workflow.run_stream`. |
| `create_processing_span(executor_id, executor_type, message_type, payload_type, source_trace_contexts=None, source_span_ids=None)` | Open an `executor.process` span. Optionally **links** to upstream spans for fan-in patterns. ([L2337-L2477](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2337-L2477)) |
| `create_edge_group_processing_span(edge_group_type, edge_group_id=None, message_source_id=None, message_target_id=None, source_trace_contexts=None, source_span_ids=None)` | Open an `edge_group.process` span. |
| `EdgeGroupDeliveryStatus` | Enum at [`observability.py:L2318-L2326`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2318-L2326). Members: `DELIVERED` (`"delivered"`), `DROPPED_TYPE_MISMATCH` (`"dropped type mismatch"`), `DROPPED_TARGET_MISMATCH` (`"dropped target mismatch"`), `DROPPED_CONDITION_FALSE` (`"dropped condition evaluated to false"`), `EXCEPTION` (`"exception"`), `BUFFERED` (`"buffered"`). Attribute value for `edge_group.delivery_status`. See [`observability-workflow-tracing.md`](../../patterns/observability-workflow-tracing.md#pattern-2-detect-dropped-messages) Pattern 2. |

> [!NOTE]
> `Workflow.run_stream` here refers to the framework's internal span-emitting path. User code calls `workflow.run(..., stream=True)`; the framework dispatches streaming internally.

### Telemetry layers (mixin classes — used by chat client and agent integrations)

These are framework internals. You generally do **not** instantiate them. They are listed here so you can recognize them in stack traces and source code.

| Symbol | Purpose |
|--------|---------|
| `ChatTelemetryLayer[OptionsCoT]` | Wraps `get_response` on chat clients. ([L1325-L1582](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1325-L1582)) |
| `EmbeddingTelemetryLayer` | Wraps embedding clients. |
| `AgentTelemetryLayer` | Wraps `Agent.run`. ([L1647-L1900](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1647-L1900)) `FoundryChatClient` uses `OTEL_PROVIDER_NAME = "azure.ai.foundry"` ([class var](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework_foundry/_chat_client.py)) and `Agent` uses `AGENT_PROVIDER_NAME = "microsoft.agent_framework"` ([`_agents.py:L657`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L657)). |

### Constants and enums

| Symbol | Notes |
|--------|-------|
| `OtelAttr(str, Enum)` | All OTel attribute name constants (~80 entries). E.g. `OtelAttr.OPERATION_NAME = "gen_ai.operation.name"`. ([L175-L308](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L175-L308)) |
| `ROLE_EVENT_MAP` | Maps `Message.role` ("system"/"user"/"assistant"/"tool") → `OtelAttr.*_MESSAGE` event name. |
| `FINISH_REASON_MAP` | Maps finish reason → OTel event finish_reason value. |
| `OTEL_ATTR_MAP` | Maps option name (e.g. `"system_name"`) → `(OtelAttr, default, is_sensitive, transform)`. ([L2068+](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2068)) |
| `TOKEN_USAGE_BUCKET_BOUNDARIES`, `OPERATION_DURATION_BUCKET_BOUNDARIES` | Histogram bucket boundaries for the two main GenAI metrics. |

> [!WARNING]
> `get_current_span()` and `start_as_current_span()` are **not** re-exported by `agent_framework.observability`. Use them directly from `opentelemetry.trace`:
> ```python
> from opentelemetry import trace
> tracer = trace.get_tracer(__name__)
> with tracer.start_as_current_span("my-span") as span:
>     ...
> ```
> (Earlier versions of this KB listed them as observability exports — they were never there.)

---

## Environment variables

### Agent Framework observability env vars

Read by `ObservabilitySettings` at module import time. Override with explicit `configure_otel_providers(...)` kwargs.

| Env var | Default | Effect |
|---------|---------|--------|
| `ENABLE_INSTRUMENTATION` | **`true`** in 1.6.0 (was `false` in 1.5.x) | Master switch. If `false`, the framework returns `NoOpTracer`/`NoOpMeter` from `get_tracer()` / `get_meter()` and the telemetry layers short-circuit. ([L645-L649](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L645-L649)) |
| `ENABLE_SENSITIVE_DATA` | `false` | When `true`, span attributes include `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` (prompt/completion/tool bodies). ([L653](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L653)) |
| `ENABLE_CONSOLE_EXPORTERS` | `false` | When `true` and you call `configure_otel_providers()`, also adds `ConsoleSpanExporter` + `ConsoleLogExporter` + `ConsoleMetricExporter`. Convenient for local debugging. ([L655](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L655)) |
| `VS_CODE_EXTENSION_PORT` | unset | If set (e.g. `4317`), `configure_otel_providers()` also wires OTLP exporters to `http://localhost:<port>` so traces flow to the [AI Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio) or [Azure AI Foundry](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-ai-foundry) VS Code extensions. ([L659](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L659)) |

> [!WARNING]
> Earlier versions of this KB documented env vars `AGENT_FRAMEWORK_INSTRUMENTATION_ENABLED` and `AGENT_FRAMEWORK_SENSITIVE_TELEMETRY_ENABLED` — **those names do not exist** in 1.8.0. Use `ENABLE_INSTRUMENTATION` / `ENABLE_SENSITIVE_DATA`.

### Standard OTel env vars (read by `configure_otel_providers`)

When `OTLP*_ENDPOINT` env vars are set, `configure_otel_providers()` automatically wires the corresponding OTLP exporters — no `exporters=` kwarg needed.

| Env var | Notes |
|---------|-------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base endpoint for all signals. ([L499-L505](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L499-L505)) |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Override per-signal for traces. |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Override per-signal for metrics. |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | Override per-signal for logs. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` (default), `http`, or `http/protobuf`. ([L507](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L507)) |
| `OTEL_EXPORTER_OTLP_HEADERS` | Comma-separated `k=v` pairs sent on every signal. |
| `OTEL_EXPORTER_OTLP_{TRACES,METRICS,LOGS}_HEADERS` | Per-signal override. ([L510-L516](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L510-L516)) |
| `OTEL_SERVICE_NAME` | Default `"agent_framework"`. Used by `create_resource()`. ([L599](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L599)) |
| `OTEL_SERVICE_VERSION` | Default = installed package version. |
| `OTEL_RESOURCE_ATTRIBUTES` | Comma-separated `k=v` pairs. Merged into resource. |

### User-agent telemetry (separate system)

Independent of observability. Lives in [`_telemetry.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_telemetry.py).

| Env var | Default | Effect |
|---------|---------|--------|
| `AGENT_FRAMEWORK_USER_AGENT_DISABLED` | unset (i.e. user-agent IS sent) | When `true`/`1`, the framework does NOT prepend `agent-framework-python/<version>` to outbound HTTP `User-Agent` headers. ([`_telemetry.py:L16-L17`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_telemetry.py#L16-L17)) |
| `FOUNDRY_HOSTING_ENVIRONMENT` | unset | When set, the framework auto-prefixes user-agent with `foundry-hosting/`. Auto-detected when the `azure.ai.agentserver.core` package is installed. ([`_telemetry.py:L30-L88`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_telemetry.py#L30-L88)) |

This is **not** the same as observability instrumentation — `disable_instrumentation()` does NOT affect user-agent reporting and vice versa. To disable both:
```bash
export ENABLE_INSTRUMENTATION=false
export AGENT_FRAMEWORK_USER_AGENT_DISABLED=true
```

---

## Sticky disable semantics

`disable_instrumentation()` is **sticky**. It sets a `_user_disabled` flag on `OBSERVABILITY_SETTINGS` that:

1. Prevents future writes to `OBSERVABILITY_SETTINGS.enable_instrumentation = True` from re-enabling
2. Makes `enable_instrumentation()`, `enable_sensitive_telemetry()`, and the auto-setup paths from library integrations **silent no-ops**
3. Logs an info message when ignored: `"enable_instrumentation() ignored: instrumentation was explicitly disabled via disable_instrumentation(). Pass force=True to re-enable."`

This is intentional — it lets the user's "I don't want telemetry" decision win against framework code that might otherwise re-enable instrumentation (e.g., when integrations are loaded later).

### Overriding the sticky disable

```python
from agent_framework.observability import (
    disable_instrumentation,
    enable_instrumentation,
    enable_sensitive_telemetry,
)

disable_instrumentation()           # sticky off

enable_instrumentation()            # NO-OP, logs "ignored"
enable_instrumentation(force=True)  # clears _user_disabled, enables

# OR
enable_sensitive_telemetry(force=True)  # also clears _user_disabled
```

> [!IMPORTANT]
> `disable_instrumentation()` does **not** tear down already-configured OTel providers or stop in-flight spans. It only gates *future* captures by Agent Framework instrumentation. Third-party instrumentation (`azure-monitor-opentelemetry`, `opentelemetry-instrumentation-*`) is unaffected.

---

## Span / metric / event catalog

### Spans

| Span name | When emitted | Key attributes |
|-----------|-------------|----------------|
| `chat <model>` | Each `ChatClient.get_response()` call | `gen_ai.operation.name="chat"`, `gen_ai.provider.name`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.response.id`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.request.{max_tokens,temperature,top_p,frequency_penalty,presence_penalty,seed,stop_sequences,top_k,choice.count}`, `gen_ai.response.finish_reasons` |
| `invoke_agent <agent>` | Each `Agent.run()` call | `gen_ai.operation.name="invoke_agent"`, `gen_ai.provider.name="microsoft.agent_framework"` (from `AGENT_PROVIDER_NAME`), `gen_ai.agent.name`, `gen_ai.agent.id`, `gen_ai.agent.description`, `gen_ai.conversation.id` |
| `execute_tool <tool>` | Each function/tool invocation | `gen_ai.operation.name="execute_tool"`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `agent_framework.function.name` |
| `embeddings <model>` | Each embedding request | `gen_ai.operation.name="embeddings"`, `gen_ai.request.encoding_formats` |
| `create_agent <agent>` | `Agent` construction | `gen_ai.operation.name="create_agent"`, `gen_ai.agent.{name,id,description}` |
| `workflow.build` | `WorkflowBuilder.build()` | `workflow_builder.name`, `workflow_builder.description`. Span events: `build.started`, `build.validation_completed`, `build.completed`, `build.error`. |
| `workflow.run` | `Workflow.run()` / `Workflow.run_stream()` | `workflow.id`, `workflow.name`, `workflow.description`, `workflow.definition`. Span events: `workflow.started`, `workflow.completed`, `workflow.error`. |
| `executor.process` | Each executor invocation inside a workflow | `executor.id`, `executor.type`, `message.type`, `message.payload_type`. Span links (not parent/child) when the executor consumes messages from multiple sources (fan-in). |
| `edge_group.process` | Each edge group fires | `edge_group.type`, `edge_group.id`, `edge_group.delivered` (bool), `edge_group.delivery_status` (`EdgeGroupDeliveryStatus` enum value). |
| `message.send` | Each message sent on an edge | `message.source_id`, `message.target_id`, `message.type`, `message.payload_type`, `message.destination_executor_id`. |

> [!NOTE]
> The `Workflow.run_stream` label above is internal span-emitter naming. User code calls `workflow.run(..., stream=True)`.

> [!NOTE]
> The `chat`, `invoke_agent`, etc. span name prefix is what shows up in trace viewers; the specific `<model>` / `<agent>` suffix is appended for readability. Trace queries should filter on `gen_ai.operation.name` (an indexed attribute), not on the span name string.

### Span events (only emitted when `ENABLE_SENSITIVE_DATA=true`)

| Event name | When | Body |
|-----------|------|------|
| `gen_ai.system.message` | Each system role message | message body |
| `gen_ai.user.message` | Each user role message | message body |
| `gen_ai.assistant.message` | Each assistant turn | message body + tool calls |
| `gen_ai.tool.message` | Each tool response | tool call ID + content |
| `gen_ai.choice` | Final assistant choice | finish_reason + message body |

These events are emitted by [`_record_messages_as_events`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L2160) on the chat span. The `gen_ai.input.messages` and `gen_ai.output.messages` span attributes (JSON-serialized full conversations) are also gated on `ENABLE_SENSITIVE_DATA`.

### Metrics (histograms)

| Metric name | Unit | Attributes | Buckets |
|-------------|------|-----------|---------|
| `gen_ai.client.token.usage` | `tokens` | `gen_ai.token.type` = `input` \| `output`, plus `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model` | `TOKEN_USAGE_BUCKET_BOUNDARIES` |
| `gen_ai.client.operation.duration` | `s` | Same as above | `OPERATION_DURATION_BUCKET_BOUNDARIES` |
| `agent_framework.function.invocation.duration` | `s` | `agent_framework.function.name`, plus error type if failed | default histogram buckets |

The exact attributes recorded on these metrics are listed in `GEN_AI_METRIC_ATTRIBUTES` (in [`observability.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py)).

### `gen_ai.system` vs `gen_ai.provider.name`

These are **two different attributes** and frequently confused:

| Attribute | Set from | Typical value |
|-----------|----------|---------------|
| `gen_ai.system` | `system_name` kwarg / `AGENT_FRAMEWORK_GEN_AI_SYSTEM` const | `"microsoft.agent_framework"` |
| `gen_ai.provider.name` | `OTEL_PROVIDER_NAME` ClassVar on the chat client / `AGENT_PROVIDER_NAME` on the agent | `"azure.ai.foundry"` (FoundryChatClient), `"microsoft.agent_framework"` (Agent) |

Use `gen_ai.provider.name` to slice traces by underlying provider (Foundry vs OpenAI vs Anthropic). Use `gen_ai.system` to identify the SDK/framework that emitted the span.

> [!WARNING]
> Earlier versions of this KB claimed `gen_ai.system = "azure.ai.foundry"` — that conflated the two. The provider IS `azure.ai.foundry` (under `gen_ai.provider.name`), but the system attribute is `microsoft.agent_framework`.

---

## Common configurations

### 1. Console output for local debugging

```python
import asyncio
from agent_framework.observability import configure_otel_providers
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async def main() -> None:
    # Easiest: set ENABLE_CONSOLE_EXPORTERS=true in .env and call configure_otel_providers()
    # with no args. The framework wires console exporters for traces/metrics/logs automatically.
    configure_otel_providers(enable_console_exporters=True)

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(project_endpoint="...", model="gpt-5-4", credential=cred)
        async with client.as_agent(name="echo", instructions="Echo input.") as agent:
            await agent.run("hello")
            # → console prints span: chat gpt-5-4 { gen_ai.operation.name=chat, ... }

asyncio.run(main())
```

### 2. OTLP collector via env vars only

```bash
# .env
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_SERVICE_NAME=my-agent-app
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=staging,team=ml
```

```python
from agent_framework.observability import configure_otel_providers
configure_otel_providers()   # picks up OTEL_* env vars automatically
```

### 3. Custom span exporter (parent demo3 pattern)

Source-of-truth example from `getting-started-with-agent-framework/src/demo3_hosted_mcp.py`:

```python
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from agent_framework.observability import configure_otel_providers


class _DemoSpanExporter(SpanExporter):
    def export(self, spans):
        for s in spans:
            attrs = dict(s.attributes or {})
            print(f"[trace] {s.name} attrs={attrs}")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


configure_otel_providers(exporters=[_DemoSpanExporter()])
```

### 4. Sensitive data capture (dev / local only)

```python
from agent_framework.observability import configure_otel_providers, enable_sensitive_telemetry

# Either via the kwarg:
configure_otel_providers(enable_sensitive_data=True)

# Or via the shortcut (also opts you in if you already configured providers):
enable_sensitive_telemetry()

# Or via env var:
# ENABLE_SENSITIVE_DATA=true
```

When enabled, span events include full prompt/completion/tool-arg bodies. **Never** turn this on in production — it captures user PII into your observability backend.

### 5. Disabling instrumentation in tests / CI

```python
# conftest.py
from agent_framework.observability import disable_instrumentation
disable_instrumentation()
```

Or via env var:
```bash
ENABLE_INSTRUMENTATION=false pytest tests/
```

### 6. VS Code AI Toolkit / Foundry extension

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers(vs_code_extension_port=4317)   # default AI Toolkit OTLP port
# Traces stream into the extension's Trace viewer while your script runs.
```

### 7. Azure Monitor / App Insights (production)

The supported recipe from the source docstring ([L1229-L1240](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1229-L1240)):

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import enable_sensitive_telemetry

# Azure Monitor sets up TracerProvider, MeterProvider, LoggerProvider with its own exporters.
configure_azure_monitor(connection_string="InstrumentationKey=...;...")

# Optional: opt into sensitive data (dev/staging only — leaks PII otherwise)
# enable_sensitive_telemetry()
```

> [!IMPORTANT]
> Do **not** also call `configure_otel_providers()` after `configure_azure_monitor()`. The OTel SDK only allows one global provider per signal — calling both creates conflicts where one silently wins.

See [`../../patterns/observability-azure-monitor.md`](../../patterns/observability-azure-monitor.md) for the end-to-end pattern including KQL queries and dashboard recipes.

---

## Custom metric views (filtering)

By default, `configure_otel_providers()` does NOT install any views — all metrics from any library flow through. To restrict to Agent Framework + GenAI metrics:

```python
from agent_framework.observability import configure_otel_providers, create_metric_views

configure_otel_providers(views=create_metric_views())
```

`create_metric_views()` returns:
```python
[
    View(instrument_name="agent_framework*"),
    View(instrument_name="gen_ai*"),
    View(instrument_name="*", aggregation=DropAggregation()),
]
```

Order matters: the wildcard `*` with `DropAggregation()` is last, so the two more-specific views match first.

To add your own views (e.g. histogram bucket overrides), prepend them:
```python
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

custom_view = View(
    instrument_name="gen_ai.client.token.usage",
    aggregation=ExplicitBucketHistogramAggregation(
        boundaries=(0, 100, 500, 1000, 5000, 10000, 50000, 100000),
    ),
)
configure_otel_providers(views=[custom_view, *create_metric_views()])
```

---

## Resource attributes

`create_resource()` builds the OTel `Resource` attached to all telemetry. By default it reads `OTEL_SERVICE_NAME`, `OTEL_SERVICE_VERSION`, `OTEL_RESOURCE_ATTRIBUTES` from env vars.

```python
from agent_framework.observability import create_resource

# Use defaults from env vars
resource = create_resource()

# Override
resource = create_resource(
    service_name="my-agent-app",
    service_version="1.2.3",
    deployment_environment="production",
    team="ml-platform",
)
```

> [!NOTE]
> `configure_otel_providers()` does **not** take a `resource=` kwarg — it builds the resource internally via `create_resource()` using whatever env vars are set. If you need a fully-custom resource, set up providers yourself (don't call `configure_otel_providers()`) and then call `enable_sensitive_telemetry()` to opt-in to sensitive capture.

---

## Per-chat-client `OTEL_PROVIDER_NAME`

Each concrete chat client class declares a `ClassVar OTEL_PROVIDER_NAME` that becomes the value of `gen_ai.provider.name` on its chat spans. The base `ChatTelemetryLayer` does **not** define this attribute itself; subclasses provide it:

| Class | `OTEL_PROVIDER_NAME` | Module |
|-------|----------------------|--------|
| `FoundryChatClient` | `"azure.ai.foundry"` | `agent_framework_foundry` |
| `OpenAIChatClient` | `"openai"` | `agent_framework.openai` |

> [!NOTE]
> `AzureOpenAIChatClient` is **not** exported by `agent_framework.openai` in 1.8.0 (verified: `dir(agent_framework.openai)` returns only `OpenAIChatClient`, `OpenAIChatCompletionClient`, `RawOpenAIChatClient`, `RawOpenAIChatCompletionClient` and their options classes). For Azure OpenAI deployments, use `OpenAIChatClient` with an `AsyncAzureOpenAI` instance, or use `FoundryChatClient`.

`OTEL_PROVIDER_NAME` is a **class attribute** set by the framework. The public constructors of `FoundryChatClient` and `OpenAIChatClient` do not expose an `otel_provider_name=` kwarg — `ChatTelemetryLayer.__init__` accepts one internally for subclass overrides, but it is not a user-facing API on the built-in concrete clients.

Similarly, `Agent` declares `AGENT_PROVIDER_NAME = "microsoft.agent_framework"` ([`_agents.py:L657`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L657)) which sets `gen_ai.provider.name` on `invoke_agent` spans. This is what distinguishes agent-level spans from chat-level spans when querying traces.

---

## How this page was verified

```python
# 1. Public exports
from agent_framework import observability as obs
print(sorted(x for x in dir(obs) if not x.startswith("_")))

# 2. configure_otel_providers signature
import inspect
print(inspect.signature(obs.configure_otel_providers))
# (*, enable_sensitive_data=None, enable_console_exporters=None, exporters=None,
#  views=None, vs_code_extension_port=None, env_file_path=None, env_file_encoding=None) -> None

# 3. FoundryChatClient.__init__ has NO instrumentation_enabled kwarg
from agent_framework.foundry import FoundryChatClient
print(list(inspect.signature(FoundryChatClient.__init__).parameters))
# ['self', 'project_endpoint', 'project_client', 'model', 'credential', 'allow_preview',
#  'default_headers', 'env_file_path', 'env_file_encoding', 'instruction_role',
#  'compaction_strategy', 'tokenizer', 'additional_properties', 'middleware',
#  'function_invocation_configuration']
#  ^ no `instrumentation_*` or `otel_*` parameter

# 4. is_instrumentation_enabled does not exist
try:
    from agent_framework.observability import is_instrumentation_enabled  # noqa
except ImportError as e:
    print("FABRICATED:", e)
# FABRICATED: cannot import name 'is_instrumentation_enabled' from 'agent_framework.observability'

# 5. Provider class vars
from agent_framework.foundry import FoundryChatClient, FoundryAgent
print(FoundryChatClient.OTEL_PROVIDER_NAME)  # azure.ai.foundry
print(FoundryAgent.AGENT_PROVIDER_NAME)      # microsoft.agent_framework
```

Run this against `agent-framework-foundry==1.8.0` to verify these claims locally.

---

## See also

- [`../../patterns/observability-otel.md`](../../patterns/observability-otel.md) — OTLP / console / custom exporter patterns
- [`../../patterns/observability-azure-monitor.md`](../../patterns/observability-azure-monitor.md) — production App Insights recipe
- [`../../patterns/observability-workflow-tracing.md`](../../patterns/observability-workflow-tracing.md) — interpreting workflow traces (executor/edge/message spans)
- [`../../anti-patterns/instrumentation-implicit-on-1.6.md`](../../anti-patterns/instrumentation-implicit-on-1.6.md) — the surprise modes
- [`devui.md`](devui.md) — DevUI's separate `instrumentation_enabled` param (different concept)
- [`clients.md`](clients.md) — `FoundryChatClient` (does NOT have `instrumentation_enabled` — opt-out is process-wide only)
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — the authoritative `gen_ai.*` attribute spec
- [PR #5865 — Instrumentation default ON](https://github.com/microsoft/agent-framework/pull/5865)
- Upstream source: [`observability.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py) (2477 LOC) + [`_telemetry.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_telemetry.py) (134 LOC)
