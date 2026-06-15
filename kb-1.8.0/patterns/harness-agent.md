# Pattern: Harness Agent — Batteries-Included Agent Factory

> Status: ⚠️ **Experimental** — `@experimental(feature_id=ExperimentalFeature.HARNESS)`
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent_framework/_harness/_agent.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_agent.py) (349 LOC)
> See also: [API ref — `compaction.md`](../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy), [`memory-experimental.md`](../api-reference/1.8.0/memory-experimental.md), [`canonical-agent-creation.md`](canonical-agent-creation.md)

> [!WARNING]
> `create_harness_agent` and every provider it wires are decorated with `@experimental(feature_id=ExperimentalFeature.HARNESS)`. The factory signature, default-instructions text, and bundled providers **can and will change** between minor versions. Pin `agent-framework-foundry==1.8.0` exactly and re-validate on every Agent Framework upgrade. See [`feature-stages.md`](../api-reference/1.8.0/feature-stages.md) for the full warning model and how to silence/track `[HARNESS] ... ExperimentalWarning`.

## Goal

Stand up a fully-wired `Agent` in **one factory call** instead of manually assembling history, compaction, todo, mode, and (optionally) memory/skills/web-search providers yourself. `create_harness_agent` is the v1.8.0-introduced "happy path" for agents that want the framework's default operating policy out-of-the-box.

## When to use this pattern

- ✅ You want one agent with **persistent transcript + context-window compaction + a todo list + mode tracking**, wired identically to the framework reference.
- ✅ You're prototyping and want **sensible defaults for `before_strategy` / `after_strategy`** without reading [`compaction.md`](../api-reference/1.8.0/compaction.md) cover-to-cover.
- ✅ Your client implements `SupportsWebSearchTool` (e.g., `FoundryChatClient` with a Bing connection) and you want web search auto-wired.
- ❌ You only need a bare agent with one function tool — use [`canonical-agent-creation.md`](canonical-agent-creation.md) instead (no harness overhead).
- ❌ You need **production-grade** memory or skills — these are still `@experimental`; see the warning above.
- ❌ You're building a `FoundryChatClient`-bound agent that you plan to publish as a hosted Foundry prompt agent — `create_harness_agent` returns a local `Agent`; for publication see [`foundry-prompt-agent.md`](foundry-prompt-agent.md).

## Code

Minimal runnable example (verified against `_harness/_agent.py:L189-L203` upstream docstring example):

```python
import asyncio
import os
from pathlib import Path

from agent_framework import create_harness_agent
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

        agent = create_harness_agent(
            client,
            name="research-assistant",
            agent_instructions="You are a research assistant. Cite sources.",
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
        )

        session = agent.create_session()
        response = await agent.run(
            "Summarize the Agent Framework 1.8.0 changelog highlights.",
            session=session,
        )
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
```

> [!IMPORTANT]
> `max_context_window_tokens` and `max_output_tokens` are **required** keyword arguments. The factory raises `ValueError` if either is invalid (rules below).

## How it works — what `create_harness_agent` actually bundles

The factory wires the following on your behalf. **Read this table carefully — not everything you might expect is on by default.** ([source: `_harness/_agent.py:L94-L137,L272-L344`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_agent.py#L94-L344))

| Concern | Default behavior | How to disable / customize |
|---|---|---|
| **History** | `InMemoryHistoryProvider()` always added first | Pass `history_provider=<your provider>` |
| **Compaction** | `CompactionProvider` with `before_strategy=ContextWindowCompactionStrategy(...)`, `after_strategy=ToolResultCompactionStrategy(keep_last_tool_call_groups=2)` | `disable_compaction=True`, or pass `before_compaction_strategy=...`/`after_compaction_strategy=...` |
| **TodoProvider** | **ON** — `TodoProvider()` added unless disabled | `disable_todo=True`, or pass `todo_provider=<custom>` |
| **AgentModeProvider** | **ON** — `AgentModeProvider()` added unless disabled | `disable_mode=True`, or pass `mode_provider=<custom>` |
| **MemoryContextProvider** | **OPT-IN** — added only when `memory_store=<MemoryStore>` is passed | Provide `memory_store=...` to enable; `disable_memory=True` to skip even when store provided |
| **SkillsProvider** | **OPT-IN** — added only when `skills_provider=...` or `skills_paths=[...]` is passed | Provide one or both kwargs |
| **Web search** | **AUTO** — added if the client implements `SupportsWebSearchTool` (e.g., `FoundryChatClient` with Bing); logs a `WARNING` if the client doesn't support it | `disable_web_search=True` to skip the auto-add and suppress the warning |
| **OpenTelemetry** | Always — sets `agent.otel_provider_name = "microsoft.agent_framework.harness"` (or your `otel_provider_name`) | Pass `otel_provider_name="<your-name>"` |
| **`require_per_service_call_history_persistence`** | Always `True` — transcript persists after every model call | Not user-tunable from this factory |

> [!NOTE]
> The factory uses kwarg-only API style (`*` in the signature). Forgetting `max_context_window_tokens=...` / `max_output_tokens=...` as kwargs (e.g., passing them positionally) raises `TypeError`.

### Default `before_strategy` = `ContextWindowCompactionStrategy`

The harness's default `before_strategy` is `ContextWindowCompactionStrategy` (new in 1.8.0). It runs a two-phase pipeline internally — tool-result eviction at `tool_eviction_threshold × max_input_tokens`, then truncation at `truncation_threshold × max_input_tokens` — so the prompt stays within your model's input budget without losing the most recent tool-call group(s).

See [`api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy`](../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy) for the full algorithm, validation rules, and constants.

### `DEFAULT_HARNESS_INSTRUCTIONS` (system-prompt policy)

When you don't pass `harness_instructions=...`, the factory prepends `DEFAULT_HARNESS_INSTRUCTIONS` (verified at [`_harness/_agent.py:L37-L52`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_agent.py#L37-L52)) to your `agent_instructions`. The full text is:

```text
You are a helpful AI assistant that uses tools to complete tasks.

## General guidelines

- Think through the task before acting. Break complex work into clear steps.
- Use the tools available to you to gather information, perform actions, and verify results.
- Explain your reasoning and thought process as you work through tasks.
- Explain what you learned and what you are going to do next between tool calls, so the user can follow along with your thought process.
- Avoid making more than 4 tool calls in a row without explaining what you are doing.
- If a tool call fails or returns unexpected results, adapt your approach rather than repeating the same call.
- When you have completed the task, present a clear and concise summary of what you did and what you found.
```

Override options:

| Want… | Pass… |
|---|---|
| The default harness policy + your domain-specific instructions appended | `agent_instructions="..."` only (most common) |
| Your own harness-level policy | `harness_instructions="<your policy text>"` |
| No harness instructions at all (only your `agent_instructions`) | `harness_instructions=""` (empty string explicitly) |

### Validation rules (`ValueError` at factory call time)

From `_harness/_agent.py:L272-L277`:

| Rule | Error message |
|---|---|
| `max_context_window_tokens > 0` | `"max_context_window_tokens must be positive."` |
| `max_output_tokens >= 0` | `"max_output_tokens must be non-negative."` |
| `max_output_tokens < max_context_window_tokens` | `"max_output_tokens must be less than max_context_window_tokens."` |

These run **before** any provider is constructed, so misconfiguration is loud and immediate.

## Gotchas

### 1. ⚠️ Experimental — pin tight, expect change

`create_harness_agent` is gated by `ExperimentalFeature.HARNESS`. Importing it emits an `ExperimentalWarning` the first time. Treat it like any other experimental API: pin `agent-framework-foundry==1.8.0` exactly (no caret/tilde), and re-read the harness module on every upgrade.

### 2. TodoProvider / ModeProvider tool names are renamed in 1.8.0

PR [#6107](https://github.com/microsoft/agent-framework/pull/6107) and PR [#6071](https://github.com/microsoft/agent-framework/pull/6071) renamed the tool names exposed by `TodoProvider` and `AgentModeProvider` (no `[BREAKING]` flag in the PR titles, but observable):

| Old (1.6.0) | New (1.8.0) | Provider |
|---|---|---|
| `add_todos` | `todos_add` | `TodoProvider` |
| `complete_todos` | `todos_complete` | `TodoProvider` |
| `remove_todos` | `todos_remove` | `TodoProvider` |
| `get_remaining_todos` | `todos_get_remaining` | `TodoProvider` |
| `get_all_todos` | `todos_get_all` | `TodoProvider` |
| `set_mode` | `mode_set` | `AgentModeProvider` |
| `get_mode` | `mode_get` | `AgentModeProvider` |

If you have hosted-tool allow-lists, evaluation rubrics, audit log greps, or .NET ↔ Python interop wiring built on the old names, **update them** when adopting `create_harness_agent`. This repo's templates don't reference these tool names in code, so the impact here is informational, but downstream users should pay attention. Full migration guidance lives in [`migration-guides/from-1.6-to-1.7.md`](../migration-guides/from-1.6-to-1.7.md).

### 3. Web-search auto-add logs a WARNING on unsupported clients

When `disable_web_search=False` (the default) and your client does **not** implement `SupportsWebSearchTool` (e.g., a vanilla `OpenAIChatClient`), the factory logs:

```text
Web search tool not available: client 'OpenAIChatClient' does not implement SupportsWebSearchTool. Set disable_web_search=True to suppress this warning.
```

Pass `disable_web_search=True` to silence it.

### 4. `MemoryContextProvider` is opt-in even when "memory" is in the docstring

The factory's docstring lists `MemoryContextProvider` among the bundled features, but it is **only attached when you pass `memory_store=<MemoryStore>`**. Don't assume your harness agent has memory by default. To enable, construct a `MemoryFileStore` (or another `MemoryStore` subclass) and pass it explicitly — see [`memory-experimental.md`](../api-reference/1.8.0/memory-experimental.md).

### 5. Skills are also opt-in (and silently absent if you forget)

Same caveat for skills: `SkillsProvider` is only attached when `skills_provider=...` **or** `skills_paths=[...]` is passed. There is no warning if you intended to attach skills but forgot the kwarg — your agent will simply have none.

### 6. Live-test status

The example above is **verified against upstream source** ([`_harness/_agent.py:L189-L203`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_harness/_agent.py#L189-L203)) but **was not executed against a live Foundry endpoint** as part of this KB authoring (X-stage policy: compile + AST only, no live API calls). Treat it as "shape-verified" — run it yourself before relying on it in production.

## See also

- API ref: [`compaction.md` § `ContextWindowCompactionStrategy`](../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy) — what the default `before_strategy` actually does
- API ref: [`memory-experimental.md`](../api-reference/1.8.0/memory-experimental.md) — `MemoryStore` / `MemoryContextProvider` (the opt-in memory bundle)
- API ref: [`feature-stages.md`](../api-reference/1.8.0/feature-stages.md) — `@experimental` warning model and how to silence
- Pattern: [`canonical-agent-creation.md`](canonical-agent-creation.md) — the lower-level alternative if you don't want the harness bundle
- Pattern: [`background-agents.md`](background-agents.md) — `BackgroundAgentsProvider` (delegate to background sub-agents, also harness-experimental)
- Pattern: [`foundry-prompt-agent.md`](foundry-prompt-agent.md) — `to_prompt_agent` to publish a local Agent as a hosted Foundry prompt agent
- Migration: [`from-1.6-to-1.7.md`](../migration-guides/from-1.6-to-1.7.md) — full 1.6 → 1.7 delta including the TodoProvider / ModeProvider tool-name renames
