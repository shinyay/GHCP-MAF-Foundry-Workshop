# Middleware: Agent / Chat / Function Pipelines

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent_framework/_middleware.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py)

Middleware is the framework's general extensibility seam — three independent pipelines (Agent, Chat, Function) that wrap each layer of an agent invocation. All middleware types are top-level exports of `agent_framework`.

## The three layers

```text
agent.run("...")
└─ AgentMiddleware pipeline                  ← AgentContext
   └─ chat client (e.g. FoundryChatClient.get_response)
      └─ ChatMiddleware pipeline             ← ChatContext
         └─ leaf chat client call (HTTP request)
         └─ FunctionMiddleware pipeline      ← FunctionInvocationContext
            └─ tool / function execution
```

Each layer has its own **context object**, its own **abstract base class**, and a matching **decorator** for callable-style middleware.

> [!NOTE]
> **1.8.0 NEW — Progressive tool exposure ([PR #6233](https://github.com/microsoft/agent-framework/pull/6233), `@experimental`)**: A new middleware-adjacent surface lets you reveal the agent's tool set in **stages** instead of all at once. Combined with `FunctionMiddleware`, you can gate higher-risk tools behind a confirmation hop, swap toolsets per turn, or implement RAG-style "load tool when needed" flows without rebuilding the `Agent`. Marked `@experimental(feature_id=ExperimentalFeature.TOOLS)` — shape may change. See also [`context-providers-rag.md`](context-providers-rag.md) for the analogous context surface and [`feature-stages.md`](feature-stages.md) for the warning model.

| Layer | Wraps | ABC | Decorator | Context |
|-------|-------|-----|-----------|---------|
| Agent | `agent.run(...)` (the whole invocation) | `AgentMiddleware` | `@agent_middleware` | `AgentContext` |
| Chat | `chat_client.get_response(...)` (one model call) | `ChatMiddleware` | `@chat_middleware` | `ChatContext` |
| Function | One tool / function invocation | `FunctionMiddleware` | `@function_middleware` | `FunctionInvocationContext` |

Verified at [`_middleware.py:L82-L90`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L82-L90) (`MiddlewareType` enum) and [`_middleware.py:L545-L567`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L545-L567) (type aliases).

## The mandatory contract

Every middleware — class or callable — has the same shape:

```python
async def process(context, call_next):
    # ... pre-execution work ...
    await call_next()        # runs the next middleware OR the wrapped operation
    # ... post-execution work ...
```

**Two strict rules** ([`_middleware.py:L406-L412`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L406-L412)):

1. **Never `return` a value.** All data flows through the context object.
2. **Set `context.result` to override** the wrapped operation; **read `context.result` after `call_next()`** to observe what it produced.

Short-circuit (skip the wrapped operation entirely) by **not calling `await call_next()`** — just set `context.result` and return.

Terminate the entire pipeline early (analogous to a hard `return`) by raising `MiddlewareTermination` ([`_middleware.py:L72-L79`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L72-L79)):

```python
raise MiddlewareTermination("budget exceeded", result=cached_response)
```

## Class-style middleware

### `AgentMiddleware`

[`_middleware.py:L357-L413`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L357-L413).

```python
from agent_framework import AgentMiddleware, AgentContext

class RetryMiddleware(AgentMiddleware):
    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    async def process(self, context: AgentContext, call_next):
        for attempt in range(self.max_retries):
            await call_next()
            if context.result and not context.result.is_error:
                break
```

### `ChatMiddleware`

[`_middleware.py:L480-L542`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L480-L542).

```python
from agent_framework import ChatMiddleware, ChatContext, Message

class SystemPromptMiddleware(ChatMiddleware):
    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt

    async def process(self, context: ChatContext, call_next):
        context.messages = [Message(role="system", contents=[self.system_prompt]), *context.messages]
        await call_next()
```

### `FunctionMiddleware`

[`_middleware.py:L416-L477`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L416-L477).

```python
from agent_framework import FunctionMiddleware, FunctionInvocationContext, MiddlewareTermination

class CachingMiddleware(FunctionMiddleware):
    def __init__(self) -> None:
        self.cache: dict[str, Any] = {}

    async def process(self, context: FunctionInvocationContext, call_next):
        key = f"{context.function.name}:{context.arguments}"
        if key in self.cache:
            context.result = self.cache[key]
            raise MiddlewareTermination()
        await call_next()
        if context.result:
            self.cache[key] = context.result
```

## Decorator-style middleware

Three decorators tag a coroutine function with the middleware type ([`_middleware.py:L570-L666`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L570-L666)). The decorator sets `func._middleware_type` on the function so the framework can categorize it without a wrapper class.

```python
from agent_framework import agent_middleware, chat_middleware, function_middleware

@agent_middleware
async def log_agent(context, call_next):
    print(f"[agent] {context.agent.name}")
    await call_next()

@chat_middleware
async def log_chat(context, call_next):
    print(f"[chat] {len(context.messages)} messages")
    await call_next()

@function_middleware
async def log_function(context, call_next):
    print(f"[function] {context.function.name}({context.arguments})")
    await call_next()
```

> [!IMPORTANT]
> Decorator-style middleware is **only the second of the two ways the framework knows the middleware type**. The first is `isinstance(mw, AgentMiddleware/ChatMiddleware/FunctionMiddleware)`. An undecorated bare async function will fail categorization at `_determine_middleware_type` ([`_middleware.py:L1330`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L1330)).

## Context objects — the data plane

### `AgentContext` ([`_middleware.py:L93-L201`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L93-L201))

| Attribute | Mutable? | Notes |
|-----------|----------|-------|
| `agent` | no | The `SupportsAgentRun` being invoked. |
| `messages` | yes | Mutate to inject/replace messages before the agent runs. |
| `session` | no | Active `AgentSession`, if any. |
| `tools` | yes | Run-level tool overrides. |
| `options` | yes | Agent-run options as a dict. |
| `stream` | no | `True` for streaming invocations. |
| `compaction_strategy`, `tokenizer` | yes | Per-run overrides. |
| `metadata` | yes | Inter-middleware scratch space. |
| `result` | yes | `AgentResponse` (non-stream) or `ResponseStream[AgentResponseUpdate, AgentResponse]` (stream). Read after `call_next()`. |
| `kwargs`, `client_kwargs`, `function_invocation_kwargs` | yes | Plumbing to lower layers. |
| `stream_transform_hooks`, `stream_result_hooks`, `stream_cleanup_hooks` | yes | Streaming-only post-processing. |

### `ChatContext` ([`_middleware.py:L265-L354`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L265-L354))

Key attributes: `client` (`SupportsChatGetResponse`), `messages` (mutate to add/remove), `options` (request options dict), `stream`, `result` (`ChatResponse` or `ResponseStream[ChatResponseUpdate, ChatResponse]`), `metadata`, `kwargs`, `function_invocation_kwargs`, plus the three `stream_*_hooks` lists.

### `FunctionInvocationContext` ([`_middleware.py:L204-L262`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L204-L262))

Key attributes: `function: FunctionTool`, `arguments: BaseModel | Mapping[str, Any]` (validated), `session`, `metadata`, `result`, `kwargs`.

## Wiring middleware

Middleware is registered **on the agent**, not on individual `run()` calls. In 1.8.0 `agent.run(...)` does not accept a `middleware=` kwarg — register all middleware once on the constructor and the framework auto-categorizes each entry:

```python
agent = client.as_agent(
    name="assistant",
    instructions="...",
    middleware=[
        RetryMiddleware(),       # AgentMiddleware
        log_chat_calls,          # @chat_middleware decorated
        validate_arguments,      # @function_middleware decorated
    ],
)
result = await agent.run("hello")
```

The framework auto-categorizes each entry by `MiddlewareType` and routes it into the matching pipeline ([`_middleware.py:L1330-L1397`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L1330-L1397)) — you don't pre-split.

For request-scoped middleware that needs to vary per call (e.g., a different retry strategy in a batch job), reach into the underlying middleware via a `ContextProvider` whose `before_run` toggles state, or instantiate a per-request `Agent` instance — there is no per-call middleware override surface.

## Pipeline classes (advanced)

[`_middleware.py:L735-L1325`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_middleware.py#L735-L1325) defines `AgentMiddlewarePipeline`, `ChatMiddlewarePipeline`, `FunctionMiddlewarePipeline`, `AgentMiddlewareLayer`, and `ChatMiddlewareLayer`. These are normally constructed by the framework — you rarely use them directly. They are public exports so advanced integrators (e.g., wrapping an external chat client) can compose pipelines manually.

## Streaming semantics

For streaming agents:

- `context.stream` is `True`.
- After `call_next()`, `context.result` is a `ResponseStream[AgentResponseUpdate, AgentResponse]`.
- Use `stream_transform_hooks` to inject per-update transforms, `stream_result_hooks` to mutate the final aggregated response, and `stream_cleanup_hooks` to run on completion.

## Exceptions

| Exception | When raised |
|-----------|-------------|
| `MiddlewareException` | Base class, raised for middleware-categorization failures and similar contract violations (e.g., context provider tried to add agent middleware — [`_sessions.py:L300`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L300)). |
| `MiddlewareTermination` | Control flow — terminate the pipeline early with optional `result`. **Not** an error. |

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| `return some_value` from `process()` | Ignored. Set `context.result` instead. |
| Forgetting `await call_next()` and forgetting to set `context.result` | Wrapped operation is skipped and result is `None`. Either short-circuit *with* a result, or call `call_next()`. |
| Subclassing `AgentMiddleware` but registering it as a callable | Type confusion. Pass the **instance** to `middleware=[...]`, not the class or the bound `.process`. |
| Adding agent middleware from a `ContextProvider` | Raises `MiddlewareException`: "Context providers may only add chat or function middleware." ([`_sessions.py:L300`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_sessions.py#L300)) |
| Mutating `context.messages` *after* `call_next()` for chat middleware | No effect — message list has already been sent to the model. Mutate before. |

## See also

- [`sessions.md`](sessions.md) — `ContextProvider` adds chat/function middleware via `SessionContext.extend_middleware`
- [`agents.md`](agents.md) — agent constructor `middleware=` parameter
- [`../../patterns/agent-middleware-retry.md`](../../patterns/agent-middleware-retry.md)
- [`../../anti-patterns/middleware-returning-value.md`](../../anti-patterns/middleware-returning-value.md)
