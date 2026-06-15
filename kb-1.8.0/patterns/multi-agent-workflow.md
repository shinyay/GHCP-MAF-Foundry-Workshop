# Pattern: Multi-Agent Workflow (WorkflowBuilder + edges + streaming)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: parent demo `src/demo5_workflow_edges.py`
> See also: [API ref — `workflows.md`](../api-reference/1.8.0/workflows.md)

## Goal

Compose **multiple specialist agents** into a directed graph where each agent's output flows into the next. Use this when one agent is too coarse — e.g., research → write → review pipelines.

## When to use

- ✅ The problem decomposes into independent specialist roles (researcher / writer / reviewer / refiner).
- ✅ You want **deterministic flow** between agents (not the model deciding when to hand off).
- ✅ You want **streaming progress** events to a UI as each agent does its work.
- ❌ One agent + tools is enough → use [`canonical-agent-creation.md`](canonical-agent-creation.md).
- ❌ You need the model to choose dynamically which agent to invoke → use a single coordinator with multiple `as_tool()` sub-agents — see [`agent-as-tool-handoff.md`](agent-as-tool-handoff.md).

## Architecture

```text
User question
      │
      ▼
┌──────────────┐
│  Researcher  │  ← Bing grounding
└──────┬───────┘
       │ findings (text)
       ▼
┌──────────────┐
│    Writer    │  ← drafts the outline
└──────┬───────┘
       │ draft (text)
       ▼
┌──────────────┐
│   Reviewer   │  ← critiques against rubric
└──────┬───────┘
       │ critique (text)
       ▼
┌──────────────┐
│    Final     │  ← produces final answer
└──────┬───────┘
       ▼
   Output
```

## Code (skeleton)

> [!NOTE]
> The authoritative 1.8.0 `WorkflowBuilder` constructor surface is summarized in [`workflows.md`](../api-reference/1.8.0/workflows.md#constructor), especially the `output_from=` / `intermediate_output_from=` guidance at lines 42-44.

```python
import asyncio
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from agent_framework import WorkflowBuilder
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


def _format_payload(data: Any) -> str:
    text = getattr(data, "text", None)
    if text is not None:
        return str(text)
    if data is None:
        return ""
    return str(data)


async def _create_agent(
    stack: AsyncExitStack,
    client: FoundryChatClient,
    *,
    name: str,
    instructions: str,
    tools: list[Any] | None = None,
):
    """Helper: open an agent inside the shared AsyncExitStack so the workflow owns its lifetime."""
    return await stack.enter_async_context(
        client.as_agent(name=name, instructions=instructions, tools=tools or [])
    )


async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")

    async with AzureCliCredential() as cred, AsyncExitStack() as stack:
        client = FoundryChatClient(
            project_endpoint=project_endpoint, model=model, credential=cred
        )

        researcher = await _create_agent(
            stack, client,
            name="researcher",
            instructions="Gather facts and return a bullet list of findings.",
        )
        writer = await _create_agent(
            stack, client,
            name="writer",
            instructions="Turn the findings into a polished one-paragraph draft.",
        )
        reviewer = await _create_agent(
            stack, client,
            name="reviewer",
            instructions="Critique the draft for accuracy and clarity. Output 'OK' or specific issues.",
        )
        final_agent = await _create_agent(
            stack, client,
            name="final",
            instructions="Apply the reviewer's critique to the draft and return the final answer.",
        )

        wf = (
            WorkflowBuilder(
                start_executor=researcher,
                output_from=[final_agent],
                intermediate_output_from=[researcher, writer, reviewer],
            )
            .add_edge(researcher, writer)
            .add_edge(writer, reviewer)
            .add_edge(reviewer, final_agent)
            .build()
        )

        final_text = ""
        async for event in wf.run("Why do leaves change color in fall?", stream=True):
            t = event.type
            # 1.8.0 unified event model — discriminate on event.type, NOT isinstance.
            if t in ("intermediate", "data"):    # "data" is a deprecated alias for "intermediate"
                chunk = _format_payload(event.data)
                print(chunk, end="", flush=True)
            elif t == "executor_completed":
                print(f"\n[{event.executor_id} done]\n", flush=True)
            elif t == "executor_failed":
                details = event.details
                error_type = details.error_type if details else "UnknownError"
                message = details.message if details else "No failure details provided."
                raise RuntimeError(f"Executor failed: {event.executor_id}: {error_type}: {message}")
            elif t == "output":
                final_text = _format_payload(event.data)
            elif t == "failed":
                details = event.details
                error_type = details.error_type if details else "UnknownError"
                message = details.message if details else "No failure details provided."
                raise RuntimeError(f"Workflow failed: {error_type}: {message}")

        print("\n--- FINAL ---")
        print(final_text)


if __name__ == "__main__":
    asyncio.run(main())
```

## Linear chain shortcut: `add_chain([...])`

For a strictly linear pipeline (each executor feeds the next, no fan-out or fan-in), `WorkflowBuilder.add_chain([...])` collapses N-1 pairwise `.add_edge(...)` calls into one. The 3 `.add_edge()` lines above become a single line:

```python
wf = (
    WorkflowBuilder(
        start_executor=researcher,
        output_from=[final_agent],
        intermediate_output_from=[researcher, writer, reviewer],
    )
    .add_chain([researcher, writer, reviewer, final_agent])  # ≡ 3 pairwise add_edge calls
    .build()
)
```

`add_chain([a, b, c, d])` is exactly equivalent to `.add_edge(a, b).add_edge(b, c).add_edge(c, d)` — same graph, same runtime semantics. The constructor kwargs (`start_executor`, `output_from`, `intermediate_output_from`) are unchanged; only the edge wiring shrinks.

**When to prefer which**:

- `.add_edge(...)` chains read better when you want to **annotate each hop** (e.g., wrap one hop in a conditional, mix in a `.add_fan_out_edges(...)`, or insert a comment per edge).
- `.add_chain([...])` reads better at **4+ executors** in pure linear sequence — diff noise drops and the pipeline shape is visible at a glance.

Both compile to the same graph; pick whichever fits your editor's diff readability. See [`../api-reference/1.8.0/workflows.md` § Edge-building methods](../api-reference/1.8.0/workflows.md#edge-building-methods) for the full set of builder helpers (`add_fan_out_edges`, `add_switch_case_edge_group`, etc.). [`workflow-as-agent-nesting.md`](workflow-as-agent-nesting.md) and [`workflow-checkpointing.md`](workflow-checkpointing.md) use `add_chain` exclusively.

## Why each piece

| Piece | Why |
|-------|-----|
| `AsyncExitStack` + `_create_agent` helper | Each `client.as_agent(...)` is an async context manager that must be closed. The exit stack closes all 4 agents in reverse order on a single `async with` exit. |
| `WorkflowBuilder(start_executor=researcher, output_from=[final_agent], intermediate_output_from=[...])` | 1.8.0 requires the start executor at **construction time** and recommends explicit output-designation lists (`register_agent()` and `set_start_executor()` are removed). |
| `.add_edge(A, B)` | Sends A's output as B's input. Linear here, but `WorkflowBuilder` supports fan-out / fan-in. |
| `async for event in wf.run(..., stream=True)` | Streams progress events. Non-streaming `wf.run(...)` returns only the final output. |
| `event.type == "..."` (NOT `isinstance(event, ...)`) | All events are the same `WorkflowEvent` class in 1.8.0; the `type` field discriminates. `isinstance` checks always fail. |
| `"data"` is a deprecated alias for `"intermediate"` | Keep both in the check for forward-compat with older runtime versions; read the payload from `event.data`. |
| `event.type == "output"` | Fires with the final output of any executor listed in `output_from=[...]`. |
| `event.type == "failed"` / `"executor_failed"` | Fires when the workflow or executor raises; use `event.details.error_type` and `event.details.message`. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `isinstance(event, ExecutorCompletedEvent)` | Those classes were removed in 1.5.0+. Check `event.type == "executor_completed"`. |
| `wb.register_agent(researcher).set_start_executor(researcher)` | Removed APIs. Use the constructor: `WorkflowBuilder(start_executor=..., output_from=[...], intermediate_output_from=[...])`. |
| Opening each agent in its own `async with` (4 nested) | Works but unreadable for 5+ agents. Use `AsyncExitStack`. |
| Reading `result.text` for the final output | The streaming version returns events, not a single result object. Capture `event.type == "output"` and stash `event.data`. |
| Adding edges to an unbuilt graph after `.build()` | The builder is consumed on `.build()`. Add all edges first. |
| Forgetting `output_from=[...]` | Workflow runs but never emits an `"output"` event → caller hangs waiting for the answer. |

## Verification

```bash
python path/to/this/script.py
```

Expected: streamed progress messages from each executor, then a final answer on the leaves question.

## See also

- [`workflows.md`](../api-reference/1.8.0/workflows.md) — full event-type table
- [`streaming-output.md`](streaming-output.md) — single-agent streaming
- [`../anti-patterns/workflow-event-isinstance.md`](../anti-patterns/workflow-event-isinstance.md)
