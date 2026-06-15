# Pattern: Error Handling (Fail Fast + AgentFrameworkException Hierarchy)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: introspection (`agent_framework.exceptions`) + parent demo pattern
> See also: [API ref — `exceptions.md`](../api-reference/1.8.0/exceptions.md)

## Goal

Catch and surface Agent Framework errors with **actionable messages**. The hierarchy was reorganized in 1.0 GA — old exceptions (like `ServiceResponseException`) were removed, replaced by the `AgentFrameworkException` family.

## When to use this pattern

- ✅ Every production agent invocation needs at least one try/except around `agent.run(...)`.
- ✅ User-facing CLIs / DevUI demos benefit from translating cryptic exceptions into "do this to fix it" messages.
- ✅ Eval pipelines benefit from per-error classification (transient vs config vs auth).

## Exception hierarchy (1.8.0)

```
AgentFrameworkException                    (base — catch this to catch everything)
├── ChatClientException
│   ├── ChatClientInvalidResponseException   ← model deployment / RBAC / endpoint errors
│   └── ChatClientRateLimitException
├── AgentException
│   ├── AgentInvalidResponseException        ← schema validation failures (structured output)
│   └── AgentExecutionException
├── ToolException
│   ├── ToolExecutionException
│   └── ToolDescriptionException
└── WorkflowException                       ← workflow build / runtime errors
```

## Code

```python
import asyncio
from agent_framework.exceptions import (
    AgentFrameworkException,
    AgentInvalidResponseException,
    ChatClientInvalidResponseException,
    ChatClientRateLimitException,
    ToolExecutionException,
)


def _classify_error(ex: Exception) -> tuple[str, str]:
    """Translate an Agent Framework exception into (category, user_message)."""
    s = str(ex)

    if isinstance(ex, ChatClientRateLimitException):
        return ("rate_limited", "Throttled by Foundry. Wait a few seconds and retry.")

    if isinstance(ex, ChatClientInvalidResponseException):
        if "Failed to resolve model info" in s:
            return ("config", "FOUNDRY_MODEL deployment name doesn't exist in this project.")
        if "401" in s or "Unauthorized" in s:
            return ("auth", "Authentication failed. Re-run `az login` and retry.")
        if "403" in s or "Forbidden" in s:
            return ("rbac", "Your principal lacks the right RBAC role. Assign 'Cognitive Services User'.")
        return ("model", f"Model call failed: {s[:200]}")

    if isinstance(ex, AgentInvalidResponseException):
        return ("schema", "Model returned data that doesn't match the response_format schema. Try simpler instructions.")

    if isinstance(ex, ToolExecutionException):
        return ("tool", f"Tool execution failed: {s[:200]}")

    if isinstance(ex, AgentFrameworkException):
        return ("framework", f"Agent Framework error: {s[:200]}")

    return ("unknown", f"Unexpected error: {s[:200]}")


async def safe_run(agent, prompt: str) -> str:
    try:
        result = await agent.run(prompt)
        return result.text
    except AgentFrameworkException as ex:
        category, message = _classify_error(ex)
        # Log full exception for debugging; surface friendly message to user.
        # logger.exception("agent.run failed", extra={"category": category})
        raise RuntimeError(f"[{category}] {message}") from ex
```

## Why each piece

| Piece | Why |
|-------|-----|
| Catch `AgentFrameworkException` (not bare `Exception`) | You see only framework errors; OS errors (KeyboardInterrupt, MemoryError) still propagate naturally. |
| Specific `isinstance(...)` checks first | More specific handling for known patterns (rate limit, schema failure) before falling back to generic message. |
| String matching on "Failed to resolve model info" / "401" / "403" | The HTTP-level detail is in the message string; this maps to the specific Foundry misconfig. |
| `raise RuntimeError(...) from ex` | Preserves the chain for `traceback.format_exception()` while presenting a friendly top-line message. |
| **No** `except ServiceResponseException` | Removed in 1.0 GA. If you see this in old code, replace with `ChatClientInvalidResponseException`. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `except Exception:` swallowing KeyboardInterrupt | Catch `AgentFrameworkException` for framework errors specifically. |
| `except ServiceResponseException:` (removed in 1.0) | Use `ChatClientInvalidResponseException`. |
| Re-raising without `from ex` | Loses the original traceback. Always use `raise ... from ex`. |
| Showing the raw stack trace to the user | Use `_classify_error` to translate; log the trace separately. |
| No retry for `ChatClientRateLimitException` | Add exponential backoff (e.g., `tenacity`) for production. |
| Catching `Exception` in `agent.as_tool()` definitions | Tool functions should let exceptions propagate to the framework; the framework wraps them as `ToolExecutionException`. |

## Retry example (with tenacity)

```python
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from agent_framework.exceptions import ChatClientRateLimitException


@retry(
    retry=retry_if_exception_type(ChatClientRateLimitException),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
)
async def run_with_retry(agent, prompt: str) -> str:
    result = await agent.run(prompt)
    return result.text
```

## Verification

```bash
# Force a config error to validate your handler:
FOUNDRY_MODEL=does-not-exist python path/to/your/script.py
```

Expected: friendly "[config] FOUNDRY_MODEL deployment name doesn't exist…" message (not a stack trace).

## See also

- [`exceptions.md`](../api-reference/1.8.0/exceptions.md) — full hierarchy with all subtypes
- [`../anti-patterns/removed-apis-since-1.0.md`](../anti-patterns/removed-apis-since-1.0.md)
- [`canonical-agent-creation.md`](canonical-agent-creation.md) — basic try/except example
