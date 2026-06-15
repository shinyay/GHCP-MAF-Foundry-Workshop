# Skills (Agent Skills Specification)

> Status: ⚠️ **EXPERIMENTAL** — the core `Skill*` model classes and the `SkillsSource` ABC are decorated with `@experimental(feature_id=ExperimentalFeature.SKILLS)` ([`_skills.py:L71`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L71) and throughout). Concrete `*SkillsSource` subclasses are not individually decorated but inherit from the decorated ABC (see callout below). Surface may change between minor versions.
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent_framework/_skills.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py)
> Specification: [agentskills.io](https://agentskills.io/specification)

> [!IMPORTANT]
> The core `Skill*` model classes on this page (`SkillResource`, `SkillScript`, `SkillFrontmatter`, `SkillScriptRunner`, and the `SkillsSource` ABC base) are decorated with `@experimental(feature_id=ExperimentalFeature.SKILLS)`. Concrete provider subclasses (`FileSkillsSource`, `InMemorySkillsSource`, `DelegatingSkillsSource`, `DeduplicatingSkillsSource`, `FilteringSkillsSource`, `AggregatingSkillsSource`) inherit from the decorated `SkillsSource` ABC, so `__init_subclass__` fires the warning when their class body executes (i.e. on first import of `_skills.py`); the decorated base also warns on direct instantiation. The `ExperimentalWarning` from `@experimental`-decorated callables fires **on use** (instantiation/subclassing/invocation), not merely on `import agent_framework`. See [`feature-stages.md`](feature-stages.md) for how to silence / track the warning and what changes when an API graduates out of experimental.

Skills implement the **Agent Skills specification** — a portable, progressive-disclosure way for agents to discover and use domain capabilities packaged as `SKILL.md` files (or defined inline in code). A skill bundles:

- **Frontmatter** (name, description, license, compatibility, allowed_tools, metadata)
- **Instructions** (free-form Markdown body of `SKILL.md`)
- **Resources** (supplementary files: `references/`, `assets/`)
- **Scripts** (executable callables: `scripts/`)

## The three progressive-disclosure tiers

1. **Advertise (~100 tokens/skill)** — only frontmatter (name + description) injected into the system prompt.
2. **Load on demand** — full body fetched via the `load_skill` tool when the LLM decides the skill is relevant.
3. **Read resources / run scripts** — `read_skill_resource` and per-skill script tools.

This is implemented by `SkillsProvider` ([`_skills.py:L1642-L1782`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1642-L1782)), which is a `ContextProvider` subclass.

## Type hierarchy

```text
Skill (ABC)                          # _skills.py:L487
├── InlineSkill                      # _skills.py:L717
├── FileSkill                        # _skills.py:L1341
└── ClassSkill (ABC)                 # _skills.py:L1002

SkillResource (ABC)                  # _skills.py:L72
├── InlineSkillResource              # _skills.py:L116
└── _FileSkillResource (private)     # _skills.py:L200

SkillScript (ABC)                    # _skills.py:L256
├── InlineSkillScript                # _skills.py:L310
└── FileSkillScript                  # _skills.py:L401

SkillsSource (ABC)                   # _skills.py:L2333
├── FileSkillsSource                 # _skills.py:L2354
├── InMemorySkillsSource             # _skills.py:L3087
├── DelegatingSkillsSource (ABC)     # _skills.py:L3123
│   ├── DeduplicatingSkillsSource    # _skills.py:L3158
│   └── FilteringSkillsSource        # _skills.py:L3208
└── AggregatingSkillsSource          # _skills.py:L3250

SkillsProvider(ContextProvider)      # _skills.py:L1643
SkillScriptRunner (Protocol)         # _skills.py:L1419
SkillFrontmatter                     # _skills.py:L545
```

## `SkillFrontmatter` — the metadata contract

[`_skills.py:L545-L603`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L545-L603).

```python
from agent_framework import SkillFrontmatter

fm = SkillFrontmatter(
    name="db-skill",                # required — see validation rules below
    description="Database ops.",    # required — ≤1024 chars
    license="MIT",                  # optional
    compatibility="postgres>=14",   # optional — ≤500 chars
    allowed_tools="query schema",   # optional — space-delimited
    metadata={"owner": "data-team"},# optional — shallow-copied
)
```

### Validation rules (enforced at construction)

| Field | Rule | Source |
|-------|------|--------|
| `name` | Lowercase letters/digits/hyphens; ≤64 chars; no leading/trailing/consecutive hyphens. Regex `^[a-z0-9]([a-z0-9]*-[a-z0-9])*[a-z0-9]*$` | [`_skills.py:L606-L623`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L606-L623), [`_skills.py:L1513`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1513) |
| `description` | Non-empty; ≤1024 chars | [`_skills.py:L626-L641`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L626-L641) |
| `compatibility` | If provided, ≤500 chars | [`_skills.py:L644-L654`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L644-L654) |

> [!IMPORTANT]
> Validation runs **only at construction**. Reassigning `fm.name = "..."` afterwards is **not** re-validated — callers are expected to honor the spec.

## Three ways to define a skill

### 1. `InlineSkill` — code-defined

[`_skills.py:L717-L918`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L717-L918).

```python
from agent_framework import InlineSkill, SkillFrontmatter

db_skill = InlineSkill(
    frontmatter=SkillFrontmatter(name="db-skill", description="Database operations."),
    instructions="Use this skill to query the operational database.",
)

@db_skill.resource
def get_schema() -> str:
    return "CREATE TABLE users ..."

@db_skill.script(description="Run a SELECT query")
async def query(sql: str) -> list[dict]:
    return await db.execute(sql)
```

- `@skill.resource` / `@skill.script` decorators support bare (`@skill.resource`) and parameterized (`@skill.resource(name=..., description=...)`) forms.
- Code-defined scripts always run **in-process** — no `SkillScriptRunner` involved ([`_skills.py:L1427-L1428`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1427-L1428)).

### 2. `FileSkill` — filesystem-backed

[`_skills.py:L1341-L1409`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1341-L1409).

Discovered automatically by `FileSkillsSource` or `SkillsProvider.from_paths(...)` from directories containing `SKILL.md`:

```text
my-skill/
├── SKILL.md          # required — YAML frontmatter + Markdown body
├── references/       # discoverable resources (DEFAULT_RESOURCE_DIRECTORIES)
│   └── schema.md
├── assets/           # discoverable resources
│   └── template.xml
└── scripts/          # discoverable scripts (DEFAULT_SCRIPT_DIRECTORIES)
    └── query.py
```

Default extensions ([`_skills.py:L1463-L1479`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1463-L1479)):

- Resources: `.md`, `.json`, `.yaml`, `.yml`, `.csv`, `.xml`, `.txt`
- Scripts: `.py`
- Resource dirs: `references`, `assets`
- Script dirs: `scripts`
- Use `"."` as a directory name to mean the skill root itself.

### 3. `ClassSkill` — class-based

[`_skills.py:L1002`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1002). Use when you want skills bound to an object's lifecycle (e.g., per-tenant instances). Mark members with framework-provided markers to expose them as resources or scripts.

## `SkillsProvider` — wiring skills to an agent

[`_skills.py:L1642-L1900+`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1642-L1900).

```python
from agent_framework import SkillsProvider

# From file directories
provider = SkillsProvider.from_paths("./skills", script_runner=my_runner)

# From code-defined skills
provider = SkillsProvider([db_skill, weather_skill])

# Single skill
provider = SkillsProvider(db_skill)
```

> [!TIP]
> Use `SkillsProvider.from_paths(...)` for file-backed skills. Do **not** pass a string/Path directly to `SkillsProvider(...)` — it raises `TypeError` ([`_skills.py:L1763-L1767`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1763-L1767)) with a helpful message.

### Key constructor flags

| Parameter | Default | Effect |
|-----------|---------|--------|
| `instruction_template` | None | Custom system-prompt template. Must contain `{skills}`; if file scripts are present also `{runner_instructions}`; if resources are present also `{resource_instructions}`. |
| `require_script_approval` | `False` | When `True`, agent pauses and emits a `function_approval_request` before running any skill script. Caller must call `request.to_function_approval_response(approved=True/False)` and pass back via `agent.run(approval_response, session=session)`. |
| `disable_caching` | `False` | Re-query the source on every `agent.run()` (so file edits are picked up live). |
| `source_id` | `"agent_skills"` | Per-instance unique provider id (`DEFAULT_SOURCE_ID` class var). |

## Composing sources

For multi-source scenarios, compose explicitly:

```python
from agent_framework import (
    AggregatingSkillsSource,
    DeduplicatingSkillsSource,
    FileSkillsSource,
    FilteringSkillsSource,
    InMemorySkillsSource,
    SkillsProvider,
)

source = DeduplicatingSkillsSource(
    FilteringSkillsSource(
        AggregatingSkillsSource([
            FileSkillsSource("./skills", script_runner=my_runner),
            InMemorySkillsSource([db_skill]),
        ]),
        predicate=lambda s: s.frontmatter.name != "internal",
    )
)
provider = SkillsProvider(source)
```

(Pattern from [`_skills.py:L1686-L1696`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1686-L1696).)

## `SkillScriptRunner` — file script execution strategy

[`_skills.py:L1417-L1453`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1417-L1453). `@runtime_checkable` Protocol — any callable matching the signature works:

```python
async def my_runner(skill, script, args=None):
    # E.g., spawn a subprocess, call a hosted code interpreter, ...
    return result
```

> [!NOTE]
> Code-defined scripts (via `@skill.script`) **always run in-process** and bypass the runner. Only `FileSkillScript` instances go through `SkillScriptRunner`.

## Security

[`_skills.py:L1661-L1663`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1661-L1663):

> File-based metadata is XML-escaped before prompt injection, and file-based resource reads are guarded against path traversal and symlink escape. Only use skills from trusted sources.

For scripts you can't fully trust, set `require_script_approval=True` and surface the approval request in your UI.

## Constants

[`_skills.py:L1458-L1479`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1458-L1479):

| Constant | Value |
|----------|-------|
| `SKILL_FILE_NAME` | `"SKILL.md"` |
| `MAX_SEARCH_DEPTH` | `2` |
| `MAX_NAME_LENGTH` | `64` |
| `MAX_DESCRIPTION_LENGTH` | `1024` |
| `MAX_COMPATIBILITY_LENGTH` | `500` |
| `DEFAULT_RESOURCE_EXTENSIONS` | `(".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt")` |
| `DEFAULT_SCRIPT_EXTENSIONS` | `(".py",)` |
| `DEFAULT_RESOURCE_DIRECTORIES` | `("references", "assets")` |
| `DEFAULT_SCRIPT_DIRECTORIES` | `("scripts",)` |
| `ROOT_DIRECTORY_INDICATOR` | `"."` |

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Calling `SkillsProvider("./skills")` directly | Raises `TypeError`. Use `SkillsProvider.from_paths("./skills")`. |
| Skill name with uppercase letters, underscores, or starting hyphen | `ValueError` at `SkillFrontmatter` construction. |
| Adding `@skill.resource` *after* the first `skill.content` access | Cached — won't be included. Add all resources/scripts before first use. |
| File-based script execution without `script_runner=...` | Scripts won't be executable; only resources are discoverable. |
| Production use without setting an exact-version pin | Skills are `@experimental`. Pin to `agent-framework-foundry==1.8.0` (no caret). |
| Trusting third-party `SKILL.md` files | Scripts can do anything in your `script_runner` sandbox. Always use `require_script_approval=True` for untrusted sources. |

## See also

- [agentskills.io specification](https://agentskills.io/specification)
- [`sessions.md`](sessions.md) — `SkillsProvider` *is* a `ContextProvider`
- [`agents.md`](agents.md) — wire via `context_providers=[SkillsProvider(...)]`
- [`../../patterns/inline-skill-definition.md`](../../patterns/inline-skill-definition.md)
