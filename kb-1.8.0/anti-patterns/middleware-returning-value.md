# Anti-Pattern: Returning a Value from Middleware `process()`

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_middleware.py:L390-L412`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L390-L412)

## ❌ Anti-pattern

Treating middleware like a function that *returns* the result:

```python
# WRONG — return value is ignored
class BadCachingMiddleware(FunctionMiddleware):
    async def process(self, context: FunctionInvocationContext, call_next):
        key = f"{context.function.name}:{context.arguments}"
        if key in self.cache:
            return self.cache[key]              # ❌ swallowed
        await call_next()
        return context.result                    # ❌ swallowed
```

```python
# Also wrong — calling a coroutine as if it returns the response
@chat_middleware
async def my_mw(context, call_next):
    response = await call_next()                 # ❌ call_next returns None
    print(response)                              # → None
```

## Why it's wrong

The middleware contract ([`_middleware.py:L390-L412`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L390-L412)) is explicit:

> `call_next: Function to call the next middleware or final agent execution. Does not return anything - all data flows through the context.`
>
> `MiddlewareTypes should not return anything. All data manipulation should happen within the context object. Set context.result to override execution, or observe context.result after calling call_next() for actual results.`

Returning a value from `process()`:

- Is **silently dropped** by the framework's pipeline runner.
- Causes the wrapped operation to either run with no override (if you `await call_next()` first) or be skipped entirely with `context.result = None` (if you `return` early).
- Misleads readers: the codepath *looks* right but produces empty/null responses at the caller.

## ✅ Correct pattern

```python
from agent_framework import (
    FunctionMiddleware,
    FunctionInvocationContext,
    MiddlewareTermination,
)

class CachingMiddleware(FunctionMiddleware):
    def __init__(self) -> None:
        self.cache: dict[str, Any] = {}

    async def process(self, context: FunctionInvocationContext, call_next):
        key = f"{context.function.name}:{context.arguments}"
        if key in self.cache:
            context.result = self.cache[key]    # ✅ set on context
            raise MiddlewareTermination()       # ✅ short-circuit cleanly
        await call_next()                        # ✅ no assignment
        if context.result is not None:
            self.cache[key] = context.result    # ✅ read from context
```

```python
# Decorator-style — same rules
@chat_middleware
async def log_chat(context, call_next):
    print(f"before: {len(context.messages)} messages")
    await call_next()                            # ✅ no assignment
    print(f"after: {context.result}")            # ✅ read from context
```

## Three legal ways to influence the result

| Goal | How |
|------|-----|
| Replace the result with your own | Set `context.result = ...`, *don't* call `call_next()`, return. |
| Short-circuit explicitly with cleanup semantics | Set `context.result = ...`, raise `MiddlewareTermination()`. |
| Inspect or transform the actual result | `await call_next()`, then read/mutate `context.result`. |

`MiddlewareTermination` ([`_middleware.py:L72-L79`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L72-L79)) accepts an optional `result=` kwarg, which the pipeline preserves on `context.result` for you:

```python
raise MiddlewareTermination("budget exceeded", result=cached_response)
```

## How to spot it in review

Search for any of these in `process()` implementations:

```bash
grep -n "return context.result" .
grep -n "response = await call_next" .
grep -nE "return [a-zA-Z_]" your_middleware_file.py | grep -v "return None"
```

Any `return <expr>` (other than `return None` or bare `return`) inside a middleware `process()` body is suspect.

## Related anti-patterns

- [`workflow-event-isinstance.md`](workflow-event-isinstance.md) — discriminate workflow events via `event.type`, not `isinstance`
- [`missing-async-with-cleanup.md`](missing-async-with-cleanup.md)

## See also

- [`../api-reference/1.8.0/middleware.md`](../api-reference/1.8.0/middleware.md)
- [`../patterns/agent-middleware-retry.md`](../patterns/agent-middleware-retry.md)
