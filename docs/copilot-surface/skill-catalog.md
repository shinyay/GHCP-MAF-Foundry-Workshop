# Skill Catalog — 3 Composite Skills

> [!NOTE]
> Skills are **composite** Copilot capabilities: they auto-activate based on user intent
> (matched against trigger phrases + activation fixtures) and orchestrate multiple prompts
> + chatmodes into a single ordered plan.

## All skills at a glance

| Skill | Purpose | Composes | Hand-off target |
|---|---|---|---|
| `af-knowledge` | KB navigation: find patterns / anti-patterns / API ref / migration guides | (none — pure lookup) | Originating chatmode |
| `foundry-bootstrap` | Zero-to-deployed Foundry agent: provision → deploy | `provision-foundry` + `deploy-agent-to-foundry` + `foundry-ops` | `af-implementer` or originator |
| `review-report-format` | Reusable severity-graded review report skeleton | (consumed BY `review-pre-merge`) | Originating chatmode |

## `af-knowledge`

**Purpose**: Navigate the 82-entry KB efficiently — find canonical patterns, anti-patterns, API reference pages, and migration guides without manual file listing.

**Trigger phrases** (activates skill):
- "Look up the canonical agent creation pattern"
- "Find anti-pattern for empty env vars in Codespaces"
- "Where's the 1.8.0 API reference for tools?"
- "Show me the migration guide for 1.6 → 1.7"

**Composite workflow**:
1. Parse user request to identify KB category (pattern / anti-pattern / API ref / migration)
2. Glob the appropriate `kb-1.8.0/<category>/*.md` directory
3. Match by filename keyword OR file body grep
4. Return one or more cited KB entries with location

**Hand-off**: Returns the resolved KB content + path to the originating chatmode. Does not
itself perform code changes.

**Why composite**: Avoids the user having to know which `kb-1.8.0/` subdirectory contains what.
Single intent → KB-aware lookup.

---

## `foundry-bootstrap`

**Purpose**: Build a complete **zero-to-deployed** plan: provision a Foundry project,
deploy a hosted agent, verify, and hand off.

**Trigger phrases** (activates skill):
- "Bootstrap Foundry from scratch"
- "Provision Foundry plus deploy end-to-end"
- "Zero-to-deployed Foundry hosted-agent"
- "Roll out hosted Foundry agent with azd ai agent extension" (added in F3)
- "Bootstrap Foundry container-based hosted agent with ACR" (added in F3)
- "End-to-end provision Foundry plus deploy hosted agent in northcentralus" (added in F3)

**Composite workflow** (5 steps):
1. Classify request as bootstrap only if both provisioning + deployment needed
2. Route provisioning half through `provision-foundry.prompt.md`
3. Route deployment half through `deploy-agent-to-foundry.prompt.md` + reference `templates/hosted-agent-deployment/`
4. Invoke `foundry-ops` for command-emission triage
5. Deliver one ordered plan with phases: inputs, provision, deploy, verify, hand-off

**Hosted-agent prerequisites** (surfaced automatically since F3):
- Region constraint: `northcentralus`-only
- Extension required: `azd extension install azure.ai.agents`
- Container build: Dockerfile + requirements.txt with `agent-framework-foundry-hosting`
- Required env vars: `AZURE_TENANT_ID`, `ENABLE_HOSTED_AGENTS=true`, `AZURE_PRINCIPAL_ID`, `AZURE_PRINCIPAL_TYPE`
- Working reference: `templates/hosted-agent-deployment/`

**Composite-safety inheritance**: Inherits `foundry-ops` **generate-only, never execute** boundary as a non-negotiable R-PHASE3-RISK-1 control.

**Hand-off**: Returns the completed bootstrap plan to `af-implementer` when code changes are expected next, or to the originating chatmode if invoked from one.

**Activation fixtures**: `tests/skill-activation-fixtures/foundry-bootstrap.jsonl` (15 entries: 6 should_trigger + 3 ACR-aware added in F3 + 6 should_not_trigger).

---

## `review-report-format`

**Purpose**: Packages the severity-grouped, confidence-tagged review report skeleton emitted by `review-pre-merge.prompt.md`.

**Activation**: Implicit — consumed by `review-pre-merge` rather than user-invoked. Provides:
- Severity ordering: BLOCKER → IMPORTANT → NIT → INFO
- Confidence tags: HIGH / MEDIUM / LOW
- Citation format: file path + line range + KB reference
- Hand-off payload format

**Why a skill (not a prompt fragment)**: Reusable across `review-pre-merge`, `scan-anti-patterns`, and future review prompts. Keeps format consistency without copy-paste.

**Hand-off**: N/A (utility skill).

---

## When skills auto-activate vs are explicit

| Mode | How it works | Example |
|---|---|---|
| **Auto-activation** (skill heuristic match) | User says trigger phrase → Copilot detects + activates skill | "Bootstrap Foundry" → `foundry-bootstrap` auto-activates |
| **Explicit invocation** | User says "use the foundry-bootstrap skill" or `/skill foundry-bootstrap` | (rare; usually auto wins) |
| **Implicit consumption** | Prompt calls a utility skill | `review-pre-merge` consumes `review-report-format` |

## Activation fixture maintenance

To **add a new trigger phrase** to a skill:

1. Edit `tests/skill-activation-fixtures/<skill-name>.jsonl`
2. Add: `{"trigger_class":"should_trigger","input":"<new phrase>","skill":"<skill-name>"}`
3. Run `python3 -m pytest tests/test_skill_activation.py -v` — must PASS
4. Document the new phrase in this catalog

Example (from F3 PR #5): added 3 ACR-aware triggers for `foundry-bootstrap`.

## See also

- [`./prompt-catalog.md`](./prompt-catalog.md) — 17 prompts that skills compose
- [`./agent-catalog.md`](./agent-catalog.md) — chatmodes that skills delegate to
- [`./architecture-overview.md`](./architecture-overview.md) — system view
- `(in source repo only) .github/skills/*/SKILL.md` — source-of-truth skill definitions
- `tests/skill-activation-fixtures/` — activation heuristic test fixtures
