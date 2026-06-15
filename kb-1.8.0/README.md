# Knowledge Base (KB)

This directory is the **Agent Framework knowledge layer** that GitHub Copilot reads when generating code for this template. It is a curated, **version-pinned** reference — not a doc dump.

> **Pin:** `agent-framework-foundry==1.8.0`
> **Source-of-truth ordering:** introspection of the installed package → parent repo verified demos → upstream release notes → Microsoft Learn (narrative only).

## Structure

```
kb/
├── README.md                                  # this file
├── api-reference/
│   └── 1.8.0/                                 # symbol-level API reference (Pass 1)
│       ├── index.md                           # nav + highlights + reading order
│       ├── packages.md                        # install rules + meta-package trap
│       ├── clients.md                         # FoundryChatClient + get_*_tool factories
│       ├── agents.md                          # client.as_agent / Agent / streaming
│       ├── tools-function.md                  # Python function tools
│       ├── tools-hosted.md                    # Bing / FileSearch / CodeInterpreter / ImageGen
│       ├── tools-mcp.md                       # MCPStdio / Streamable HTTP / Websocket
│       ├── tools-shell.md                     # NEW in 1.6 — hosted + LocalShellTool + DockerShellTool (Pass 2 corrected)
│       ├── feature-stages.md                  # Stability tiers + warning recipes (Pass 2)
│       ├── workflows.md                       # WorkflowBuilder + WorkflowEvent
│       ├── workflow-internals.md              # Pregel / EdgeGroup / State / Viz internals (Pass 2)
│       ├── middleware.md                      # Agent/Chat/Function pipelines (Pass 2)
│       ├── sessions.md                        # AgentSession + ContextProvider + HistoryProvider (Pass 2)
│       ├── skills.md                          # ⚠️ EXPERIMENTAL — Skill family + SkillsProvider (Pass 2)
│       ├── history-providers.md               # RedisHistoryProvider + CosmosHistoryProvider (Pass 2)
│       ├── context-providers-rag.md           # Mem0 / Redis / AI Search RAG providers (Pass 2)
│       ├── memory-experimental.md             # ⚠️ EXPERIMENTAL — MemoryStore / MemoryFileStore (Pass 2)
│       ├── structured-output.md               # Pydantic via response_format=
│       ├── observability.md                   # OTel + instrumentation default ON (1.6)
│       ├── devui.md                           # serve() + workshop vs production
│       ├── evaluation.md                      # ⚠️ EXPERIMENTAL — EVALS subsystem (Pass 2)
│       ├── composition-adapters.md            # as_tool / as_mcp_server / as_agent directional matrix (Pass 2)
│       ├── declarative.md                     # ⚠️ BETA — AgentFactory / WorkflowFactory / 28 action kinds (1.8.0: 6 removed) (Pass 2)
│       ├── settings.md                        # load_settings + SecretString (Pass 2)
│       ├── serialization.md                   # SerializationProtocol / SerializationMixin / type ID resolution / DI (Pass 2)
│       ├── compaction.md                      # CompactionProvider + 7 strategies (1.8.0 added ContextWindowCompactionStrategy) + group model (Pass 2)
│       ├── security.md                        # ⚠️ EXPERIMENTAL — FIDES info-flow control + SecureAgentConfig (Pass 2)
│       └── exceptions.md                      # AgentFrameworkException hierarchy
├── patterns/                                  # verified end-to-end recipes
│   ├── canonical-agent-creation.md            # single agent + Python tool
│   ├── hosted-bing-search.md                  # Bing grounding
│   ├── local-mcp-stdio.md                     # npx-based MCP server
│   ├── structured-output-pydantic.md          # response_format=
│   ├── multi-agent-workflow.md                # WorkflowBuilder + edges + streaming
│   ├── devui-local-development.md             # serve() workshop pattern
│   ├── foundry-toolbox-mcp-http.md            # Toolbox via MCPStreamableHTTPTool
│   ├── rag-with-file-search.md                # Hosted file search
│   ├── streaming-output.md                    # CLI / UI streaming
│   ├── observability-otel.md                  # OTLP / console / custom exporter (vendor-agnostic)
│   ├── observability-azure-monitor.md         # App Insights end-to-end + KQL queries (Pass 2)
│   ├── observability-workflow-tracing.md      # interpret workflow/executor/edge spans (Pass 2)
│   ├── error-handling.md                      # AgentFrameworkException + fail-fast
│   ├── workflow-checkpointing.md              # FileCheckpointStorage + Cosmos backend + resume (Pass 2)
│   ├── workflow-as-agent-nesting.md           # workflow.as_agent() composition (Pass 2)
│   ├── agent-middleware-retry.md              # Retry / cache / observe via middleware (Pass 2)
│   ├── session-history-persistence.md         # Custom HistoryProvider backends (Pass 2)
│   ├── persistent-history-cosmos.md           # CosmosHistoryProvider end-to-end (Pass 2)
│   ├── rag-with-azure-ai-search.md            # AzureAISearchContextProvider end-to-end (Pass 2)
│   ├── inline-skill-definition.md             # ⚠️ EXPERIMENTAL — InlineSkill recipe (Pass 2)
│   ├── agent-evaluation-local.md              # ⚠️ EXPERIMENTAL — LocalEvaluator deterministic checks (Pass 2)
│   ├── agent-evaluation-foundry.md            # ⚠️ EXPERIMENTAL — FoundryEvals LLM-as-judge (Pass 2)
│   ├── workflow-evaluation.md                 # ⚠️ EXPERIMENTAL — per-agent breakdown (Pass 2)
│   ├── agent-as-tool-handoff.md               # coordinator + specialist via as_tool() (Pass 2)
│   ├── agent-as-mcp-server.md                 # expose agent over MCP stdio (Pass 2)
│   ├── declarative-agent.md                   # ⚠️ BETA — load PromptAgent from YAML (Pass 2)
│   ├── declarative-workflow.md                # ⚠️ BETA — load Workflow from YAML + HITL (Pass 2)
│   ├── harness-agent.md                       # NEW in 1.8.0 — Harness base class for custom agents
│   ├── background-agents.md                   # NEW in 1.8.0 — long-running agents + token budgets
│   └── foundry-prompt-agent.md                # NEW in 1.8.0 — declarative Foundry prompt agents
├── anti-patterns/                             # "don't do this" with detection + fix
│   ├── meta-package-overwrite.md              # pip install agent-framework breaks imports
│   ├── removed-apis-since-1.0.md              # full table of removed APIs + replacements
│   ├── sync-credential-in-async.md            # azure.identity (sync) vs .aio
│   ├── empty-env-vars-codespaces.md           # Codespaces empty-string trap
│   ├── devui-production-defaults.md           # workshop defaults in production = unsafe
│   ├── missing-async-with-cleanup.md          # leaked connections + subprocess zombies
│   ├── instrumentation-implicit-on-1.6.md     # default-ON surprises since 1.6
│   ├── workflow-event-isinstance.md           # isinstance check on WorkflowEvent
│   ├── middleware-returning-value.md          # return value from process() is dropped (Pass 2)
│   ├── using-the-wrong-memory-primitive.md    # CheckpointStorage vs HistoryProvider vs ContextProvider (Pass 2)
│   ├── eval-as-test-substitute.md             # ⚠️ EXPERIMENTAL — EVALS as CI gate misuse (Pass 2)
│   ├── composition-pitfalls.md                # 13 WRONG/RIGHT pairs across as_tool/as_mcp_server/as_agent (Pass 2)
│   └── declarative-pitfalls.md                # ⚠️ BETA — 8 WRONG/RIGHT pairs (safe_mode / unknown kind / SSRF / PowerFx) (Pass 2)
└── migration-guides/                          # version-to-version upgrade docs
    ├── from-1.6-to-1.7.md                     # latest delta (NEW in 1.8.0)
    ├── from-1.5-to-1.6.md                     # previous delta
    └── cumulative-since-1.0.md                # all changes since 1.0 GA
```

## Reading order

| Question | Start here |
|----------|-----------|
| "How do I build an agent?" | [`patterns/canonical-agent-creation.md`](patterns/canonical-agent-creation.md) |
| "How do I add Bing search / file search / MCP?" | `patterns/hosted-bing-search.md` / `rag-with-file-search.md` / `local-mcp-stdio.md` |
| "How do I compose multiple agents?" | [`patterns/multi-agent-workflow.md`](patterns/multi-agent-workflow.md) |
| "How do I return structured output?" | [`patterns/structured-output-pydantic.md`](patterns/structured-output-pydantic.md) |
| "How do I stream tokens to a CLI?" | [`patterns/streaming-output.md`](patterns/streaming-output.md) |
| "How do I persist conversation history?" | [`patterns/session-history-persistence.md`](patterns/session-history-persistence.md) |
| "How do I persist chat history in production?" | [`api-reference/1.8.0/history-providers.md`](api-reference/1.8.0/history-providers.md) → [`patterns/persistent-history-cosmos.md`](patterns/persistent-history-cosmos.md) |
| "How do I add RAG with Azure AI Search?" | [`patterns/rag-with-azure-ai-search.md`](patterns/rag-with-azure-ai-search.md) |
| "Which is the right memory primitive for my problem?" | [`anti-patterns/using-the-wrong-memory-primitive.md`](anti-patterns/using-the-wrong-memory-primitive.md) → [`api-reference/1.8.0/packages.md`](api-reference/1.8.0/packages.md#persistence--memory-packages--capability-matrix) |
| "How do I add retry/cache/logging around an agent?" | [`patterns/agent-middleware-retry.md`](patterns/agent-middleware-retry.md) |
| "How do I package a domain capability as a skill?" | [`patterns/inline-skill-definition.md`](patterns/inline-skill-definition.md) ⚠️ experimental |
| "How do middleware / sessions / skills relate?" | [`api-reference/1.8.0/middleware.md`](api-reference/1.8.0/middleware.md) → [`sessions.md`](api-reference/1.8.0/sessions.md) → [`skills.md`](api-reference/1.8.0/skills.md) |
| "How do I evaluate an agent / catch quality regressions?" | [`api-reference/1.8.0/evaluation.md`](api-reference/1.8.0/evaluation.md) → [`patterns/agent-evaluation-local.md`](patterns/agent-evaluation-local.md) → [`patterns/agent-evaluation-foundry.md`](patterns/agent-evaluation-foundry.md) |
| "How do I score per-sub-agent in a workflow?" | [`patterns/workflow-evaluation.md`](patterns/workflow-evaluation.md) |
| "Why are my eval scores flaky in CI?" | [`anti-patterns/eval-as-test-substitute.md`](anti-patterns/eval-as-test-substitute.md) |
| "How do I let one agent delegate to specialists (LLM-decided)?" | [`api-reference/1.8.0/composition-adapters.md`](api-reference/1.8.0/composition-adapters.md) → [`patterns/agent-as-tool-handoff.md`](patterns/agent-as-tool-handoff.md) |
| "How do I expose my agent to Claude Desktop / VS Code MCP?" | [`patterns/agent-as-mcp-server.md`](patterns/agent-as-mcp-server.md) |
| "When should I use `as_tool` vs `WorkflowBuilder`?" | [`api-reference/1.8.0/composition-adapters.md#decision-guide-which-adapter-for-which-problem`](api-reference/1.8.0/composition-adapters.md#decision-guide-which-adapter-for-which-problem) |
| "Why is `Workflow.as_agent()` raising `cannot handle list[Message]`?" | [`anti-patterns/composition-pitfalls.md#8-workflowas_agent-on-a-workflow-whose-start-executor-cannot-handle-listmessage`](anti-patterns/composition-pitfalls.md) |
| "How do I load an agent/workflow from YAML?" | [`api-reference/1.8.0/declarative.md`](api-reference/1.8.0/declarative.md) ⚠️ beta → [`patterns/declarative-agent.md`](patterns/declarative-agent.md) / [`patterns/declarative-workflow.md`](patterns/declarative-workflow.md) |
| "Why is my `=Env.X` empty in YAML?" | [`anti-patterns/declarative-pitfalls.md#4-using-env-without-disabling-safe_mode`](anti-patterns/declarative-pitfalls.md) |
| "How do I add HITL pauses to a workflow?" | [`patterns/declarative-workflow.md#human-in-the-loop-hitl`](patterns/declarative-workflow.md) ⚠️ beta |
| "I'm upgrading from 1.6 to 1.7" | [`migration-guides/from-1.6-to-1.7.md`](migration-guides/from-1.6-to-1.7.md) |
| "I'm upgrading from 1.5 to 1.6" | [`migration-guides/from-1.5-to-1.6.md`](migration-guides/from-1.5-to-1.6.md) |
| "I see a `ModuleNotFoundError` for `agent_framework.foundry`" | [`anti-patterns/meta-package-overwrite.md`](anti-patterns/meta-package-overwrite.md) |
| "I see `Unclosed connector` / `ResourceWarning`" | [`anti-patterns/missing-async-with-cleanup.md`](anti-patterns/missing-async-with-cleanup.md) |
| "What's the full hierarchy of an exception X?" | [`api-reference/1.8.0/exceptions.md`](api-reference/1.8.0/exceptions.md) |
| "What does `client.get_*_tool()` return / accept?" | [`api-reference/1.8.0/clients.md`](api-reference/1.8.0/clients.md) |
| "Why am I seeing `FutureWarning` from agent_framework?" | [`api-reference/1.8.0/feature-stages.md`](api-reference/1.8.0/feature-stages.md) |
| "Is the Shell tool ready for production?" | [`api-reference/1.8.0/tools-shell.md`](api-reference/1.8.0/tools-shell.md) — three options (hosted / local / Docker), `agent-framework-tools` is **alpha** |
| "Which Foundry factories are experimental vs stable?" | [`api-reference/1.8.0/tools-hosted.md#foundry-factory-stability-map-160`](api-reference/1.8.0/tools-hosted.md) |
| "How do I load API keys/endpoints from `.env`?" | [`api-reference/1.8.0/settings.md`](api-reference/1.8.0/settings.md) (`load_settings` + `SecretString`) |
| "How do I keep an API key out of logs / repr?" | [`api-reference/1.8.0/settings.md#secretstring`](api-reference/1.8.0/settings.md) |
| "How do I serialize an Agent / Workflow / custom executor?" | [`api-reference/1.8.0/serialization.md`](api-reference/1.8.0/serialization.md) (`SerializationProtocol` / `SerializationMixin` / 4-tier type ID resolution) |
| "How do I bound long chat histories?" | [`api-reference/1.8.0/compaction.md`](api-reference/1.8.0/compaction.md) (7 strategies + `CompactionProvider`) |
| "How do I summarize old turns into a system note?" | [`api-reference/1.8.0/compaction.md#summarizationstrategy`](api-reference/1.8.0/compaction.md) |
| "How do I defend an agent against prompt injection?" | [`api-reference/1.8.0/security.md`](api-reference/1.8.0/security.md) ⚠️ experimental — `SecureAgentConfig` drop-in + `quarantined_llm` / `inspect_variable` |
| "How do I tag external API responses as untrusted?" | [`api-reference/1.8.0/security.md#storage-helpers`](api-reference/1.8.0/security.md) |

## Conventions

- **Version-pinned.** Every page states `agent-framework-foundry==1.8.0` and the verification source (introspection / parent demo / upstream PR).
- **Status tags.** Each pattern and reference page is tagged `Status: Stable` or `Status: Experimental`. Experimental APIs may change in minor releases — pin tightly.
- **Source-of-truth ordering.** When sources disagree, **introspection wins**, then **parent repo verified demos**, then **upstream release notes**, then **Microsoft Learn**. Each page notes which it relied on.
- **Working over comprehensive.** Short, runnable examples are more valuable than option dumps.
- **Cite primary sources.** Reference Microsoft Learn URLs and `microsoft/agent-framework` PRs (e.g., `PR #5865`) where relevant.

## How to add a new pattern

1. Write a runnable script (under `templates/`) and verify it against the pinned version.
2. Add a `.md` to `kb/patterns/` following the format used by `canonical-agent-creation.md`:
   - Status / Pinned / Verified-against banner
   - Goal / When to use / Code / Why each piece / Common mistakes / Verification / See also
3. Cross-link to relevant `api-reference/` pages.
4. Update this README's structure tree.
5. If the pattern introduces a new constraint or banned API, add it to `kb/anti-patterns/` too.

## When this KB goes stale

Microsoft Agent Framework releases frequently — historically with BREAKING changes per minor version. When a new stable release ships:

1. Do **not** edit this KB in place.
2. Clone this template into a new repo `ms-agent-framework-template-v<NEW>.0`.
3. Run the cumulative validation script from [`migration-guides/cumulative-since-1.0.md`](migration-guides/cumulative-since-1.0.md).
4. Update the pin, re-verify every pattern, update API ref pages.
5. Tag the old repo with the final version it supports.

This keeps each version's knowledge **frozen and audit-able** — no version drift.

## Pass-1 vs Pass-2 KB

This KB started as **Pass 1** (package introspection + parent repo demos + release notes) and is being incrementally enriched by **Pass 2** (source-code-driven, each non-trivial claim cited at `<file>:<line>` against [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0)).

Pass-2 PRs (subsystem-by-subsystem, in dependency order):

| PR | Subsystem | Status |
|----|-----------|--------|
| A | `workflows-deep` (`workflows.md` rewrite, `workflow-internals.md`, `workflow-checkpointing.md`, `workflow-as-agent-nesting.md`, anti-pattern fix) | ✅ merged |
| B | `middleware-sessions-skills` (3 new ref pages + 3 patterns + 1 anti-pattern + `agents.md` corrections) | ✅ merged |
| C | `memory-stores` (3 new ref pages + 2 patterns + 1 anti-pattern + `packages.md` Pass-1 corrections + Cosmos backend added to `workflow-checkpointing.md`) | ✅ merged |
| D | `evaluation` (`evaluate_agent` / `evaluate_workflow` / `FoundryEvals` — `evaluation.md`, 3 patterns, 1 anti-pattern, agents/workflows cross-links) | ✅ merged |
| E | `composition-adapters` (`as_tool`, `as_mcp_server`, `Workflow.as_agent`, `_maybe_wrap_agent` — `composition-adapters.md`, 2 patterns, 1 anti-pattern, 5 cross-link updates) | ✅ merged |
| F | `declarative-yaml` (`AgentFactory` / `WorkflowFactory` / 34 action kinds — `declarative.md`, 2 patterns, 1 anti-pattern, 6 cross-link updates) ⚠️ beta package | ✅ merged |
| G | `observability-deep` (`observability.md` rewrite, `observability-azure-monitor.md`, `observability-workflow-tracing.md`, `clients.md`/`observability-otel.md`/`instrumentation-implicit-on-1.6.md`/`from-1.5-to-1.6.md` fabrication fixes) | ✅ merged |
| H | `experimental-tools` (new `feature-stages.md` central stability page, `tools-shell.md` rewrite, `tools-hosted.md` stability tier corrections) | ✅ merged |
| I | `packages-config-cross-cutting` (`security.py`, `_serialization.py`, `_compaction.py`, `_settings.py`) | ✅ merged |

The backlog lives at `/.copilot/session-state/<session>/files/kb-pass2-todo.md` (not committed).
