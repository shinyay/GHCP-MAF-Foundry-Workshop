# Migration Guide: 1.5.x → 1.6.0

> Released: May 19, 2026
> Pinned in this template: `agent-framework-foundry==1.6.0` (this document covers the upgrade from 1.5.x to 1.6.0; current template pin is `==1.8.0`)
> Upstream release notes: [python-1.6.0](https://github.com/microsoft/agent-framework/releases/tag/python-1.6.0)

> [!NOTE]
> **Doc location migration.** This is a historical migration guide. The KB folder was renamed from `kb/api-reference/1.6.0/` to `kb/api-reference/1.8.0/` during the template spawn, so cross-links below point to `1.8.0/` paths (the current file location); the content these pages document is still the relevant 1.6.0 API surface where called out by line context.

## TL;DR

| Change | Severity | Action |
|--------|---------|--------|
| Instrumentation is enabled by default | **Behavior change** | Add `disable_instrumentation()` if you don't want it |
| `opentelemetry-sdk` is no longer a hard dependency | **Dep change** | Make sure your transitive deps still bring it in (or add it explicitly) |
| New experimental factories under `client.get_*_tool()` | Additive | None required; opt in if useful |
| New `client.get_shell_tool()` (local + Docker shell) | **Additive** + **security** | Use with allow-listing; see [`tools-shell.md`](../api-reference/1.8.0/tools-shell.md) |
| `agent-framework-monty` package introduced | **Additive** | Optional add-on for orchestration helpers |
| Various exception messages improved | Cosmetic | Update string-match-based handling if you rely on exact text |

No removals or signature changes for the canonical `client.as_agent(...)` / `WorkflowBuilder(...)` paths.

---

## 1. Instrumentation default = ON (PR #5865)

**Before (1.5.x):** Instrumentation was opt-in.

```python
from agent_framework.observability import configure_otel_providers
configure_otel_providers()    # required to see spans
```

**After (1.6.0):** Instrumentation is **on by default**. The framework registers OTel hooks at import time.

```python
# No call required — spans flow automatically as long as an exporter is configured.
```

### Implications

- The framework's chat/agent/workflow telemetry **layers** are active by default, but spans go to the **globally-registered** OTel `TracerProvider`. Without explicit setup (`configure_otel_providers()` or `configure_azure_monitor()` or your own SDK wiring), the global provider is the OTel default proxy — spans land in `NoOpTracer` and disappear.
- If you call `configure_azure_monitor(connection_string=cs)` OR `configure_otel_providers(...)` anywhere in your process, telemetry starts flowing — including from any chat client / agent / workflow imported after that point.
- `APPLICATIONINSIGHTS_CONNECTION_STRING` set in your environment does NOT auto-route spans by itself; it is read when something calls `configure_azure_monitor()`. The risk is that a third-party library or a left-over snippet calls `configure_azure_monitor()` from os env, and you don't notice.
- To make telemetry behavior obvious in 1.6.0, call `disable_instrumentation()` **before** any client/agent construction in environments where you do not want capture (tests, CI dry-runs).
- See [`../anti-patterns/instrumentation-implicit-on-1.6.md`](../anti-patterns/instrumentation-implicit-on-1.6.md) for the surprise modes.

### Migration step

Decide your intent and be explicit:

| Intent | Code |
|--------|------|
| I want telemetry → App Insights | `configure_azure_monitor(connection_string=...)` (do NOT also call `configure_otel_providers`) — see [`../patterns/observability-azure-monitor.md`](../patterns/observability-azure-monitor.md) |
| I want telemetry → console (dev) | `configure_otel_providers(enable_console_exporters=True)` |
| I want telemetry → OTLP collector | Set `OTEL_EXPORTER_OTLP_ENDPOINT=...` then `configure_otel_providers()` |
| I want telemetry → custom exporter | `configure_otel_providers(exporters=[MySpanExporter()])` |
| I do NOT want telemetry | `from agent_framework.observability import disable_instrumentation; disable_instrumentation()` (call BEFORE any client/agent construction; **sticky** — use `enable_instrumentation(force=True)` to undo) |

In tests / CI, **always** call `disable_instrumentation()` at startup to avoid surprises.

---

## 2. `opentelemetry-sdk` no longer a hard dep

**Before (1.5.x):** `agent-framework-core` pinned `opentelemetry-sdk` as a transitive dep, so it was always present.

**After (1.6.0):** Removed from the hard requires. Users must bring their own OTel stack.

### Implications

- If you ran `pip install agent-framework-foundry==1.6.0 --no-deps` (or used a strict dependency resolver), you'll see:
  ```
  ImportError: No module named 'opentelemetry.sdk'
  ```
- Most users won't notice — `azure-monitor-opentelemetry` brings it in transitively.

### Migration step

In `requirements.txt`, add `opentelemetry-sdk` explicitly if you don't already depend on Azure Monitor:

```
opentelemetry-sdk>=1.27.0
```

Or, if you use Azure Monitor:

```
azure-monitor-opentelemetry>=1.6.0   # brings in opentelemetry-sdk transitively
```

---

## 3. New experimental hosted tool factories

The 1.6.0 `FoundryChatClient` now exposes (all experimental):

| Factory | Status | Notes |
|---------|--------|-------|
| `get_a2a_tool(...)` | Experimental | Agent-to-Agent protocol (Foundry side preview) |
| `get_browser_automation_tool(...)` | Experimental | Browser automation hosted runtime |
| `get_computer_use_tool(...)` | Experimental | Computer use (mouse/keyboard control) |
| `get_fabric_tool(...)` | Experimental | Microsoft Fabric integration |
| `get_memory_search_tool(...)` | Experimental | Hosted memory store search |
| `get_sharepoint_tool(...)` | Experimental | SharePoint connector |
| `get_shell_tool(...)` | **New** + Experimental | Local or Docker-isolated shell execution |
| `get_bing_custom_search_tool(...)` | Experimental | Bing Custom Search (vs the general Bing Grounding) |

### Migration step

None required. Opt in by calling the factory and adding to `tools=[...]`. All experimental tools are documented in [`tools-hosted.md`](../api-reference/1.8.0/tools-hosted.md).

> [!WARNING]
> Experimental APIs may change signature between minor releases. Pin to a specific version and re-check on every bump.

---

## 4. Shell tool — security note

`client.get_shell_tool(...)` lets your agent run shell commands. **This is dangerous**:
- Local mode: full access to the host's shell.
- Docker mode: isolated to a container (safer but still capable of network egress).

### Migration step

If you adopt the Shell tool:

1. Use the **Docker** mode (isolated execution) instead of local.
2. Use the tool's `allowed_commands=[...]` parameter to allow-list only what you need.
3. Never expose a shell-tool-enabled agent through unauthenticated DevUI.

See [`tools-shell.md`](../api-reference/1.8.0/tools-shell.md) for full safety guidance.

---

## 5. `agent-framework-monty` (optional)

A new optional add-on package providing additional orchestration helpers (multi-agent compaction, memory stores, etc.). Not required for typical Foundry usage.

```bash
pip install agent-framework-monty==1.6.0
```

(This is also "experimental" — pin tightly.)

---

## Validation checklist after upgrade

```bash
# 1. Reinstall cleanly:
pip install --upgrade --force-reinstall agent-framework-foundry==1.6.0

# 2. Verify imports work:
python -c "from agent_framework.foundry import FoundryChatClient; print('OK')"

# 3. Verify your existing scripts still run:
python -m compileall -q src/

# 4. Smoke test one agent:
python src/demo1_run_agent.py

# 5. Inspect observability — either you have an exporter or you've disabled it.
python -c "from agent_framework.observability import OBSERVABILITY_SETTINGS; print('inst on:', OBSERVABILITY_SETTINGS.enable_instrumentation)"
```

## See also

- [`cumulative-since-1.0.md`](cumulative-since-1.0.md) — all changes since 1.0 GA
- [`../anti-patterns/instrumentation-implicit-on-1.6.md`](../anti-patterns/instrumentation-implicit-on-1.6.md)
- [`../patterns/observability-otel.md`](../patterns/observability-otel.md)
- [`../patterns/observability-azure-monitor.md`](../patterns/observability-azure-monitor.md)
- [`../api-reference/1.8.0/observability.md`](../api-reference/1.8.0/observability.md)
- [Microsoft Agent Framework Releases](https://github.com/microsoft/agent-framework/releases)
