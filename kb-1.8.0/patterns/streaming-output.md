# Pattern: Streaming Output (CLI / UI)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: introspection (`Agent.run(stream=True)`) + parent demo `src/demo5_workflow_edges.py` (workflow streaming)
> See also: [API ref — `agents.md`](../api-reference/1.8.0/agents.md), [`workflows.md`](../api-reference/1.8.0/workflows.md)

## Goal

Stream the agent's response **token-by-token** to a CLI or web UI for a responsive feel. In 1.8.0 there's **no separate `run_stream()` method** — streaming is opt-in via `stream=True` on `run()`.

## When to use

- ✅ CLI tools where the user is watching the terminal in real time.
- ✅ Web UIs that render deltas as they arrive (chat bubbles).
- ✅ Long answers where users want to see progress before completion.
- ❌ Structured output (`response_format=`) → 1.8.0 streams text only; use non-streaming.
- ❌ Batch / eval pipelines where you only need the final answer → use non-streaming for simpler error handling.

## Code — single agent, CLI

```python
import asyncio
import os
import sys
from pathlib import Path

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


for k, v in dotenv_values(Path(__file__).resolve().parents[1] / ".env").items():
    if v is not None and not (os.getenv(k) or "").strip():
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


async def main(prompt: str) -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=project_endpoint, model=model, credential=cred
        )
        async with client.as_agent(
            name="assistant",
            instructions="You are a concise, helpful assistant.",
        ) as agent:
            # stream=True turns run() into an async iterator of update chunks
            async for update in agent.run(prompt, stream=True):
                # Update shape can vary across builds; collect common fields.
                delta = (
                    getattr(update, "text", None)
                    or getattr(update, "content", None)
                    or ""
                )
                if delta:
                    print(delta, end="", flush=True)
            print()   # trailing newline once stream completes


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Tell me a haiku about Tokyo."))
```

## Code — workflow streaming

For multi-agent workflows, the streaming surface is **WorkflowEvent**, not text chunks:

```python
async for event in wf.run(prompt, stream=True):
    if event.type in ("intermediate", "data"):
        # An executor produced a partial output (token delta).
        chunk = getattr(event, "content", None) or ""
        print(chunk, end="", flush=True)
    elif event.type == "executor_completed":
        print(f"\n[{event.executor_id} done]\n")
    elif event.type == "output":
        print(f"\n--- FINAL ---\n{event.data}")
    elif event.type == "failed":
        raise RuntimeError(f"Workflow failed: {event.details.error_type}: {event.details.message}")
```

See [`multi-agent-workflow.md`](multi-agent-workflow.md) for the full workflow context.

## Why each piece

| Piece | Why |
|-------|-----|
| `stream=True` on `run()` | 1.5.0+ canonical form. `run_stream()` was **removed**. |
| `async for ... in agent.run(..., stream=True)` | The returned object is an async iterator of updates, not a coroutine. **Don't `await` it.** |
| `getattr(update, "text", ...) or getattr(update, "content", ...)` | The update payload shape varies across SDK builds. Defensive access covers both. |
| `print(..., flush=True)` | Without `flush=True`, Python buffers output and the user sees nothing until the end. |
| Single trailing newline | Stream typically ends with text but no newline. Add one for clean CLI output. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `await agent.run(prompt, stream=True)` | When `stream=True`, the call returns an async iterator. Use `async for`, **not** `await`. |
| Calling `agent.run_stream(...)` | Removed in 1.5.0. Use `run(..., stream=True)`. |
| Reading `update.text` only | Some builds put the delta in `.content`. Use the defensive `getattr(...) or getattr(...)`. |
| Streaming + structured output (`response_format=...`) | 1.8.0 streams text only. Structured output requires non-streaming. |
| Forgetting `flush=True` on `print()` | Terminal buffers everything until the function returns — the streaming feel is lost. |
| Wrapping streaming in a long-running web request without backpressure | Client disconnects = server keeps generating. Add cancellation handling. |

## Verification

```bash
python path/to/this/script.py "Tell me a haiku about Tokyo."
```

Expected: text appears letter-by-letter (not all at once), ending with a newline.

## See also

- [`agents.md`](../api-reference/1.8.0/agents.md) — `Agent.run()` reference
- [`workflows.md`](../api-reference/1.8.0/workflows.md) — workflow event types
- [`multi-agent-workflow.md`](multi-agent-workflow.md) — full workflow streaming example
- [`../anti-patterns/workflow-event-isinstance.md`](../anti-patterns/workflow-event-isinstance.md)
