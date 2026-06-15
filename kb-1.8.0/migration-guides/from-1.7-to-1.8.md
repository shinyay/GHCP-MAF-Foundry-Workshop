# Migration Guide: 1.7.0 → 1.8.0

> Released: June 4, 2026 (7 days after 1.7.0)
> Pinned in this template: `agent-framework-foundry==1.8.0`
> Upstream release notes: [python-1.8.0](https://github.com/microsoft/agent-framework/releases/tag/python-1.8.0)
> Verified sources: [`_evaluation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L370-L505), [`_foundry_evals.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L519-L760)

If you are running 1.7.x and want 1.8.0, this guide tells you what changes for template consumers first. It is intentionally narrow: drop-in upgrade posture, opt-in APIs you may adopt, and the upstream BREAKING changes this template does not use.

## TL;DR

| # | Change | Package | Severity | Action required |
|---|--------|---------|----------|-----------------|
| 1 | Adaptive Evals consumer surface (`GeneratedEvaluatorRef`, per-dimension scores, assert helpers) (PR #6101) | `agent-framework-foundry` + core evals | 🟢 Additive (`@experimental`) | Opt in only; author rubrics in Foundry portal |
| 2 | `MCPSkillsSource(client: ClientSession)` for MCP-backed skill catalogues (PR #6169) | `agent-framework-core` | 🟢 Additive (`@experimental`) | Opt in only; note uppercase `MCP` class name |
| 3 | `FunctionInvocationContext.add_tools` / `remove_tools` (PR #6233) | `agent-framework-core` | 🟢 Additive (`@experimental`) | Opt in only for progressive tool exposure |
| 4 | `AgentFileStore` / `FileAccessProvider` (PR #6099) | `agent-framework-core` | 🟢 Additive | Opt in only for controlled agent file access |
| 5 | `BackgroundAgentsProvider` task-lifecycle types (PR #6155) | `agent-framework-core` | 🟢 Additive (`@experimental`) | Opt in only; factory remains `create_harness_agent(...)` |
| 6 | `github-copilot-sdk@1.0.0` API stabilization (PR #6286) | `github-copilot-sdk` | 🔴 Upstream BREAKING | Not used by this template |
| 7 | Skills experimental API refactor | `agent-framework-core` | 🔴 Upstream BREAKING | Only affects direct low-level Skills callers |
| 8 | Foundry / MCP / compaction / observability quality fixes | various | 🔵 Bugfix | None required |

**Bottom line for this template**: 1.8.0 is a **drop-in upgrade** for shipped templates and prompts. No required code change unless your derived repo opted into the affected upstream experimental surfaces.

---

## Consumer impact for this template

The canonical agent creation path (`FoundryChatClient(...).as_agent(...)`), async resource cleanup, streaming via `run(stream=True)`, DevUI workshop flags, and instrumentation posture are unchanged from 1.7.0.

> [!NOTE]
> The dependency envelope is unchanged from 1.7.0. Reinstalling from `requirements.txt` should not introduce a resolver fight if your repo was already clean on 1.7.x.

| Area | 1.8.0 posture |
|---|---|
| Foundry deps | `azure-ai-projects>=2.1.0,<3.0`; `azure-ai-inference>=1.0.0b9,<1.0.0b10` |
| HTTP / telemetry deps | `aiohttp>=3.9.0`; `opentelemetry-api>=1.39.0`; `opentelemetry-sdk>=1.30.0` |
| Instrumentation | Still default ON since 1.6.0 (PR #5865); no 1.8.0 change |
| DevUI defaults | Still `host=127.0.0.1`, `auth_enabled=True`, no CORS allow-list |

> [!TIP]
> Treat 1.8.0 as an API-expansion release for this template: upgrade pins, reinstall, compile, then only adopt the new APIs you actually need.

---

## New opt-in APIs

These surfaces shipped in 1.8.0 but are not auto-wired into the existing templates or prompts. Every import below was smoke-verified against the installed 1.8.0 environment.

### 1. Adaptive Evals consumer surface (PR #6101)

Use this when you already have a rubric evaluator authored in Foundry and want to run it through the Agent Framework eval pipeline. The runnable scaffold is [`../../templates/adaptive-evals/`](../../templates/adaptive-evals/); the API reference is [`../api-reference/1.8.0/evaluation.md`](../api-reference/1.8.0/evaluation.md) and the warning model is [`feature-stages.md`](../api-reference/1.8.0/feature-stages.md#adaptive-evals-and-mcpskillssource-new-in-180).

```python
from agent_framework_foundry import GeneratedEvaluatorRef, FoundryEvals
from agent_framework._evaluation import EvalResults

ref = GeneratedEvaluatorRef.latest(name="support-quality")
evals = FoundryEvals(evaluators=[ref, FoundryEvals.RELEVANCE])
EvalResults.assert_no_failed_items(results)
```

> [!IMPORTANT]
> 1.8.0 is **consumer-only** for Adaptive Evals. `FoundryEvals.generate_rubric(...)`, `load_evaluators_from_yaml(...)`, `RubricDimension`, `EvalGenerationSource`, and `BaseAgent.as_eval_source(...)` did **not** ship; author rubrics out-of-band in the Foundry portal.

### 2. `MCPSkillsSource` (PR #6169)

Load Foundry or external skill catalogues over MCP by wrapping an MCP `ClientSession`. Smoke import: `from agent_framework import MCPSkillsSource`.

### 3. Progressive tool exposure (PR #6233)

Use `FunctionInvocationContext.add_tools(...)` and `remove_tools(...)` when a tool should expose a narrower follow-up toolset only after it has validated state or user intent. Smoke import: `from agent_framework import FunctionInvocationContext`.

### 4. Agent file access abstractions (PR #6099)

Use `AgentFileStore` / `FileAccessProvider` when an agent reads or writes user files and you need a swappable storage and access-control seam. Smoke import: `from agent_framework import AgentFileStore, FileAccessProvider`.

### 5. Background task-lifecycle extension (PR #6155)

1.8.0 extends the 1.7.0 `BackgroundAgentsProvider` surface with task/session/response lifecycle types. Smoke import: `from agent_framework import BackgroundAgentsProvider, BackgroundTaskInfo, BackgroundTaskStatus, AgentSession, AgentResponse, create_harness_agent`.

> [!WARNING]
> Do not invent a separate harness class import for 1.8.0. The public entry point remains `create_harness_agent(...)`; PR #6155 added lifecycle types around background work.

---

## Upstream BREAKING changes not used by this template

| PR | Break | Template impact |
|---|-------|-----------------|
| [#6286](https://github.com/microsoft/agent-framework/pull/6286) | `github-copilot-sdk@1.0.0` API stabilization | None — this template does not import `github_copilot_sdk` |
| Skills experimental refactor | Low-level `MCPSkill` / `MCPSkillResource` / `SkillResource` callers should re-verify code | None — this template uses the documented public Skills surface |

If your derived repo directly used either upstream surface, test that code before treating the upgrade as drop-in.

---

## Transparent quality fixes (no code change required)

| PR | Fix | Action |
|---|-----|--------|
| [#6263](https://github.com/microsoft/agent-framework/pull/6263) | `FoundryAgent` accepts optional `timeout=`; defaults preserve behavior | None |
| [#5773](https://github.com/microsoft/agent-framework/pull/5773) | Sync `def` tools dispatch through `asyncio.to_thread` instead of blocking the event loop | None |
| [#6210](https://github.com/microsoft/agent-framework/pull/6210) | Hosted MCP call/result no longer drop on stripped reasoning | None |
| [#6249](https://github.com/microsoft/agent-framework/pull/6249) | Hosted-agent toolbox consent flow fixed | None |
| [#6299](https://github.com/microsoft/agent-framework/pull/6299) | Compaction summary `message_id` collisions fixed | None |
| [#6026](https://github.com/microsoft/agent-framework/pull/6026) | Observability dataclass span-attribute serialization made safe | None |

---

## Validation checklist after upgrade

```bash
python -m pip install -r requirements.txt
python -m compileall -q .
python -W ignore -c "from agent_framework_foundry import GeneratedEvaluatorRef, FoundryEvals; from agent_framework._evaluation import EvalResults"
python -W ignore -c "from agent_framework import MCPSkillsSource, FunctionInvocationContext, AgentFileStore, FileAccessProvider"
python -W ignore -c "from agent_framework import BackgroundAgentsProvider, BackgroundTaskInfo, BackgroundTaskStatus, AgentSession, AgentResponse, create_harness_agent"
```

Then run your existing tests. If applicable, also spot-check one streaming run, one workflow run, and one eval run that exercises the new evaluator surface.

---

## See also

- [`cumulative-since-1.0.md`](cumulative-since-1.0.md) — full release-delta ledger for this KB
- [`from-1.6-to-1.7.md`](from-1.6-to-1.7.md) — previous migration step
- [`../api-reference/1.8.0/evaluation.md`](../api-reference/1.8.0/evaluation.md) — Adaptive Evals consumer surface and citations
- [`../api-reference/1.8.0/feature-stages.md`](../api-reference/1.8.0/feature-stages.md) — experimental warning model for EVALS and SKILLS
- [`../../templates/adaptive-evals/`](../../templates/adaptive-evals/) — runnable Adaptive Evals scaffold
- [Microsoft Agent Framework `python-1.8.0` release](https://github.com/microsoft/agent-framework/releases/tag/python-1.8.0)
