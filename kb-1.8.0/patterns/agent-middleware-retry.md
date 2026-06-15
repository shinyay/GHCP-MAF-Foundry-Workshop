# Pattern: Agent Middleware for Retry / Caching / Observability

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_middleware.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py)

## Goal

Wrap `agent.run(...)` with reusable cross-cutting concerns (retry, caching, rate-limiting, structured logging) without modifying the agent or chat-client code.

## When to use which middleware layer

| Concern | Use |
|---------|-----|
| Retry entire agent invocation (multiple turns / tool calls together) | `AgentMiddleware` |
| Inject system prompt, log every model call, count tokens | `ChatMiddleware` |
| Validate tool arguments, cache tool outputs, audit tool invocations | `FunctionMiddleware` |

See [`../api-reference/1.8.0/middleware.md`](../api-reference/1.8.0/middleware.md) for the full layer model.

## Pattern 1 — Retry the whole agent run

```python
import asyncio
from agent_framework import AgentMiddleware, AgentContext

class RetryOnTransientError(AgentMiddleware):
    """Retry the entire agent.run() on transient errors."""

    def __init__(self, *, max_attempts: int = 3, backoff_s: float = 1.0) -> None:
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s

    async def process(self, context: AgentContext, call_next):
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                await call_next()
                if context.result and not getattr(context.result, "is_error", False):
                    return
            except (TimeoutError, ConnectionError) as exc:
                last_exc = exc
                if attempt == self.max_attempts:
                    raise
                await asyncio.sleep(self.backoff_s * 2 ** (attempt - 1))
        if last_exc:
            raise last_exc
```

Wire it on the agent:

```python
agent = client.as_agent(
    name="assistant",
    instructions="...",
    middleware=[RetryOnTransientError(max_attempts=3)],
)
```

## Pattern 2 — Cache tool calls

```python
from agent_framework import FunctionMiddleware, FunctionInvocationContext, MiddlewareTermination

class FunctionResultCache(FunctionMiddleware):
    def __init__(self) -> None:
        self.cache: dict[str, Any] = {}

    async def process(self, context: FunctionInvocationContext, call_next):
        key = f"{context.function.name}:{context.arguments}"
        if key in self.cache:
            context.result = self.cache[key]
            raise MiddlewareTermination()      # short-circuit: skip the wrapped invocation
        await call_next()
        if context.result is not None:
            self.cache[key] = context.result
```

`MiddlewareTermination` is the canonical control-flow signal — it unwinds the pipeline cleanly with `context.result` already set. ([`_middleware.py:L72-L79`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L72-L79))

## Pattern 3 — Observability via decorator-style middleware

```python
import time
from agent_framework import chat_middleware

@chat_middleware
async def log_chat_timing(context, call_next):
    start = time.perf_counter()
    await call_next()
    duration_ms = (time.perf_counter() - start) * 1000
    msg_count = len(context.messages)
    print(f"[chat] {msg_count} messages → {duration_ms:.1f} ms")
```

The `@chat_middleware` decorator (and its siblings `@agent_middleware`, `@function_middleware`) sets the `_middleware_type` attribute so the framework routes the callable into the correct pipeline ([`_middleware.py:L599`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L599)). Without the decorator, plain async functions fail categorization.

## Pattern 4 — Combining multiple middleware

```python
agent = client.as_agent(
    name="assistant",
    instructions="...",
    middleware=[
        RetryOnTransientError(max_attempts=3),  # AgentMiddleware
        log_chat_timing,                         # @chat_middleware
        FunctionResultCache(),                   # FunctionMiddleware
    ],
)
```

The framework auto-categorizes each entry via `_determine_middleware_type` ([`_middleware.py:L1330`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L1330)) and dispatches each to its dedicated pipeline. **You do not pre-split the list.**

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `return context.result` (or `return some_value`) from `process()` | Ignored. Set `context.result` and let `process()` return `None` implicitly. |
| Forgot `await call_next()` and forgot to set `context.result` | The wrapped operation never runs and the agent returns `None`. |
| Used a bare async function without `@chat_middleware` / `@function_middleware` / `@agent_middleware` | `_determine_middleware_type` raises. |
| Tried to add `AgentMiddleware` from inside a `ContextProvider.before_run` | `MiddlewareException`: "Context providers may only add chat or function middleware." ([`_sessions.py:L300`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L300)) |
| Stored a tool result in a class-level cache without locking when streaming | Two concurrent agent runs can race. Use a `Lock` or scope the cache per session. |

## Verification

```python
from agent_framework import AgentMiddleware, AgentContext

class Counter(AgentMiddleware):
    def __init__(self) -> None:
        self.calls = 0

    async def process(self, context: AgentContext, call_next):
        self.calls += 1
        await call_next()

counter = Counter()
agent = client.as_agent(name="test", instructions="echo", middleware=[counter])

await agent.run("hi")
await agent.run("there")
assert counter.calls == 2
```

## See also

- [`../api-reference/1.8.0/middleware.md`](../api-reference/1.8.0/middleware.md)
- [`../anti-patterns/middleware-returning-value.md`](../anti-patterns/middleware-returning-value.md)
- [`session-history-persistence.md`](session-history-persistence.md) — context providers that inject middleware
