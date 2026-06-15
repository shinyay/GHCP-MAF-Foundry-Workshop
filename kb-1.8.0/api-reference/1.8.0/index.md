# API Reference — Agent Framework 1.8.0

> Status: **Stable** (1.8.0 GA, 2026-05-28)
> Pinned in this template: `agent-framework-foundry==1.8.0`
> Verified against: runtime introspection of the pinned wheel + canonical patterns in the parent demo repo (`getting-started-with-agent-framework`)

This is the **navigation hub** for the Agent Framework 1.8.0 surface as it is actually shipped on PyPI (not what the docs aspirationally describe). Every page below is grounded in:

1. `inspect` / `help()` output against the installed `agent-framework-foundry==1.8.0` wheel.
2. The 8 working demos in the parent `getting-started-with-agent-framework` repo (canonical when docs disagree).
3. Microsoft Learn / upstream release notes (narrative + change tracking only).

If you are an LLM reading this: **read the page that matches your symbol first**, then cross-reference `kb/patterns/` for an end-to-end working example.

---

## Reading order for newcomers

1. **`packages.md`** — which PyPI package to install and which to NEVER install.
2. **`clients.md`** — `FoundryChatClient` (the entry point for everything else).
3. **`agents.md`** — `client.as_agent(...)` and the `Agent` runtime.
4. **`tools-function.md`** — Python function tools (typing + descriptions).
5. Pick one of `tools-hosted.md` / `tools-mcp.md` based on the tool kind you need.
6. **`exceptions.md`** — what to catch and how to surface fail-fast messages.

For multi-agent / workflow scenarios, jump to `workflows.md` after step 3.

---

## Page index

| Page | What it covers |
|------|----------------|
| [`packages.md`](packages.md) | PyPI packages, optional installs, the meta-package trap |
| [`clients.md`](clients.md) | `FoundryChatClient` constructor + lifecycle + 15 `get_*_tool()` factories |
| [`agents.md`](agents.md) | `Agent` / `FoundryAgent` / `client.as_agent()` / `run()` / streaming |
| [`tools-function.md`](tools-function.md) | `@tool` / plain Python callable / `Annotated` arg descriptions |
| [`tools-hosted.md`](tools-hosted.md) | Bing grounding, Code Interpreter, File Search, Image Generation |
| [`tools-mcp.md`](tools-mcp.md) | `MCPStdioTool` / `MCPStreamableHTTPTool` / `MCPWebsocketTool` |
| [`tools-shell.md`](tools-shell.md) | **NEW 1.6.0** — Shell tool (local + Docker) |
| [`workflows.md`](workflows.md) | `WorkflowBuilder` / `WorkflowEvent` discriminator / edges & handoff |
| [`structured-output.md`](structured-output.md) | Pydantic `BaseModel` → `response_format=` |
| [`observability.md`](observability.md) | OTel providers, 1.6.0 instrumentation-default-ON change |
| [`devui.md`](devui.md) | `serve()` 1.4+ defaults, workshop vs production usage |
| [`exceptions.md`](exceptions.md) | `AgentFrameworkException` hierarchy + removed exceptions |

---

## 1.8.0 highlights (what changed since 1.6.0)

| Area | Change | See |
|------|--------|-----|
| Declarative actions | `AppendValue`/`EmitEvent`/`Confirmation`/`WaitForInput` **removed**; `Switch`/`Goto` renamed to `ConditionGroup`/`GotoAction` (PR #6126). | [`declarative.md`](declarative.md), [`../../migration-guides/from-1.6-to-1.7.md`](../../migration-guides/from-1.6-to-1.7.md#1-declarative-actions-removed-and-renamed-pr-6126--breaking) |
| Provider tool names | `TodoProvider` tool names renamed (`add_todos` → `todos_add`, etc., PR #6107); `AgentModeProvider` tool names renamed (`set_mode` → `mode_set`, `get_mode` → `mode_get`, PR #6071). Silent breaker for hosted-tool allow-lists / eval rubrics / .NET interop. | [`../../migration-guides/from-1.6-to-1.7.md`](../../migration-guides/from-1.6-to-1.7.md#2-todoprovider-tool-names-renamed-pr-6107--silent-breaker) |
| Harness agents | NEW `create_harness_agent` + `DEFAULT_HARNESS_INSTRUCTIONS` (PR #6041, `@experimental`). | [`../../patterns/harness-agent.md`](../../patterns/harness-agent.md) |
| Background agents | NEW `BackgroundAgentsProvider` + `BackgroundTaskInfo` + `BackgroundTaskStatus` (PR #6069, `@experimental`). | [`../../patterns/background-agents.md`](../../patterns/background-agents.md) |
| Foundry prompt-agent | NEW `to_prompt_agent(agent)` for Foundry prompt-agent publication (PR #5959, `@experimental`). | [`../../patterns/foundry-prompt-agent.md`](../../patterns/foundry-prompt-agent.md) |
| Compaction | NEW `ContextWindowCompactionStrategy` — token-budget-aware compaction (PR #6041). | [`compaction.md`](compaction.md#contextwindowcompactionstrategy) |

For the full **migration delta** from 1.6 → 1.7 (including PR-level citations + before/after diffs), see [`../../migration-guides/from-1.6-to-1.7.md`](../../migration-guides/from-1.6-to-1.7.md).

---

## 1.6.0 highlights (what changed since 1.5.0)

| Area | Change | See |
|------|--------|-----|
| Observability | **Instrumentation default ON** (PR #5865). Opt out with `disable_instrumentation()` if you don't want telemetry. | [`observability.md`](observability.md), [`../../anti-patterns/instrumentation-implicit-on-1.6.md`](../../anti-patterns/instrumentation-implicit-on-1.6.md) |
| OTel dep | `opentelemetry-sdk` is **no longer a hard dependency** — install it yourself if you need the SDK (exporters, providers). | [`observability.md`](observability.md) |
| Shell tool | New **Shell tool** for local + Docker exec (PR #5664). `Status: Experimental`. | [`tools-shell.md`](tools-shell.md) |
| Hosted factories | Several Foundry hosted factories went from preview → callable (`get_browser_automation_tool`, `get_computer_use_tool`, `get_memory_search_tool`, `get_sharepoint_tool`, `get_fabric_tool`, `get_a2a_tool`). `Status: Experimental` for all. | [`tools-hosted.md`](tools-hosted.md) |
| MCP | `MCPWebsocketTool` added alongside `MCPStdioTool` / `MCPStreamableHTTPTool`. | [`tools-mcp.md`](tools-mcp.md) |
| DevUI | `serve()` got new params: `mode='developer'\|'user'`, `instrumentation_enabled`, `auth_token`. Existing 1.4 defaults (`host='127.0.0.1'`, `auth_enabled=True`) unchanged. | [`devui.md`](devui.md) |

For the full **migration delta** from 1.5 → 1.6, see [`../../migration-guides/from-1.5-to-1.6.md`](../../migration-guides/from-1.5-to-1.6.md).
For the **cumulative breaking-change log since 1.0 GA**, see [`../../migration-guides/cumulative-since-1.0.md`](../../migration-guides/cumulative-since-1.0.md).

---

## Conventions used by every page

Every API reference page below follows the same shape:

```
# <Symbol>
> Status: Stable | Experimental | Preview
> Pinned: agent-framework-foundry==1.8.0
> Verified against: <introspection> + <parent demo / template>

## Signature        ← actual installed signature, copied verbatim
## Constructor / parameters
## Lifecycle        ← async with? cleanup obligations?
## Example          ← minimum working example
## Common mistakes  ← links to kb/anti-patterns/*.md
## See also
```

If you see `Status: Experimental`, the API is shipped but **not validated by the parent demo repo**. Treat it as best-effort and watch for signature drift across minor versions.

---

## Source-of-truth ordering (when sources disagree)

1. Introspection of the installed wheel (`inspect.signature`, `help()`).
2. Parent repo demo (verified working code).
3. Upstream `microsoft/agent-framework` release notes / PRs.
4. Microsoft Learn (narrative only — code examples there frequently lag the pinned version).

When a page asserts a signature, the source is always **#1**. When a page asserts a usage pattern, the source is always **#2** unless the pattern is brand new in 1.6.0 (then #3, marked `Status: Experimental`).
