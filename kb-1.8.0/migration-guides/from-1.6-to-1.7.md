# Migration Guide: 1.6.0 → 1.7.0

> Released: May 28, 2026 (6 days after 1.6.0)
> Pinned in this template: `agent-framework-foundry==1.7.0`
> Upstream release notes: [python-1.7.0](https://github.com/microsoft/agent-framework/releases/tag/python-1.7.0)
> Diff scope: 35 commits, 300 files across `python/` between `python-1.6.0..python-1.7.0`

## TL;DR

| # | Change | Package | Severity | Action required |
|---|--------|---------|----------|-----------------|
| 1 | Declarative actions `AppendValue`/`EmitEvent`/`Confirmation`/`WaitForInput` removed; `Switch`/`Goto` renamed to `ConditionGroup`/`GotoAction` (PR #6126) | `agent-framework-declarative` beta | **🔴 BREAKING** | Rewrite YAML / executor lists; see § 1 |
| 2 | `TodoProvider` exposes renamed tool names: `add_todos` → `todos_add`, etc. (PR #6107) | `agent-framework-core` | **🟡 Silent breaker** | Update hosted-tool allow-lists, eval rubrics, .NET interop wiring; see § 2 |
| 3 | `AgentModeProvider` exposes renamed tool names: `set_mode` → `mode_set`, `get_mode` → `mode_get` (PR #6071) | `agent-framework-core` | **🟡 Silent breaker** | Same as #2; see § 3 |
| 4 | `create_harness_agent` + `DEFAULT_HARNESS_INSTRUCTIONS` (PR #6041) | `agent-framework-core` | 🟢 Additive (`@experimental`) | Opt-in; see § 4 + [`harness-agent.md`](../patterns/harness-agent.md) |
| 5 | `BackgroundAgentsProvider` + `BackgroundTaskInfo` + `BackgroundTaskStatus` (PR #6069) | `agent-framework-core` | 🟢 Additive (`@experimental`) | Opt-in; see § 5 + [`background-agents.md`](../patterns/background-agents.md) |
| 6 | `to_prompt_agent(agent)` for Foundry prompt-agent publication (PR #5959) | `agent-framework-foundry` | 🟢 Additive (`@experimental`) | Opt-in; see § 6 + [`foundry-prompt-agent.md`](../patterns/foundry-prompt-agent.md) |
| 7 | `ContextWindowCompactionStrategy` — token-budget-aware compaction (PR #6041) | `agent-framework-core` | 🟢 Additive | Opt-in or via `create_harness_agent` default; see § 7 + [`compaction.md`](../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy) |
| 8 | Various Foundry / OpenAI / DevUI bugfixes | various | 🔵 Bugfix | None required; see § Bug fixes |
| 9 | No new transitive deps; only version-floor bumps in `agent-framework-foundry`'s requires | — | ⚪ Dep | See § Dependencies |

**Bottom line for this template**: 1.7.0 is **safe to adopt** — none of the BREAKING or silent-breaker items affect any code in `templates/`, `examples/`, or `workshop/` in this repo. The four `@experimental` additions are opt-in and have new dedicated KB pattern docs.

---

## 1. Declarative actions removed and renamed (PR #6126) 🔴 BREAKING

PR [#6126](https://github.com/microsoft/agent-framework/pull/6126) removes Python-only declarative actions that have no C# canonical equivalent and renames the Python-only aliases `Switch`/`Goto` to the C#-canonical `ConditionGroup`/`GotoAction`. **15 files** in `python/packages/declarative/` are affected (executor classes + registry + validation rows + public exports + tests all deleted).

> [!NOTE]
> This change is shipped in the **`agent-framework-declarative`** package's beta `1.0.0b260528` (the declarative package only publishes betas). It is independent of the `agent-framework-foundry==1.7.0` stable pin used by this template. If you do NOT use declarative workflows, you are not affected.

**Removed actions (4):**

| Action | Replacement |
|---|---|
| `AppendValue` | (no replacement) — use `SendActivity` or a custom executor |
| `EmitEvent` | `SendActivity` (the canonical user-facing emit primitive) |
| `Confirmation` | `RequestExternalInputExecutor` (HITL pattern) |
| `WaitForInput` | `RequestExternalInputExecutor` (HITL pattern) |

**Renamed actions (2 aliases):**

| Old (Python-only alias) | New (C# canonical) |
|---|---|
| `Switch` | `ConditionGroup` |
| `Goto` | `GotoAction` |

**Before (1.6.0):**

```yaml
# my-workflow.yaml
actions:
  - kind: EmitEvent
    name: notify_user
    value: "Step complete"
  - kind: Switch
    on: order_total
    cases:
      - value: ">100"
        then:
          - kind: Goto
            target: high_value_path
```

**After (1.7.0):**

```yaml
# my-workflow.yaml
actions:
  - kind: SendActivity
    name: notify_user
    text: "Step complete"
  - kind: ConditionGroup
    on: order_total
    cases:
      - value: ">100"
        then:
          - kind: GotoAction
            target: high_value_path
```

### Migration step

1. `grep -rn "kind: \(AppendValue\|EmitEvent\|Confirmation\|WaitForInput\|Switch\|Goto\)" your-workflows/` — list every YAML using the removed/renamed kinds.
2. Rewrite each occurrence using the table above.
3. For YAMLs you cannot edit (e.g., legacy customer files), the runtime now emits an "unknown kind" warning and **silently skips** the executor — debug visibility, not crash. Re-run any integration test that exercised those paths.
4. See [`../api-reference/1.8.0/declarative.md`](../api-reference/1.8.0/declarative.md) and [`../anti-patterns/declarative-pitfalls.md`](../anti-patterns/declarative-pitfalls.md) for the updated catalog.

---

## 2. `TodoProvider` tool names renamed (PR #6107) 🟡 Silent breaker

PR [#6107](https://github.com/microsoft/agent-framework/pull/6107) renames the tool names exposed by `TodoProvider` to the `todos_*` convention (consistent with `BackgroundAgentsProvider`'s `background_agents_*` and `ModeProvider`'s new `mode_*` — see § 3). The PR title carries **no `[BREAKING]` tag**, but the tool names are part of the user-visible API surface for any caller that pins to specific tool names.

| Old (1.6.0) | New (1.7.0) |
|---|---|
| `add_todos` | `todos_add` |
| `complete_todos` | `todos_complete` |
| `remove_todos` | `todos_remove` |
| `get_remaining_todos` | `todos_get_remaining` |
| `get_all_todos` | `todos_get_all` |

### When this matters

You are affected if any of the following pin to the old names:

- **Hosted-tool allow-lists** (Foundry agent definitions, evaluation rubrics, etc.) that gate which tools an LLM may call by name
- **Evaluation rubrics** that score agent behavior by counting calls to specific tool names
- **.NET ↔ Python interop** wiring that referenced the Python tool names from C# code
- **Audit log greps** built on the old names
- **DevUI screenshots / docs** that include tool-call traces

This template's own templates / examples do not reference these tool names in code; the impact here is **informational for downstream users**.

### Migration step

```bash
# Find call sites in your code / config:
grep -rn "add_todos\|complete_todos\|remove_todos\|get_remaining_todos\|get_all_todos" .

# In each hit, swap to the new name per the table.
```

---

## 3. `AgentModeProvider` tool names renamed (PR #6071) 🟡 Silent breaker

PR [#6071](https://github.com/microsoft/agent-framework/pull/6071) renames `AgentModeProvider`'s tool names to the `mode_*` convention. Same `no [BREAKING] tag` caveat as § 2.

| Old (1.6.0) | New (1.7.0) |
|---|---|
| `set_mode` | `mode_set` |
| `get_mode` | `mode_get` |

### Migration step

```bash
grep -rn "\bset_mode\b\|\bget_mode\b" .
```

Swap to the new names per the table.

---

## 4. NEW: `create_harness_agent` — batteries-included agent factory (PR #6041, `@experimental`)

PR [#6041](https://github.com/microsoft/agent-framework/pull/6041) introduces `create_harness_agent` — a single factory call that bundles **history**, **compaction**, **TodoProvider**, **AgentModeProvider** (defaults ON) plus optional **MemoryContextProvider** / **SkillsProvider** and auto-added **web search** (when the client supports it). Also adds `DEFAULT_HARNESS_INSTRUCTIONS` (the default "think before acting, ≤4 tool calls in a row" system-prompt policy).

**Gated by** `@experimental(feature_id=ExperimentalFeature.HARNESS)` — pin tightly and re-validate on every upgrade.

```python
from agent_framework import create_harness_agent
from agent_framework.foundry import FoundryChatClient

agent = create_harness_agent(
    FoundryChatClient(project_endpoint=..., model=..., credential=...),
    name="research-assistant",
    agent_instructions="Cite sources.",
    max_context_window_tokens=128_000,
    max_output_tokens=16_384,
)
```

### Migration step

None — this is opt-in. If you were previously assembling these providers manually, the harness factory replaces ~30 lines of boilerplate with one call. Read the full pattern doc: **[`../patterns/harness-agent.md`](../patterns/harness-agent.md)**.

---

## 5. NEW: `BackgroundAgentsProvider` — non-blocking sub-agent delegation (PR #6069, `@experimental`)

PR [#6069](https://github.com/microsoft/agent-framework/pull/6069) introduces `BackgroundAgentsProvider`, `BackgroundTaskInfo`, `BackgroundTaskStatus`, and `DEFAULT_BACKGROUND_AGENTS_SOURCE_ID`. A parent agent can delegate work to named background agents that run as concurrent `asyncio.Task`s, with status (`RUNNING`/`COMPLETED`/`FAILED`/`LOST`) and text results retrievable via 6 exposed tools (`background_agents_*`).

**Gated by** `@experimental(feature_id=ExperimentalFeature.HARNESS)`.

```python
from agent_framework import BackgroundAgentsProvider, create_harness_agent

researcher = create_harness_agent(client, name="researcher", ...)
coder = create_harness_agent(client, name="coder", ...)

background = BackgroundAgentsProvider(agents=[researcher, coder])
parent = create_harness_agent(client, context_providers=[background], ...)
```

### Migration step

None — opt-in. **Caveat**: background task runtime state (in-flight `asyncio.Task` objects + child sessions) is **in-memory only**; tasks become `LOST` after a process restart. See **[`../patterns/background-agents.md`](../patterns/background-agents.md) § Concurrency semantics** for the seven operational caveats unique to this pattern.

---

## 6. NEW: `to_prompt_agent` — publish a local Agent as a hosted Foundry prompt agent (PR #5959, `@experimental`)

PR [#5959](https://github.com/microsoft/agent-framework/pull/5959) introduces `to_prompt_agent(agent)` in `agent-framework-foundry`. It converts an `Agent` bound to a `FoundryChatClient` into a `PromptAgentDefinition` ready to publish via `AIProjectClient.agents.create_version(definition)`.

**Gated by** `@experimental(feature_id=ExperimentalFeature.TO_PROMPT_AGENT)`.

> [!IMPORTANT]
> The PR description mentions a `deploy_as_prompt_agent` convenience wrapper, but **that function does NOT exist** in `agent-framework-foundry==1.7.0`. Only `to_prompt_agent` shipped. The `AIProjectClient.agents.create_version(...)` publish step is your code's responsibility.

```python
from agent_framework.foundry import FoundryChatClient, to_prompt_agent

agent = FoundryChatClient(...).as_agent(name="weather-bot", tools=[get_weather])
definition = to_prompt_agent(agent)
# Publish (your code):
# await aiproject_client.agents.create_version(definition)
```

### Migration step

None — opt-in. **Caveat**: local Python function tools are translated to **declarations only** — the published prompt agent advertises the schema but cannot execute your local Python server-side. Use hosted SDK tools (`client.get_web_search_tool()`, `client.get_code_interpreter_tool()`, `client.get_mcp_tool()`) for tools that must "just work" post-publish. See **[`../patterns/foundry-prompt-agent.md`](../patterns/foundry-prompt-agent.md)** for the full tool-translation matrix and constraints.

---

## 7. NEW: `ContextWindowCompactionStrategy` — token-budget compaction (PR #6041)

PR [#6041](https://github.com/microsoft/agent-framework/pull/6041) adds a 7th compaction strategy to the existing 6 in 1.6.0. `ContextWindowCompactionStrategy` runs a two-phase pipeline internally — tool-result eviction at `tool_eviction_threshold × max_input_tokens` (default `0.5`), then truncation at `truncation_threshold × max_input_tokens` (default `0.8`) — keeping the most recent N tool-call groups (default `4`) intact.

```python
from agent_framework import ContextWindowCompactionStrategy, CompactionProvider

strategy = ContextWindowCompactionStrategy(
    max_context_window_tokens=128_000,
    max_output_tokens=16_384,
)
provider = CompactionProvider(before_strategy=strategy, ...)
```

This is also the **default `before_strategy`** when you use `create_harness_agent` (verified at [`_harness/_agent.py:L79`](https://github.com/microsoft/agent-framework/blob/python-1.7.0/python/packages/core/agent_framework/_harness/_agent.py#L79)).

### Migration step

None — this is purely additive. If you currently use `SlidingWindowStrategy` or `SummarizationStrategy` explicitly, no change is forced. See **[`../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy`](../api-reference/1.8.0/compaction.md#contextwindowcompactionstrategy)** for the full algorithm, constants, and decision table comparing all 7 strategies.

---

## Bug fixes (Python-affecting subset)

| # | PR | Component | Fix |
|---|----|-----------|-----|
| F1 | [#6040](https://github.com/microsoft/agent-framework/pull/6040) | `foundry` | `FoundryAgent` now forwards `default_headers` into the underlying chat client (fixes #6027). If you injected custom request headers via `default_headers` and they were being silently dropped, they now flow through. |
| F2 | [#5861](https://github.com/microsoft/agent-framework/pull/5861) | `foundry_hosting` | Hosted handoff argument serialization correctness fix. |
| F3 | [#6049](https://github.com/microsoft/agent-framework/pull/6049) | `foundry_hosting` | Hosted checkpoints can now restore `MessageRole` values that previously failed deserialization. |
| F4 | [#6037](https://github.com/microsoft/agent-framework/pull/6037) | `openai` | Citation `get_url` metadata preserved through response post-processing. |
| F5 | [#5734](https://github.com/microsoft/agent-framework/pull/5734) | `openai` | Chat Completions streaming now guards against null `deltas` (3rd-party providers that diverge from the OpenAI spec no longer crash). |
| F6 | [#6028](https://github.com/microsoft/agent-framework/pull/6028) + [#6029](https://github.com/microsoft/agent-framework/pull/6029) | `openai` | Stream wrappers without `.headers` are read defensively (no `AttributeError` from custom HTTP clients). |
| F7 | [#5996](https://github.com/microsoft/agent-framework/pull/5996) | `core` | `@experimental` warnings now point at the user's call site, not the stdlib internals. Stack traces become useful again. |
| F8 | [#6050](https://github.com/microsoft/agent-framework/pull/6050) | `declarative` | Declarative `Foreach` body exit wiring fix. |
| F9 | [#6038](https://github.com/microsoft/agent-framework/pull/6038) | `devui` | DevUI streaming memory growth regression fix. Long DevUI sessions no longer leak. |

### Migration step

None — bugfixes only. If your test suite was working around F1/F7/F9, you can simplify after upgrading.

---

## Dependencies

| Package | 1.6.0 → 1.7.0 change |
|---|---|
| `agent-framework-core` | **No `requires_dist` change** (verified via PyPI diff) |
| `agent-framework-foundry` | Only version-floor bumps: `agent-framework-core>=1.7.0`, `agent-framework-openai>=1.7.0`. No new transitive deps. |
| `agent-framework-chatkit` | `openai-chatkit>=1.6.4` floor raised (not used in this template). |

**Sub-packages with ZERO changes** (verified — no files in diff): `redis`, `azure-cosmos`, `purview`, `github-copilot`, `hyperlight`, `monty`, `orchestrations`, `durabletask`, `ag-ui`, `azurefunctions`.

### Migration step

In `requirements.txt`, bump:

```text
agent-framework-foundry==1.7.0
agent-framework-core==1.7.0
agent-framework-openai==1.7.0
```

This template's 6 `requirements.txt` files (root + 4 templates + 1 example) were already bumped during the 1.6.0 → 1.7.0 template spawn.

---

## Validation checklist after upgrade

```bash
# 1. Reinstall cleanly:
pip install --upgrade --force-reinstall agent-framework-foundry==1.7.0

# 2. Verify imports work (incl. new APIs):
python -c "from agent_framework import create_harness_agent, BackgroundAgentsProvider, ContextWindowCompactionStrategy; print('core OK')"
python -c "from agent_framework.foundry import FoundryChatClient, to_prompt_agent; print('foundry OK')"

# 3. Verify your existing scripts still compile:
python -m compileall -q src/ templates/ examples/

# 4. Smoke test one agent (canonical path unchanged):
python src/demo1_run_agent.py

# 5. Confirm no leftover references to removed declarative actions:
grep -rn "kind: \(AppendValue\|EmitEvent\|Confirmation\|WaitForInput\|Switch\|Goto\)" . || echo "clean"

# 6. Confirm no leftover references to renamed TodoProvider / ModeProvider tool names:
grep -rn "\(add_todos\|complete_todos\|remove_todos\|get_remaining_todos\|get_all_todos\|\\bset_mode\\b\|\\bget_mode\\b\)" . || echo "clean"
```

If steps 5 and 6 print `clean`, you have no exposure to the silent breakers.

---

## See also

- [`cumulative-since-1.0.md`](cumulative-since-1.0.md) — all changes since 1.0 GA (1.7 row appended in X-8)
- [`from-1.5-to-1.6.md`](from-1.5-to-1.6.md) — previous step (instrumentation default ON, etc.)
- [`../anti-patterns/declarative-pitfalls.md`](../anti-patterns/declarative-pitfalls.md) — updated declarative anti-patterns reflecting PR #6126
- [`../patterns/harness-agent.md`](../patterns/harness-agent.md) — full pattern doc for § 4
- [`../patterns/background-agents.md`](../patterns/background-agents.md) — full pattern doc for § 5
- [`../patterns/foundry-prompt-agent.md`](../patterns/foundry-prompt-agent.md) — full pattern doc for § 6
- [`../api-reference/1.8.0/compaction.md`](../api-reference/1.8.0/compaction.md) — full API ref including § 7 `ContextWindowCompactionStrategy`
- [`../api-reference/1.8.0/declarative.md`](../api-reference/1.8.0/declarative.md) — updated declarative reference reflecting PR #6126
- [Microsoft Agent Framework `python-1.7.0` release](https://github.com/microsoft/agent-framework/releases/tag/python-1.7.0)
