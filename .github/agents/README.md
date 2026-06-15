# Custom chatmodes (`.github/agents/`)

This directory holds the **custom Copilot chatmodes** for the `ms-agent-framework-template-v1.8.0` template repository. Each chatmode is a single Markdown file with YAML frontmatter that Copilot activates when the developer selects it. All chatmodes share the contract documented in this README so they can hand off work to each other cleanly.

> If you only want to *use* a chatmode, pick one from the **Family** table below and start a conversation with it selected.
> If you want to *add or modify* a chatmode, read **Frontmatter schema** + **Agent body template** + **Verification** before editing.

## Family

| File | Role | Phase added |
|---|---|---|
| `af-implementer.agent.md` | Writes Python code on Agent Framework 1.8.0 — minimum-diff, KB-aware, version-pinned | ✅ PR-J |
| `af-architect.agent.md` | Pre-implementation design advisor — picks patterns + flags anti-patterns + outputs a design doc | ✅ PR-K |

> [!NOTE]
> In the source template repo this family included two additional chatmodes (`af-reviewer` for anti-pattern walks and `foundry-ops` for environment triage). They were removed from this workshop fork because Lab 2 — the only Lab actively maintained here — does not exercise post-implementation review or Foundry environment provisioning. See `kb-1.8.0/anti-patterns/` for manually-walkable anti-patterns instead.

## Frontmatter schema

Every chatmode file must begin with YAML frontmatter delimited by `---`. Four keys are required:

| Key | Type | Allowed values | Notes |
|---|---|---|---|
| `name` | string | `[a-z][a-z0-9-]*` | Used as the chatmode ID Copilot displays |
| `description` | string | free text, single line | Shown in the chatmode picker; describe the persona + scope |
| `tools` | list of strings | subset of `["read", "search", "edit", "execute"]` | Capabilities the chatmode is allowed to use |
| `infer` | boolean | `true` or `false` | When `true`, Copilot may infer additional context from the workspace |

Canonical example:

```yaml
---
name: af-implementer
description: A development agent that implements Python agents on Microsoft Agent Framework 1.8.0. Reads pattern docs first, makes minimal-diff changes, never invents APIs, and runs verification (at minimum compileall).
tools: ["read", "search", "edit", "execute"]
infer: true
---
```

> Frontmatter is parsed by the verification scripts in `scripts/` using stdlib only (no PyYAML dependency). Multi-line YAML values are **not** supported by the current parser — keep each value on one line.

## Agent body template

Every chatmode body **must include all of these sections**. The **relative order of the core sections** below is the contract; persona-specific operational sections (e.g., `af-implementer`'s `## Pass-2 KB Awareness`, `## Phase F Awareness`, `## Implementation Conventions`) MAY be inserted between core sections as long as the core-section relative order is preserved.

Core sections (relative order is enforced):

1. **Opening persona paragraph** — one short paragraph stating who the chatmode is and what problem space it owns.
2. **`## Objectives (In Priority Order)`** *(or `## Objectives In Priority Order`)* — numbered list, 3-5 bullets, prioritized.
3. **`## Accuracy and Version Awareness`** (or chatmode-specific `## Required Reading`) — lists the relevant KB paths under `kb-1.8.0/` and the pin in `requirements.txt` that the chatmode must consult before acting.
4. **`## Workflow`** — numbered, enforceable steps the chatmode follows for every request.
5. **`## Output Format`** *(REQUIRED for non-implementer chatmodes; OPTIONAL for `af-implementer` since its output is a diff)* — exact structure of the chatmode's deliverable (e.g., review report, design doc, triage table).
6. **`## Quality Standards`** — repeatable quality bar the chatmode upholds.
7. **`## Restrictions`** — what the chatmode must *not* do (including removed APIs — see implementer's section for the canonical list).
8. **`## Hand-off`** — which other chatmode picks up after this one, and how the output is consumed.
9. **`## Companion Prompts (Phase 3 hooks)`** — bulleted list of `(planned)` prompt filenames that will wrap this chatmode's workflow in Phase 3.
10. **`## Related Skills (Phase 3 hooks)`** — bulleted list of `(planned)` skill IDs in agentskills.io directory form (`<skill-id>/SKILL.md`).

**Persona-specific inserts allowed**: the implementer for example inserts `## Pass-2 KB Awareness` (routing index) and `## Phase F Awareness` (known pitfalls) between sections 3 and 4, and `## Implementation Conventions` + `## When the Requested Pattern Is Not in kb-1.8.0/patterns/` between sections 4 and 6. `af-architect` may do the same as long as the 10 core sections all appear in the listed relative order.

**Heading-text tolerance**: minor heading-text variants (e.g., `## Objectives In Priority Order` vs `## Objectives (In Priority Order)`) are acceptable; the contract is by section *purpose*, not exact heading wording. The verification scripts (`scripts/check-agent-frontmatter.py`, `scripts/check-agent-markdown.py`) currently enforce mechanical structure only (frontmatter validity, heading nesting, link resolution); per-section presence checks are deferred to a future tightening.

## Output Format (family-level minimums for non-implementer chatmodes)

The non-implementer chatmode in this workshop (`af-architect`) emits a *structured Markdown deliverable*, not a code diff. Its `## Output Format` body MUST define a stable Markdown skeleton meeting these minimums:

1. **Required top-level headings** (declared once at the top of the chatmode's `## Output Format` body and ALWAYS emitted in that order, even if a section is "N/A").
2. **Explicit hand-off target** — every deliverable ends with a Hand-off section naming `af-implementer` (the only downstream chatmode in this workshop).
3. **KB citation on every recommendation** — pattern selections cite a `kb-1.8.0/patterns/` file; anti-pattern flags cite a `kb-1.8.0/anti-patterns/` file; API claims cite a `kb-1.8.0/api-reference/1.8.0/` file. Backticked relative paths like `kb-1.8.0/patterns/canonical-agent-creation.md` are acceptable (these are NOT validated by `scripts/check-agent-markdown.py` — see Verification below).
4. **Risk / blocker table** — at least one table column dedicated to risks, blockers, or unresolved questions, even if a single row says "None at this stage".
5. **"N/A with rationale" allowed** — irrelevant sections may be filled with "N/A — *one-sentence rationale*"; they MUST NOT be silently omitted, because `af-implementer` relies on stable section presence to parse the deliverable.

The implementer is exempt from this contract because its deliverable is a code diff (validated by Python tooling, not Markdown structure).

## File layout convention

- Naming: `<role>.agent.md` (lowercase, kebab-case)
- Placement: `.github/agents/<file>` (this directory)
- Size: ≤ 200 lines target per file.
- Library content (long pattern explanations, code snippets, anti-pattern catalogues) lives in `kb-1.8.0/` — chatmodes *reference* `kb-1.8.0/`, they don't duplicate it.

## Hand-off vocabulary

```
                ┌─────────────────────────────────┐
                │     af-architect                │
                │  design → patterns → risks      │
                └─────────────┬───────────────────┘
                              │ design doc
                              ▼
                ┌─────────────────────────────────┐
                │   af-implementer                │
                │  KB-aware minimum-diff code     │
                └─────────────────────────────────┘
```

### Hand-off matrix (per chatmode)

| Chatmode | Receives | Emits | Hands off to |
|---|---|---|---|
| `af-architect` | user request / unclear feature[^uf] | design doc + risk register | `af-implementer` |
| `af-implementer` | design doc OR direct task | code diff + change summary | (none — implementer is the workshop terminal) |

[^uf]: "Unclear feature" = a request requiring pattern selection, scope decomposition, risk assessment, or architectural trade-off before implementation. If the request is unambiguous and matches an existing pattern in `kb-1.8.0/patterns/`, the developer should go directly to `af-implementer` instead.

This matrix is the contract for each chatmode's `## Hand-off` body section. `af-architect` MUST keep its `## Hand-off` consistent with this table.

## Phase 3 closeout — chatmode hook reconciliation

Each chatmode reserves two sections (`## Companion Prompts` and `## Related Skills`) listing the prompts and skills that wrap its workflow. Rules:

- Entries listed in these sections MUST resolve to real files under `.github/prompts/` (this workshop has no .github/skills/ — supplementary skills are in `kb-1.8.0/`). The `(planned)` placeholder convention was retired when Phase 3 closeout removed the last forward-looking entries (see [Epic #1](https://github.com/shinyay/ms-agent-framework-template-v1.8.0/issues/1)).
- Filenames listed in `Companion Prompts` are stable contracts; renaming requires a chatmode-doc update in the same PR.
- Skill IDs listed in `Related Skills` use the agentskills.io directory form `<skill-id>/SKILL.md` — not flat `*.skill.md` files.
- If a chatmode genuinely has no companion prompts or related skills (rare), omit the section entirely rather than leaving a stub.

## Verification

Chatmode-file-specific verification (run before opening any PR that touches `.github/agents/`):

```bash
# 1. Frontmatter strict check (stdlib only; validates frontmatter delimiters + required keys + tools list type)
python3 scripts/check-agent-frontmatter.py .github/agents/<file>.agent.md

# 2. Markdown structural check (frontmatter delimiter parity, heading nesting, code-fence parity,
#    AND resolution of explicit Markdown links of the form [label](relative/path.md))
python3 scripts/check-agent-markdown.py .github/agents/<file>.agent.md

# 3. Line-count cap
wc -l .github/agents/*.md   # each should be ≤ 200

# 4. KB-citation resolver (manual — check #2 does NOT validate backticked `kb-1.8.0/...` paths,
#    only Markdown-link-syntax paths. Backticked citations like `kb-1.8.0/patterns/foo.md` slip past
#    check #2. Run this one-liner to catch broken backticked KB references):
grep -hoE 'kb-1.8.0/[a-zA-Z0-9/_.-]+\.md' .github/agents/<file>.agent.md \
  | sort -u \
  | while read p; do [ -f "$p" ] || echo "MISSING: $p"; done
# (no output = all KB citations resolve; any "MISSING: ..." lines must be fixed before PR)
```

For repo-wide code/template verification (Python syntax, e2e runs against Foundry), see `AGENTS.md` and `.github/copilot-instructions.md` — this README does **not** duplicate those policies.

## See also

- [`kb-1.8.0/README.md`](../../kb-1.8.0/README.md) — Agent Framework knowledge base (patterns, anti-patterns, API reference)
- [`AGENTS.md`](../../AGENTS.md) — repository-wide working conventions
- [`.github/copilot-instructions.md`](../copilot-instructions.md) — Copilot-specific accuracy rules and validation policy
