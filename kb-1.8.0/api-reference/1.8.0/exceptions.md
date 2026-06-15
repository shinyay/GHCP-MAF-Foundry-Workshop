# Exceptions

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: introspection of `agent_framework.exceptions` + parent demos 2, 3, 4, 5, 7, 8

Agent Framework exposes a single exception root — `AgentFrameworkException` — with a sub-hierarchy that lets you catch granular failure modes.

---

## Hierarchy

```
AgentFrameworkException                       ← catch-all root
├── AgentException
│   ├── AgentExecutionException
│   ├── AgentInitializationException
│   └── AgentInvalidResponseException
├── ChatClientException
│   ├── ChatClientInitializationException
│   ├── ChatClientInvalidRequestException
│   └── ChatClientInvalidResponseException    ← model-side problems (most common)
├── ContentError
│   ├── ContentFilterException                ← model returned a content-policy refusal
│   ├── AdditionalPropertiesTypeException
│   └── ContentSerializationException
├── IntegrationException
│   └── IntegrationExecutionException         ← errors from custom integrations
├── MiddlewareException
│   ├── MiddlewareInvalidConfigurationException
│   └── MiddlewareExecutionException
├── SettingNotFoundError                       ← missing required env var / setting
├── ToolException
│   ├── ToolExecutionException                 ← your tool callable raised
│   ├── ToolInitializationException
│   └── UserInputRequiredException             ← MCP tool needs human approval (interactive flow)
└── WorkflowException
    ├── WorkflowExecutionException
    └── WorkflowInitializationException
```

### Declarative subpackage (⚠️ BETA — `agent-framework-declarative`)

Defined in [`agent_framework_declarative._workflows._errors`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_errors.py) and [`_loader.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py):

```
AgentException
└── DeclarativeLoaderError            ← AgentFactory: YAML parse / schema / agent build failure
    └── ProviderLookupError           ← model.provider doesn't match a built-in or additional mapping

WorkflowException
├── DeclarativeWorkflowError          ← WorkflowFactory: build-time YAML/handler issues
└── DeclarativeActionError            ← run-time failure inside a declarative action executor
```

Importable as `from agent_framework.declarative import DeclarativeLoaderError, DeclarativeWorkflowError, DeclarativeActionError, ProviderLookupError`. See [`declarative.md`](declarative.md#exceptions) for the table and [`../../anti-patterns/declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md) for how each one is triggered.

---

## Removed exceptions (since 1.0 GA)

| Removed | Use instead |
|---------|------------|
| `ServiceResponseException` | `ChatClientInvalidResponseException` |
| `ServiceInitializationException` | `ChatClientInitializationException` or `AgentInitializationException` (context-dependent) |
| `KernelException` | `AgentFrameworkException` (no equivalent — was Semantic Kernel-era) |

See [`../../anti-patterns/removed-apis-since-1.0.md`](../../anti-patterns/removed-apis-since-1.0.md).

---

## The most common catch — `ChatClientInvalidResponseException`

Parent demos 2/3/4/5/7/8 all wrap `agent.run(...)` with this catch because it surfaces the two most user-actionable failures:

| Symptom in `str(ex)` | Cause | Action |
|---------------------|-------|--------|
| `"Failed to resolve model info"` | `FOUNDRY_MODEL` deployment name doesn't exist in this Foundry project | Open the Foundry portal → Models + endpoints → verify the deployment name |
| `"403"` / `"Forbidden"` | RBAC: your identity lacks permissions on the project | Have an admin grant you the Foundry agent runner role |
| `"Credential ... not authenticated"` | `az login` is missing or expired | Run `az login` and retry |

### Canonical pattern

```python
from agent_framework.exceptions import ChatClientInvalidResponseException

try:
    result = await agent.run(prompt)
except ChatClientInvalidResponseException as ex:
    msg = str(ex)
    if "Failed to resolve model info" in msg:
        raise RuntimeError(
            "Microsoft Foundry could not resolve the model deployment specified by FOUNDRY_MODEL.\n\n"
            "What to check:\n"
            "- In the Foundry portal for this project, open 'Models + endpoints' and "
            "  confirm the deployment name exists.\n"
            "- FOUNDRY_MODEL must be the Foundry project model deployment name.\n\n"
            f"Current value:\n  FOUNDRY_MODEL={os.environ.get('FOUNDRY_MODEL','')}"
        ) from ex
    if "403" in msg or "Forbidden" in msg:
        raise RuntimeError(
            "Request was forbidden (403).\n"
            "- Verify you ran `az login`.\n"
            "- Verify your Entra ID has RBAC permissions on the Foundry project."
        ) from ex
    if "Credential" in msg and "not authenticated" in msg.lower():
        raise RuntimeError(
            "Azure CLI credential is not authenticated. Run `az login` and try again."
        ) from ex
    raise
```

The key insight: **catch the specific exception class, then string-match the message** for known sub-cases and re-raise with actionable guidance. Anything you don't recognise: re-raise unchanged.

---

## Workflow-level errors

In streaming mode, workflow failures come **through the event stream** (not as raised exceptions):

```python
async for event in workflow.run(prompt, stream=True):
    if event.type == "failed":
        details = getattr(event, "details", None)
        msg = f"{details.error_type}: {details.message}" if details else "(no details)"
        print(f"[!] Workflow failed: {msg}")
    elif event.type == "executor_failed":
        details = getattr(event, "details", None)
        print(f"[!] Executor failed: id={event.executor_id} — {details.error_type}: {details.message}")
```

A `try/except WorkflowException` block wraps the *whole* `async for` iteration and catches initialization errors, not per-executor failures. Per-executor failures should be handled via the event stream above.

---

## Other catch points

| Exception | When |
|-----------|------|
| `SettingNotFoundError` | Missing required env var (e.g. `FOUNDRY_PROJECT_ENDPOINT`). Use the parent demo's `_require_env()` pattern for friendlier messages. |
| `ContentFilterException` | The model refused to answer due to content policy. Inspect `ex.details` for the filtered category. |
| `UserInputRequiredException` | MCP tool with `approval_mode="always"` needs human approval. Surface to user, get input, resume. |
| `ToolExecutionException` | A function tool raised an unexpected exception. Wrapped from the original. The original is on `ex.__cause__`. |

---

## Fail-fast for missing env vars

Don't wait for `SettingNotFoundError` from deep in the SDK — fail at startup with a clear message. Parent demos use:

```python
def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable is missing or empty: {name}. "
            "Set it via .env / export / Codespaces secrets and try again."
        )
    return value

project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
model = _require_env("FOUNDRY_MODEL")
```

Note the **`.strip()`** — Codespaces sometimes injects env vars as the empty string, and `os.getenv` returns `""` (not None). See [`../../anti-patterns/empty-env-vars-codespaces.md`](../../anti-patterns/empty-env-vars-codespaces.md).

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `except Exception` everywhere | Catch `ChatClientInvalidResponseException` (and friends) specifically — re-raise unknown errors. |
| Using removed `ServiceResponseException` | Migrate to `ChatClientInvalidResponseException`. |
| Treating workflow per-executor failures as raised exceptions | They come through `event.type == "executor_failed"` in streaming mode. |
| Not stripping env var values | Empty-string-injected vars pass `if name:` checks. Use `_require_env()` pattern. |

---

## See also

- [`agents.md`](agents.md) — what `Agent.run(...)` can raise
- [`workflows.md`](workflows.md) — workflow-level error events
- [`../../patterns/error-handling.md`](../../patterns/error-handling.md) — full fail-fast recipe
- [`declarative.md`](declarative.md) — ⚠️ BETA — declarative subpackage exceptions
- [`../../anti-patterns/removed-apis-since-1.0.md`](../../anti-patterns/removed-apis-since-1.0.md)
- [`../../anti-patterns/empty-env-vars-codespaces.md`](../../anti-patterns/empty-env-vars-codespaces.md)
- [`../../anti-patterns/declarative-pitfalls.md`](../../anti-patterns/declarative-pitfalls.md) — ⚠️ BETA — when each declarative exception is raised
