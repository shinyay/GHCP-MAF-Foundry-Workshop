# Pattern: OpenTelemetry Configuration (OTLP / Console / Custom)

> Status: **Stable** core API; specific exporters are external packages.
> Verified against: `agent-framework-foundry==1.8.0`, `opentelemetry-sdk>=1.27.0`, parent `src/demo3_hosted_mcp.py` (custom `SpanExporter`)
> Pinned: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/packages/core/agent_framework)

## Goal

Wire Agent Framework telemetry to **vendor-agnostic OpenTelemetry backends** — OTLP collector, console, or custom exporter. For **Azure App Insights**, see [`observability-azure-monitor.md`](observability-azure-monitor.md) (different recipe, uses `configure_azure_monitor()` instead of `configure_otel_providers()`).

## When to use

| Scenario | Use this pattern |
|----------|------------------|
| OSS observability stack (Jaeger, Grafana Tempo, Honeycomb, etc.) | ✅ — point OTLP exporters at your collector |
| Local console output for debugging a single run | ✅ — `enable_console_exporters=True` |
| Custom in-process span sink for tests or demos | ✅ — pass `exporters=[CustomExporter()]` |
| Azure App Insights | ❌ — use [`observability-azure-monitor.md`](observability-azure-monitor.md) instead |
| OpenAI/Anthropic-direct (no Foundry, no Azure) | ✅ — same recipe; the chat client emits the same `gen_ai.*` attributes |

## Prerequisites

```bash
pip install agent-framework-foundry==1.8.0
pip install opentelemetry-sdk>=1.27.0                # required to register your own providers
pip install opentelemetry-exporter-otlp-proto-grpc   # only for OTLP recipes below
```

The repo's `requirements.txt` already pins `opentelemetry-sdk` so it's always available, even though it's no longer a hard dependency of `agent-framework-core` since 1.6.0.

## Configuration paths

`configure_otel_providers()` is the **single entry point**. There is no "bring your own TracerProvider" kwarg — you can only:

1. Let it auto-create providers (default), OR
2. Pass specific `exporters=[...]` to add to its providers, OR
3. Set up providers yourself (don't call `configure_otel_providers()`) and call `enable_sensitive_telemetry()` if you need sensitive data capture.

```python
# Signature (verified via inspect.signature)
def configure_otel_providers(
    *,
    enable_sensitive_data: bool | None = None,
    enable_console_exporters: bool | None = None,
    exporters: list[LogRecordExporter | SpanExporter | MetricExporter] | None = None,
    views: list[View] | None = None,
    vs_code_extension_port: int | None = None,
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
) -> None: ...
```

> [!IMPORTANT]
> There is **no `tracer_provider=` kwarg**. Earlier KB versions documented `configure_otel_providers(tracer_provider=provider)` — that was a fabrication. The function ALWAYS creates its own providers via `create_resource()` internally. To use your own providers, don't call this function at all; configure providers directly with OTel SDK calls and rely on Agent Framework's default-on instrumentation.

---

## Recipe 1: Console exporter (debug, fastest setup)

```python
# console_observability.py
import asyncio

from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import configure_otel_providers
from azure.identity.aio import AzureCliCredential


async def main() -> None:
    # Easiest path: framework wires Console{Span,Log,Metric}Exporter automatically.
    configure_otel_providers(enable_console_exporters=True)

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(project_endpoint="...", model="gpt-5-4", credential=cred)
        async with client.as_agent(name="echo", instructions="Echo input.") as agent:
            await agent.run("hello")
            # → prints span: chat gpt-5-4 { gen_ai.operation.name=chat, ... }
            # → prints span: invoke_agent echo  { gen_ai.operation.name=invoke_agent, ... }


asyncio.run(main())
```

Or via env var (still requires the `configure_otel_providers()` call — the env var only flips the default for the `enable_console_exporters` kwarg):
```bash
export ENABLE_CONSOLE_EXPORTERS=true
python my_agent.py   # script must still call configure_otel_providers()
```

> [!IMPORTANT]
> Setting `ENABLE_CONSOLE_EXPORTERS=true` does **not** automatically register a console exporter. The framework reads this env var inside `ObservabilitySettings` when `configure_otel_providers()` runs — without that call, no provider is set up and no spans go anywhere. Same for `APPLICATIONINSIGHTS_CONNECTION_STRING`: it does nothing until something calls `configure_azure_monitor()`.

---

## Recipe 2: OTLP collector via env vars

The framework reads `OTEL_EXPORTER_OTLP_*` env vars automatically — no `exporters=[...]` argument needed.

```bash
# .env
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.observability:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_SERVICE_NAME=my-agent-app
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=staging,team=ml-platform
```

```python
# otlp_observability.py
from agent_framework.observability import configure_otel_providers

configure_otel_providers()   # picks up OTEL_EXPORTER_OTLP_* and OTEL_SERVICE_NAME from env

# ... rest of agent code unchanged
```

Per-signal endpoint override (e.g. metrics go to Prometheus, traces go to Tempo):
```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://tempo:4317
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://prometheus:4318
OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http
```

For HTTP/OTLP instead of gRPC:
```bash
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

---

## Recipe 3: Custom span exporter (the parent demo3 pattern)

Source-of-truth: `getting-started-with-agent-framework/src/demo3_hosted_mcp.py` lines 84-118. This demo pushes spans through an in-process exporter so you can see exactly what attributes flow per call:

```python
# custom_exporter_observability.py
from __future__ import annotations

import asyncio
from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import configure_otel_providers
from azure.identity.aio import AzureCliCredential


class DemoSpanExporter(SpanExporter):
    """Print spans to stdout instead of sending them anywhere."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for s in spans:
            attrs = dict(s.attributes or {})
            print(f"[trace] name={s.name} duration_ms={(s.end_time - s.start_time) / 1e6:.1f}")
            for k in ("gen_ai.operation.name", "gen_ai.request.model",
                      "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"):
                if k in attrs:
                    print(f"  {k}={attrs[k]}")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


async def main() -> None:
    configure_otel_providers(exporters=[DemoSpanExporter()])

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(project_endpoint="...", model="gpt-5-4", credential=cred)
        async with client.as_agent(name="echo", instructions="Echo input.") as agent:
            await agent.run("Say hi.")


asyncio.run(main())
```

You can pass the same custom exporter alongside env-driven OTLP exporters — they are additive.

---

## Recipe 4: VS Code AI Toolkit / Foundry extension

The [AI Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio) and [Azure AI Foundry](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-ai-foundry) VS Code extensions listen on an OTLP port (default `4317`) for in-IDE trace visualization.

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers(vs_code_extension_port=4317)
# Equivalent to OTLP exporter pointing at http://localhost:4317
```

Or set the env var:
```bash
export VS_CODE_EXTENSION_PORT=4317
python my_agent.py
```

The traces stream into the extension's "Tracing" view in real time.

---

## Recipe 5: Sensitive data capture (dev only)

By default, prompts/completions/tool args are **NOT** in span attributes (only metadata: model, token counts, finish reasons). To capture full content for debugging:

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers(
    enable_console_exporters=True,
    enable_sensitive_data=True,   # ← prompts/completions in span events
)
```

Or as a follow-on after providers are configured by something else (e.g. Azure Monitor):
```python
from agent_framework.observability import enable_sensitive_telemetry
enable_sensitive_telemetry()
```

When enabled, the chat span gets these event records:

| Event name | Body |
|-----------|------|
| `gen_ai.system.message` | system message body |
| `gen_ai.user.message` | user message body |
| `gen_ai.assistant.message` | assistant turn (with tool calls) |
| `gen_ai.tool.message` | tool response |
| `gen_ai.choice` | finish_reason + final assistant message |

> [!WARNING]
> **Never** enable in production. This puts user PII / business secrets / customer data into your observability backend.

---

## Recipe 6: Metric views (filter what's collected)

By default `configure_otel_providers()` does NOT install views — all metrics from any library flow through. To restrict to Agent Framework metrics only:

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

To add custom bucket boundaries on a specific metric:
```python
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

custom = View(
    instrument_name="gen_ai.client.token.usage",
    aggregation=ExplicitBucketHistogramAggregation(
        boundaries=(0, 100, 500, 1000, 5000, 10000, 50000, 100000),
    ),
)
configure_otel_providers(views=[custom, *create_metric_views()])
```

Order matters: more-specific views first; the wildcard `DropAggregation()` view from `create_metric_views()` is last so it doesn't catch your custom view.

---

## Why each piece

| Piece | Why |
|-------|-----|
| `configure_otel_providers(...)` | Single call that wires `TracerProvider`, `MeterProvider`, `LoggerProvider` with your exporters, sets the global OTel resource, and flips `OBSERVABILITY_SETTINGS.enable_instrumentation = True`. |
| `enable_sensitive_data=True` | Opts you into capturing message bodies/tool args. Off by default for PII safety. |
| `enable_console_exporters=True` | Adds `ConsoleSpanExporter` + `ConsoleLogExporter` + `ConsoleMetricExporter` regardless of `exporters=` arg. |
| `exporters=[...]` | Custom exporters added to the providers. Compatible with `SpanExporter`, `LogRecordExporter`, `MetricExporter` instances. |
| `views=create_metric_views()` | Restricts metrics to Agent Framework + GenAI; drops everything else (third-party libs, etc.). |
| `vs_code_extension_port=4317` | Wires an OTLP exporter to `http://localhost:4317` for IDE-level trace viewers. |

## Verification

```python
# Verify settings reflect your config
from agent_framework.observability import OBSERVABILITY_SETTINGS

print(OBSERVABILITY_SETTINGS.enable_instrumentation)   # True after configure_otel_providers()
print(OBSERVABILITY_SETTINGS.enable_sensitive_data)    # whatever you set
print(OBSERVABILITY_SETTINGS.enable_console_exporters) # whatever you set
```

Run an agent and look for spans named `chat <model>`, `invoke_agent <agent>`, `execute_tool <tool>`. If no spans appear:

| Symptom | Likely cause |
|---------|--------------|
| No spans at all | You called `disable_instrumentation()` somewhere; or `ENABLE_INSTRUMENTATION=false`; or `configure_otel_providers()` was not called and no `OTEL_EXPORTER_OTLP_*` env vars are set. |
| Spans created but no exporter receives them | You configured providers BEFORE calling `configure_otel_providers()` — the framework's provider overwrites yours. Pick one or the other. |
| `ModuleNotFoundError: opentelemetry.sdk` | `pip install opentelemetry-sdk`. |
| Spans missing `gen_ai.input.messages` etc. | `enable_sensitive_data` is `False` (default). Set `ENABLE_SENSITIVE_DATA=true` or `enable_sensitive_telemetry()`. |
| `gen_ai.provider.name` shows `"unknown"` | The chat client class is missing `OTEL_PROVIDER_NAME` ClassVar. Built-in clients (`FoundryChatClient`, `OpenAIChatClient`, etc.) all set this. |

---

## Common mistakes

| Mistake | Correction |
|---------|-----------|
| Setting up your own `TracerProvider` AND calling `configure_otel_providers()` | Pick one. Calling both creates competing providers; the OTel SDK only honors one global per signal type. |
| Calling `configure_otel_providers()` multiple times | Source warns against this — `_executed_setup` may re-execute but provider double-registration is undefined. Configure once at startup. |
| Using `enable_sensitive_telemetry=` as a kwarg to `configure_otel_providers()` | That kwarg name **does not exist**. The correct kwarg is `enable_sensitive_data=True`. Or call `enable_sensitive_telemetry()` separately. |
| Using `tracer_provider=` kwarg to `configure_otel_providers()` | That kwarg **does not exist**. The function creates providers internally. To use your own, don't call this function. |
| Calling `configure_otel_providers()` after `configure_azure_monitor()` | Double-setup of providers; one silently wins. Use [`observability-azure-monitor.md`](observability-azure-monitor.md) recipe instead. |
| Expecting `disable_instrumentation()` to tear down already-configured exporters | It only gates *future* captures by Agent Framework. Existing in-flight spans and third-party instrumentation (e.g. `opentelemetry-instrumentation-httpx`) keep flowing. |
| Calling `enable_instrumentation()` after `disable_instrumentation()` | No-op by design (sticky). Use `enable_instrumentation(force=True)`. |

## See also

- [`../api-reference/1.8.0/observability.md`](../api-reference/1.8.0/observability.md) — full API surface, env vars, span/metric catalog
- [`observability-azure-monitor.md`](observability-azure-monitor.md) — production App Insights pattern (different recipe)
- [`observability-workflow-tracing.md`](observability-workflow-tracing.md) — interpreting workflow/executor/edge spans
- [`../anti-patterns/instrumentation-implicit-on-1.6.md`](../anti-patterns/instrumentation-implicit-on-1.6.md) — surprise modes
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- Upstream source: [`observability.py:L1122-L1298`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1122-L1298) (configure_otel_providers)
