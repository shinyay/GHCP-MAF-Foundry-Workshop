# Anti-Pattern: Surprises with 1.6.0+ Default-On Instrumentation

> Status: **Active hazard** — new in 1.6.0 ([PR #5865](https://github.com/microsoft/agent-framework/pull/5865))
> Affects: 1.6.0 onward
> Severity: **Medium** — silent data exfil if you have an exporter you didn't configure intentionally; cost overhead per call
> Verified against: `agent-framework-foundry==1.8.0`, [`observability.py:L637-L1120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L637-L1120)

## Background — what changed in 1.6.0

| | 1.5.x and earlier | 1.6.0+ |
|---|---|---|
| `ENABLE_INSTRUMENTATION` default | `False` | **`True`** |
| `opentelemetry-sdk` dependency | Hard dep of `agent-framework-core` | Lazy-imported (must install yourself) |
| Telemetry without `configure_otel_providers()` | None | Spans flow IF any process configures providers |
| Disabling once-and-for-all | `enable_instrumentation()` toggleable | `disable_instrumentation()` is **sticky** unless `force=True` |

The new contract: AF's telemetry layers are **on** by default. They emit to the globally-configured OTel `TracerProvider`. If **any** code in the process registers an exporting provider (your own `configure_otel_providers()` / `configure_azure_monitor()`, a transitive dep, an Azure Functions worker host, etc.), AF spans will flow to that backend without you doing anything else. Setting `APPLICATIONINSIGHTS_CONNECTION_STRING` / `OTEL_EXPORTER_OTLP_ENDPOINT` env vars by themselves does NOT register a provider — but it does mean that any setup call elsewhere in the process will pick those values up.

---

## Hazard 1: Silent telemetry from leftover connection strings

### Symptom

You upgraded from 1.5.x to 1.6.0 and noticed:
- App Insights workspace started receiving traces from agents you didn't expect.
- Agent runs got slightly slower (5-50 ms per call) for no obvious code change.
- You see `chat <model>` and `invoke_agent <agent>` spans in workspaces you never enabled.

### ❌ Wrong assumption

```python
# WRONG mental model carried over from 1.5.x:
# "I didn't call configure_otel_providers(), so no telemetry is collected."

import os
os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = "..."   # left over from another project
# ... an upstream library / app entry point calls configure_azure_monitor() based on that env var ...
# Surprise: AF spans flow to the workspace pointed at by the env var, because the layers are on by default.
```

### Why it's wrong

`ENABLE_INSTRUMENTATION` defaults to `True` in 1.6.0. AF's `ChatTelemetryLayer` / `AgentTelemetryLayer` / `workflow_tracer()` are active out of the box. The env var by itself does NOT register a provider — but if **anything** in the process (a transitive dep, a parent framework, an old snippet) calls `configure_azure_monitor()` or `configure_otel_providers()`, it picks up `APPLICATIONINSIGHTS_CONNECTION_STRING` and starts shipping spans, and AF's hooks happily emit to it.

The trap is the **combination**: env var leftover + something-somewhere calling a provider-setup function. AF made the layers on by default in 1.6, so that "something" no longer needs to be your own code.

### ✅ Right

```python
# In CI / tests / sandbox: explicit opt-out at startup
from agent_framework.observability import disable_instrumentation

disable_instrumentation()   # MUST be called BEFORE any client/agent construction

from agent_framework.foundry import FoundryChatClient
# ... agent code; no spans will be emitted by Agent Framework hooks ...
```

```python
# In production: explicit opt-IN with the exporter you actually want
import os
from azure.monitor.opentelemetry import configure_azure_monitor

cs = os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]   # KeyError if missing, fail fast
configure_azure_monitor(connection_string=cs)
# Do NOT also call configure_otel_providers() — see Hazard 4 below.
```

### How to detect

```python
import os
from agent_framework.observability import OBSERVABILITY_SETTINGS

if OBSERVABILITY_SETTINGS.enable_instrumentation:
    cs = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if cs or otlp:
        print(f"[observability] ENABLED. Exports may flow to: AppInsights={bool(cs)}, OTLP={otlp}")
    else:
        print("[observability] Hooks active but no exporter detected — spans will be dropped.")
else:
    print("[observability] disabled (good for CI / tests).")
```

> [!IMPORTANT]
> Use `OBSERVABILITY_SETTINGS.enable_instrumentation` (a property on the singleton), **NOT** a function called `is_instrumentation_enabled()` — that function does not exist in the public API. Earlier KB versions documented it; that was a fabrication.

---

## Hazard 2: `disable_instrumentation()` is sticky

### Symptom

```python
from agent_framework.observability import disable_instrumentation, enable_instrumentation

disable_instrumentation()
# ... later in the same process ...
enable_instrumentation()   # ← LOOKS like it re-enables. Doesn't.

# Agent runs produce no spans. You scratch your head for an hour.
```

### Why it's wrong

`disable_instrumentation()` sets both `_enable_instrumentation = False` AND a separate sticky flag `_user_disabled = True`. After that:
- All future writes to `OBSERVABILITY_SETTINGS.enable_instrumentation` are **silently dropped**.
- `enable_instrumentation()` becomes a no-op and logs an INFO message.
- `enable_sensitive_telemetry()` similarly no-ops.

Verified at [`observability.py:L693-L700`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L693-L700) (setter dropping writes when `_user_disabled`) and [`observability.py:L1086-L1120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L1086-L1120) (`enable_instrumentation` body).

### ✅ Right

```python
from agent_framework.observability import enable_instrumentation

# To recover from a sticky disable, you must pass force=True:
enable_instrumentation(force=True)
```

Or just don't toggle in the same process — pick one decision at startup.

### How to detect

If `OBSERVABILITY_SETTINGS.enable_instrumentation` is `False` immediately after a call to `enable_instrumentation()`, you're hitting this sticky path. Check by running with `LOG_LEVEL=INFO`:

```
INFO  agent_framework.observability: Instrumentation has been explicitly disabled via disable_instrumentation. Use force=True to re-enable.
```

---

## Hazard 3: `disable_instrumentation()` doesn't tear down providers

### Symptom

You call `disable_instrumentation()` to silence Agent Framework, but spans **still** flow to your backend.

### Why it's wrong

`disable_instrumentation()` only gates the framework's own capture paths. It does NOT:
- Tear down any registered `TracerProvider` / `MeterProvider` / `LoggerProvider`.
- Stop in-flight spans from being flushed.
- Stop third-party instrumentation libraries (`opentelemetry-instrumentation-httpx`, `opentelemetry-instrumentation-requests`, etc.) from emitting their own HTTP spans for the API calls the agent makes underneath.

So your App Insights still shows HTTP dependency spans for OpenAI/Foundry endpoints, even though `chat <model>` and `invoke_agent <agent>` go silent.

### ✅ Right — pick the right tool

```python
# To silence Agent Framework only:
from agent_framework.observability import disable_instrumentation
disable_instrumentation()

# To stop ALL OTel telemetry process-wide:
# - Don't call configure_azure_monitor() / configure_otel_providers().
# - Unset OTEL_EXPORTER_OTLP_ENDPOINT and APPLICATIONINSIGHTS_CONNECTION_STRING.
# - Uninstall opentelemetry-instrumentation-* packages if pulled in transitively.
```

---

## Hazard 4: Double-registering providers (Azure Monitor + `configure_otel_providers`)

### Symptom

You wire up Azure Monitor for App Insights AND also call `configure_otel_providers()` to add a console exporter. Some signals (often metrics) silently stop flowing to App Insights.

### ❌ Wrong

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import configure_otel_providers
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

configure_azure_monitor(connection_string=cs)            # registers ProviderA
configure_otel_providers(exporters=[ConsoleSpanExporter()])  # registers ProviderB — collides
```

### Why it's wrong

The OTel SDK only honors ONE global `TracerProvider`/`MeterProvider`/`LoggerProvider` per process. The second `set_*_provider()` call either replaces the first or is rejected with a warning, depending on SDK version. Either way you lose telemetry from one configuration.

### ✅ Right

Pick **one** entry point:

```python
# Production: Azure Monitor only
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import enable_sensitive_telemetry

configure_azure_monitor(connection_string=cs)
if os.environ.get("ENABLE_SENSITIVE_DATA"):
    enable_sensitive_telemetry()
```

```python
# Dev: console only
from agent_framework.observability import configure_otel_providers

configure_otel_providers(enable_console_exporters=True, enable_sensitive_data=True)
```

See [`observability-azure-monitor.md`](../patterns/observability-azure-monitor.md) and [`observability-otel.md`](../patterns/observability-otel.md).

---

## Hazard 5: Console exporter in production (volume blowup)

### Symptom

A developer leaves `ENABLE_CONSOLE_EXPORTERS=true` in a `.env` checked into Git. A production deployment inherits it. Logs become unreadable — every chat call dumps full spans (often 100+ lines per turn) to stdout.

### ❌ Wrong

```bash
# .env shared via Git
ENABLE_CONSOLE_EXPORTERS=true
ENABLE_SENSITIVE_DATA=true
```

### Why it's wrong

Each agent turn produces multiple spans (`invoke_agent`, `chat`, `execute_tool` x N), each with 10-30 attributes. With `enable_sensitive_data=True`, full message bodies are logged. In production this floods structured log pipelines (Datadog, Loki, App Insights logs), drives up storage cost, and risks PII exposure in log search.

### ✅ Right

```bash
# .env.example (template only — committed)
# ENABLE_CONSOLE_EXPORTERS=false  # do not enable in production

# .env (gitignored — local override)
ENABLE_CONSOLE_EXPORTERS=true
ENABLE_SENSITIVE_DATA=true
```

Or programmatically gate on environment:

```python
from agent_framework.observability import configure_otel_providers

is_dev = os.environ.get("APP_ENV") == "dev"
configure_otel_providers(
    enable_console_exporters=is_dev,
    enable_sensitive_data=is_dev,
)
```

---

## Hazard 6: Treating `ENABLE_INSTRUMENTATION` and friends as Agent Framework env vars

### ❌ Wrong

```bash
# Names from earlier KB versions / mistaken docs
AGENT_FRAMEWORK_INSTRUMENTATION_ENABLED=false
AGENT_FRAMEWORK_SENSITIVE_TELEMETRY_ENABLED=true
```

### Why it's wrong

The actual env var names are **not** prefixed with `AGENT_FRAMEWORK_`. Verified at [`observability.py:L637-L740`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L637-L740):

| Real env var | Default |
|---|---|
| `ENABLE_INSTRUMENTATION` | `true` |
| `ENABLE_SENSITIVE_DATA` | `false` |
| `ENABLE_CONSOLE_EXPORTERS` | `false` |
| `VS_CODE_EXTENSION_PORT` | unset |

### ✅ Right

```bash
ENABLE_INSTRUMENTATION=false   # process-wide off (alternative to disable_instrumentation())
ENABLE_SENSITIVE_DATA=true     # dev only
```

---

## Quick decision table

| Want to... | Do this |
|------------|---------|
| Disable Agent Framework spans process-wide (sticky) | `disable_instrumentation()` BEFORE any client/agent construction |
| Re-enable after a sticky disable | `enable_instrumentation(force=True)` |
| Disable via env var instead | `export ENABLE_INSTRUMENTATION=false` |
| Send to App Insights | `configure_azure_monitor(connection_string=cs)` — see [pattern](../patterns/observability-azure-monitor.md) |
| Send to OTLP collector | env vars only: `OTEL_EXPORTER_OTLP_ENDPOINT=...` then `configure_otel_providers()` — see [pattern](../patterns/observability-otel.md) |
| Add console output for debugging | `configure_otel_providers(enable_console_exporters=True)` |
| Capture prompts/completions | `enable_sensitive_telemetry()` OR `enable_sensitive_data=True` kwarg — DEV ONLY |
| Detect surprise observability at startup | check `OBSERVABILITY_SETTINGS.enable_instrumentation` + presence of `APPLICATIONINSIGHTS_CONNECTION_STRING` / `OTEL_EXPORTER_OTLP_ENDPOINT` env vars |

---

## See also

- [Pattern — `observability-otel.md`](../patterns/observability-otel.md)
- [Pattern — `observability-azure-monitor.md`](../patterns/observability-azure-monitor.md)
- [API ref — `observability.md`](../api-reference/1.8.0/observability.md)
- [Migration — `from-1.5-to-1.6.md`](../migration-guides/from-1.5-to-1.6.md)
- [PR #5865 (instrumentation default ON, BREAKING)](https://github.com/microsoft/agent-framework/pull/5865)
- Upstream source: [`observability.py:L693-L700`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/observability.py#L693-L700) (sticky disable mechanism)
