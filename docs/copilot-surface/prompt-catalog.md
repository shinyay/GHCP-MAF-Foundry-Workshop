# Prompt Catalog — 17 Copilot Prompts

> [!NOTE]
> All 17 `.github/prompts/*.prompt.md` files in this template, organized by category and tier.
> Each prompt is a **single-task** unit: it does one specific thing, hands off to a named
> chatmode, and cites relevant KB entries.

## Tier reference

- **Tier A** = read-only / analysis / advisory. Safe to invoke without confirmation.
- **Tier B** = mutating / destructive / security-sensitive. Requires explicit confirmation gates.

## All prompts at a glance

| Prompt | Tier | Category | Companion | Hand-off |
|---|:---:|---|---|---|
| `add-agent` | A | Adder | af-implementer | af-reviewer |
| `add-bing-grounding` | B | Adder (Tool) | af-implementer | af-reviewer |
| `add-foundry-evaluation` | B | Adder (Quality) | af-implementer | af-reviewer |
| `add-foundry-toolbox` | B | Adder (Tool) | af-implementer | af-reviewer |
| `add-hosted-file-search` | B | Adder (Tool) | af-implementer | af-reviewer |
| `add-mcp-tool` | A | Adder (Tool) | af-implementer | af-reviewer |
| `add-tool` | A | Adder (Tool) | af-implementer | af-reviewer |
| `deploy-agent-to-foundry` | B | Foundry-ops | foundry-ops | foundry-ops |
| `migrate-from-1.5` | A | Migrator | af-implementer | af-reviewer |
| `migrate-to-1.8` | A | Migrator | af-reviewer | af-reviewer |
| `provision-foundry` | B | Foundry-ops | foundry-ops | foundry-ops |
| `review-pre-merge` | A | Reviewer | af-reviewer | af-implementer |
| `rotate-credentials` | B | Foundry-ops | foundry-ops | af-implementer |
| `scan-anti-patterns` | A | Reviewer | af-reviewer | af-implementer |
| `triage-foundry-error` | B | Foundry-ops | foundry-ops | af-implementer |
| `upgrade-version` | A | Maintenance | N/A | N/A |
| `verify-template` | A | Maintenance | af-implementer | af-reviewer |

---

## Category: Adders (7 prompts) — extend an existing starter

### `add-agent.prompt.md` (Tier A)
**Purpose**: Add a new agent to a multi-agent workflow.  
**When to invoke**: User says "add a translator agent", "introduce a frontline triage agent".  
**Inputs**: Agent name, instructions, tools list, position in workflow.  
**Output**: Scaffolded `Agent(...)` definition wired into existing `WorkflowBuilder`.

### `add-tool.prompt.md` (Tier A)
**Purpose**: Add a custom Python function tool to an agent.  
**When to invoke**: User says "the agent should be able to fetch stock prices", "add a tool for sending emails".  
**Inputs**: Tool name, what it does, return type, side effects.  
**Output**: Scaffolded function with `typing.Annotated` args + wired to `as_agent(tools=[...])`.

### `add-mcp-tool.prompt.md` (Tier A)
**Purpose**: Add an MCP-based tool (stdio or streamable HTTP).  
**When to invoke**: User says "integrate this CLI", "use the MCP server at <URL>".  
**Inputs**: MCP server URL or command, tool selection criteria.  
**Output**: Scaffolded `MCPStreamableHTTPTool(...)` or `MCPStdioServerTool(...)` wired to agent.

### `add-bing-grounding.prompt.md` (Tier B — adds external dependency)
**Purpose**: Add hosted Bing web-search grounding to an agent.  
**When to invoke**: User says "needs to search the web", "answer with current information".  
**Inputs**: Foundry project endpoint + (existing) Bing connection name.  
**Output**: Scaffolded `client.get_web_search_tool(...)` wired to agent.

### `add-hosted-file-search.prompt.md` (Tier B)
**Purpose**: Add hosted file-search (RAG) to an agent.  
**When to invoke**: User says "agent should query our handbook", "build a knowledge-base bot".  
**Inputs**: Vector store ID(s) + ingestion files.  
**Output**: Scaffolded `client.get_file_search_tool(...)` + ingestion script.

### `add-foundry-toolbox.prompt.md` (Tier B)
**Purpose**: Wire a Foundry Toolbox (centrally-published MCP HTTP tools) to an agent.  
**When to invoke**: User says "use the org's shared tool catalog", "consume Foundry Toolbox".  
**Inputs**: Toolbox name + MCP HTTP endpoint.  
**Output**: Scaffolded `MCPStreamableHTTPTool(name=..., url=...)`.

### `add-foundry-evaluation.prompt.md` (Tier B)
**Purpose**: Add Adaptive Evals quality-gating to a starter.  
**When to invoke**: User says "I need CI quality gates", "evaluate agent responses".  
**Inputs**: Evaluator rubric name + portal-authored dimensions.  
**Output**: Scaffolded `GeneratedEvaluatorRef(...)` + `FoundryEvals(evaluators=[ref])` + assertion helpers.

---

## Category: Migrators (2 prompts) — upgrade AF version

### `migrate-from-1.5.prompt.md` (Tier A)
**Purpose**: Migrate code from AF 1.5.x → 1.8.0 (covers 1.6/1.7 deltas inline).  
**When to invoke**: User has 1.5.x-era code and wants to upgrade.  
**Output**: Diff guide + KB references to deprecation table.

### `migrate-to-1.8.prompt.md` (Tier A)
**Purpose**: Narrow wrapper for 1.6.x → 1.8.0 migrations.  
**When to invoke**: User specifically on 1.6.x or 1.7.x.  
**Inputs**: Existing code paths to scan.  
**Output**: Removed-APIs first-pass + the two silent-breaker tool-name renames in `TodoProvider` / `AgentModeProvider`.

---

## Category: Foundry-ops (4 prompts) — Azure environment operations

### `provision-foundry.prompt.md` (Tier B — destructive)
**Purpose**: Provision a new Foundry project + AI Services account + model deployment.  
**When to invoke**: User says "set up Foundry from scratch", "new env".  
**Output**: Safety-tagged `az cognitiveservices ...` commands as conversational markdown (foundry-ops emits, human executes).

### `deploy-agent-to-foundry.prompt.md` (Tier B — destructive)
**Purpose**: Deploy a hosted agent via `azd ai agent` extension.  
**When to invoke**: User says "publish my agent", "deploy to Foundry runtime".  
**Output**: `azd init` → `azd ai agent init -m <manifest>` → `azd up` sequence with `AZURE_TENANT_ID` callout (Cycle 6 G5 lesson).

### `triage-foundry-error.prompt.md` (Tier B)
**Purpose**: Diagnose a Foundry error stacktrace.  
**When to invoke**: User pastes a `403`, `BCP037`, DNS failure, or other Azure error.  
**Output**: Triage Catalogue lookup → cited KB anti-pattern → suggested fix command.

### `rotate-credentials.prompt.md` (Tier B — destructive-recoverable)
**Purpose**: Rotate a Foundry account key (rare; managed identity preferred).  
**When to invoke**: User says "key rotation needed", "compliance requires key rotation".  
**Safety**: 2-turn confirmation gate; out-of-band Key Vault retrieval (`az keys list` forbidden).

---

## Category: Reviewers (2 prompts) — code/diff analysis

### `review-pre-merge.prompt.md` (Tier A)
**Purpose**: Pre-merge review of a code diff.  
**When to invoke**: Before opening a PR; after applying scoped changes.  
**Output**: Severity-graded findings (BLOCKER/IMPORTANT/NIT/INFO) using `review-report-format` skill.

### `scan-anti-patterns.prompt.md` (Tier A)
**Purpose**: Scan code for known anti-patterns from `kb-1.8.0/anti-patterns/*.md`.  
**When to invoke**: As a gate in `verify-template`, or standalone for an existing diff.  
**Output**: 17-row scan table (one per anti-pattern KB entry) × match status (✅ none / ❌ found at line X).

---

## Category: Maintenance (2 prompts)

### `verify-template.prompt.md` (Tier A — gate prompt)
**Purpose**: Mechanically validate one template directory under `templates/` (compileall + frontmatter + pytest + link integrity).  
**When to invoke**: After any change to a template; before opening a PR; as CI gate.  
**Output**: Per-gate PASS/FAIL/SKIP report (10 gates).  
**Used by**: Plan E P3.5, Plan F3, Plan F4 all ran this gate suite before commit.

### `upgrade-version.prompt.md` (Tier A)
**Purpose**: Upgrade Agent Framework version pin across the repo.  
**When to invoke**: A new AF point release ships.  
**Output**: pin updates in `requirements.txt` + verification steps + migration-guide read recommendation.

---

## Companion chatmode summary

Most prompts pair with `af-implementer` as the companion (the chatmode invoking the prompt)
and hand off to `af-reviewer` (for the post-implementation review). The 4 foundry-ops
prompts pair with `foundry-ops` for both (because Foundry ops never hands off downstream).

| Companion | Count | Examples |
|---|---|---|
| `af-implementer` | 9 | All adders + migrate-from-1.5 + verify-template |
| `af-reviewer` | 3 | migrate-to-1.8 + review-pre-merge + scan-anti-patterns |
| `foundry-ops` | 4 | provision-foundry + deploy-agent + triage-foundry-error + rotate-credentials |
| (none) | 1 | upgrade-version (standalone) |

## See also

- [`./skill-catalog.md`](./skill-catalog.md) — 3 composite skills that combine these prompts
- [`./agent-catalog.md`](./agent-catalog.md) — 4 chatmodes that companion / hand off
- [`./architecture-overview.md`](./architecture-overview.md) — system-level view
- [`./scenarios.md`](./scenarios.md) — which prompt sequence fits which scenario
