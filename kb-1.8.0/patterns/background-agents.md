# Pattern: Background Agents — Non-Blocking Sub-Agent Delegation

> Status: ⚠️ **Experimental** — `@experimental(feature_id=ExperimentalFeature.HARNESS)`
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent_framework/_harness/_background_agents.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_background_agents.py) (521 LOC)
> See also: [`harness-agent.md`](harness-agent.md), [API ref — `compaction.md`](../api-reference/1.8.0/compaction.md), [`multi-agent-workflow.md`](multi-agent-workflow.md)

> [!WARNING]
> `BackgroundAgentsProvider` and `BackgroundTaskInfo` are decorated with `@experimental(feature_id=ExperimentalFeature.HARNESS)`. The provider class, the 6 tool names exposed to the LLM, and the on-session state schema **can and will change** between minor versions. Pin `agent-framework-foundry==1.8.0` exactly and re-validate on every Agent Framework upgrade. See [`feature-stages.md`](../api-reference/1.8.0/feature-stages.md) for the full warning model.

## Goal

Let a **parent agent** delegate long-running sub-tasks to **named background agents** and continue working without blocking. Each delegated task runs in its own `AgentSession`, executes concurrently as an `asyncio.Task`, and exposes its status (`RUNNING` / `COMPLETED` / `FAILED` / `LOST`) and final text result back to the parent via tool calls.

## When to use this pattern

- ✅ The parent agent needs to **fire off a slow tool / sub-research task and continue talking** to the user.
- ✅ You want to **fan out to multiple specialist agents** in parallel and wait for the first (or all) to complete.
- ✅ A long sub-task should keep its **own conversation history** that can be **resumed later** with follow-up input.
- ❌ The sub-call is fast and synchronous — use a regular function tool or `agent.run(...)`.
- ❌ You need **cross-process / cross-restart durability** — background task runtime state is **in-memory only** and is lost on process restart (orphaned tasks transition to `LOST`).
- ❌ You need structured (non-text) results from the sub-agent — results come back as `AgentResponse.text`.

## Code

```python
import asyncio
import os
from pathlib import Path

from agent_framework import BackgroundAgentsProvider, create_harness_agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
for _k, _v in dotenv_values(_DOTENV_PATH).items():
    if _v is None:
        continue
    if not (os.getenv(_k) or "").strip():
        os.environ[_k] = _v


async def main() -> None:
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        )

        # Build two specialist child agents (themselves harness-agents).
        researcher = create_harness_agent(
            client,
            name="researcher",
            description="Performs deep web research on a topic.",
            agent_instructions="You research topics thoroughly and cite sources.",
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
        )
        coder = create_harness_agent(
            client,
            name="coder",
            description="Writes and reviews Python code.",
            agent_instructions="You are an expert Python programmer.",
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
        )

        # Wire the background-agents provider into a parent agent.
        background = BackgroundAgentsProvider(agents=[researcher, coder])
        parent = create_harness_agent(
            client,
            name="orchestrator",
            agent_instructions="Delegate research and coding to specialists.",
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
            context_providers=[background],  # ← extra provider on top of the harness defaults
        )

        session = parent.create_session()
        response = await parent.run(
            "Research the 1.8.0 Agent Framework changes, then ask the coder to scaffold a "
            "minimal background-agents demo. Wait for both to finish before summarizing.",
            session=session,
        )
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
```

> [!IMPORTANT]
> Pass background agents into the **parent's** `context_providers=[...]`. Do **not** call `create_harness_agent(..., context_providers=[BackgroundAgentsProvider(...)])` on the child agents themselves unless you intend recursive delegation.

## How it works

### Six exposed tools (verified at [`_background_agents.py:L320-L470`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_background_agents.py#L320-L470))

All tool names use the `background_agents_*` prefix (the convention is **new** in 1.8.0 — they were not renamed from earlier names; this is the first release in which the provider exists):

| Tool name | Signature | What it does |
|---|---|---|
| `background_agents_start_task` | `(agent_name: str, input: str, description: str) -> str` | Creates a new `AgentSession` on the named child agent, kicks off `asyncio.create_task(child.run(input, session=...))`, registers it under a fresh integer task ID, returns confirmation text |
| `background_agents_wait_for_first_completion` | `(task_ids: list[int]) -> str` | `asyncio.wait(..., return_when=FIRST_COMPLETED)` over the matching in-flight tasks; finalizes the first one to complete and returns its ID + status |
| `background_agents_get_task_results` | `(task_id: int) -> str` | Refreshes state, then returns `result_text` (if COMPLETED), `error_text` (if FAILED), `"Task state was lost..."` (if LOST), or `"Task X is still running."` (if RUNNING) |
| `background_agents_get_all_tasks` | `() -> str` | Refreshes state, returns a multi-line listing of all known tasks with id/status/agent_name/description |
| `background_agents_continue_task` | `(task_id: int, text: str) -> str` | Reuses the child's session to send a follow-up turn — only allowed on COMPLETED/FAILED tasks (NOT on RUNNING or LOST) |
| `background_agents_clear_completed_task` | `(task_id: int) -> str` | Removes the task entry and frees its child session — only for terminal-state tasks (NOT RUNNING) |

All six are registered with `approval_mode="never_require"` — the LLM can invoke them without human-in-the-loop approval prompts.

### `BackgroundTaskStatus` enum (verified at [`_background_agents.py:L42-L48`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_background_agents.py#L42-L48))

```python
class BackgroundTaskStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    LOST = "lost"
```

| Status | When | What the parent agent should do |
|---|---|---|
| `RUNNING` | Task created, asyncio.Task in-flight | Wait (`wait_for_first_completion`) or check later (`get_all_tasks`) |
| `COMPLETED` | asyncio.Task finished without exception | Read `get_task_results`; optionally `continue_task` to extend; eventually `clear_completed_task` to free memory |
| `FAILED` | asyncio.Task raised or was cancelled | Read `get_task_results` for the error message; `continue_task` allowed (e.g., retry with revised input); `clear_completed_task` to drop |
| `LOST` | asyncio.Task reference is no longer in `runtime.in_flight_tasks` (e.g., provider instance recreated, process restarted) | **Cannot be resumed** — `continue_task` returns an error; only `clear_completed_task` works. Start a new task instead. |

### Two-layer state model

| Layer | Where it lives | Persisted across process restart? |
|---|---|---|
| **Serializable provider state** — `{"next_task_id": N, "tasks": [BackgroundTaskInfo.to_dict(), ...]}` — keyed in `session.state[source_id]` | `AgentSession` state (whatever your session backend persists) | **Yes** (if your session is persisted, e.g., to Cosmos or file) |
| **Runtime state** — in-flight `asyncio.Task` objects + child `AgentSession` handles — keyed in `BackgroundAgentsProvider._runtime[session_id]` | Provider instance memory (not serializable) | **No** — on restart, all in-flight tasks become orphaned |

When the parent agent resumes after a restart, `_refresh_task_state` (called by every read tool) sees that an entry's status is still `RUNNING` in the persisted state but the asyncio.Task isn't in `_runtime.in_flight_tasks` → it marks the entry as `LOST` and persists the transition.

### Constructor validation (verified at [`_background_agents.py:L132-L152`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_background_agents.py#L132-L152))

```python
class BackgroundAgentsProvider(ContextProvider):
    def __init__(
        self,
        agents: Sequence[SupportsAgentRun],  # required, non-empty
        *,
        source_id: str = DEFAULT_BACKGROUND_AGENTS_SOURCE_ID,  # "background_agents"
        instructions: str | None = None,  # uses DEFAULT_BACKGROUND_AGENTS_INSTRUCTIONS template if None
    ) -> None: ...
```

Raises `ValueError` if:
- `agents` is empty
- Any agent's `name` is empty or whitespace-only
- Two agents share a name (case-insensitive: `"researcher"` and `"RESEARCHER"` collide)

The default `instructions` template uses a `{background_agents}` placeholder that the provider substitutes with a `"- <name>: <description>"` listing for the LLM.

## Concurrency semantics — operational limits

This pattern is new in this KB; the following caveats are unique to background-agents and easy to overlook.

### 1. No built-in timeout

`background_agents_wait_for_first_completion(task_ids)` calls `asyncio.wait(...)` with no `timeout=` parameter. If every selected task hangs (e.g., the child agent's LLM call stalls), the parent **blocks indefinitely**. Mitigations:

- Constrain child agents with explicit per-run timeouts via your chat client's settings.
- Build a sentinel "watchdog" child agent that fails fast and include it in the `task_ids` list.

### 2. `wait_for_first_completion([])` returns an error string

The LLM is responsible for not calling this with an empty list. The tool returns `"Error: No task IDs provided."` rather than raising — your parent agent should treat it as a recoverable error and ask itself why the list was empty.

### 3. Starting the same child concurrently is allowed

Each `start_task` call mints a new task ID and creates a fresh `AgentSession` on the child. Two concurrent `start_task(agent_name="researcher", ...)` calls produce two independent tasks with independent histories — they do **not** share state.

### 4. `wait_for_first_completion` does NOT cancel the others

When the first task completes, the remaining `asyncio.Task`s in the `waitable` list keep running. The parent must either wait for them later, call `get_task_results` after they finish naturally, or `clear_completed_task` when they reach terminal state. There is no `cancel_task` tool exposed.

### 5. `continue_task` is gated by status

Per [`_background_agents.py:L444-L450`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_background_agents.py#L444-L450):

- `LOST` → returns `"Error: Task X cannot be continued because its session was lost. Start a new task instead."`
- `RUNNING` → returns `"Error: Task X is still running. Wait for it to complete before continuing."`
- `COMPLETED` / `FAILED` → proceeds, reusing the child's `sub_session` so conversation history is preserved across the resume

### 6. Results are text-only

`background_agents_get_task_results` returns `AgentResponse.text`. There is no path to retrieve structured outputs, tool-call traces, or intermediate messages from the sub-agent. If you need structured cross-agent data flow, use [`multi-agent-workflow.md`](multi-agent-workflow.md) (`WorkflowBuilder`) instead.

### 7. Parent session sharing is unsafe

Each parent `AgentSession` has its own `_RuntimeState` keyed in `BackgroundAgentsProvider._runtime[session_id]`. Two **external concurrent** parent runs against the *same* `AgentSession` could race on `_get_runtime` / `runtime.in_flight_tasks`. Either keep one in-flight `agent.run(...)` per session at a time, or use separate sessions per concurrent caller.

## Gotchas

### ⚠️ Experimental — pin tight, expect change

`BackgroundAgentsProvider` is `@experimental(feature_id=ExperimentalFeature.HARNESS)`. The 6 tool names are part of the contract and may rename in a future minor version (compare to PR [#6107](https://github.com/microsoft/agent-framework/pull/6107) / [#6071](https://github.com/microsoft/agent-framework/pull/6071) which renamed TodoProvider / ModeProvider tool names in 1.8.0). Don't bake the tool names into hosted-tool allow-lists or eval rubrics without a version-fence.

### Live-test status

The code example above is **verified against upstream source** but **was not executed against a live Foundry endpoint** as part of this KB authoring (X-stage policy: compile + AST only, no live API calls). Run it yourself before relying on it.

### `source_id` collision

If you accidentally instantiate two `BackgroundAgentsProvider` instances with the same `source_id` (default `"background_agents"`) on the same parent agent, they will share the same persisted state slot in `session.state` but have **independent** `_runtime` dicts → guaranteed LOST status on every `_refresh_task_state` call. Always give multiple providers distinct `source_id` values.

## See also

- Pattern: [`harness-agent.md`](harness-agent.md) — `create_harness_agent` (which child agents in the example above are built with)
- Pattern: [`multi-agent-workflow.md`](multi-agent-workflow.md) — `WorkflowBuilder` is the alternative for **structured** multi-agent orchestration (DAG, typed messages, checkpointing)
- API ref: [`compaction.md`](../api-reference/1.8.0/compaction.md) — context-window management for the parent and each child
- API ref: [`feature-stages.md`](../api-reference/1.8.0/feature-stages.md) — `@experimental` warning model
- Anti-pattern: existing KB anti-patterns under `kb/anti-patterns/` — verify none are violated by the example
