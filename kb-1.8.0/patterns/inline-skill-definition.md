# Pattern: Defining and Wiring an Inline Skill

> Status: ⚠️ **EXPERIMENTAL** — `Skill`, `InlineSkill`, `SkillsProvider` are `@experimental(ExperimentalFeature.SKILLS)`.
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_skills.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py)
> Specification: [agentskills.io](https://agentskills.io/specification)

## Goal

Define a domain skill **in code** (no `SKILL.md` file) and wire it into an agent so the LLM gets progressive-disclosure access: a short advertisement in the system prompt, then full body on demand, then resource reads / script invocations.

## When to use this pattern

- You want to bundle a domain capability as a portable, self-describing unit *before* you commit to a file layout.
- You want the skill's resources and scripts to live in the same Python module as the rest of your application.
- You don't yet need cross-process / cross-language skill discovery (use `FileSkill` + `SKILL.md` for that).

## Code

```python
from agent_framework import (
    AgentSession,
    InlineSkill,
    SkillFrontmatter,
    SkillsProvider,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
import os

# 1. Build the skill
db_skill = InlineSkill(
    frontmatter=SkillFrontmatter(
        name="db-skill",                # lowercase + hyphens only, ≤64 chars
        description="Read-only PostgreSQL operations against the orders DB.",
        license="MIT",
        compatibility="postgres>=14",
        metadata={"owner": "data-team"},
    ),
    instructions=(
        "Use this skill when the user asks about orders, customers, or revenue. "
        "Always call get_schema before constructing a query, then call run_query."
    ),
)


@db_skill.resource(description="Schema of the orders database")
def get_schema() -> str:
    return """\
CREATE TABLE orders (
  id BIGSERIAL PRIMARY KEY,
  customer_id BIGINT,
  total_cents BIGINT,
  created_at TIMESTAMPTZ
);
"""


@db_skill.script(description="Run a read-only SELECT against orders DB")
async def run_query(sql: str) -> list[dict]:
    if not sql.strip().lower().startswith("select"):
        raise ValueError("only SELECT statements are permitted")
    async with my_pool.acquire() as conn:
        rows = await conn.fetch(sql)
        return [dict(r) for r in rows]


# 2. Wrap in a provider
skills = SkillsProvider(
    [db_skill],
    require_script_approval=True,    # opt-in safety for any script call
    disable_caching=False,
)

# 3. Wire to the agent
async with AzureCliCredential() as cred:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=cred,
    )
    async with client.as_agent(
        name="data-assistant",
        instructions="You answer questions about the orders database.",
        context_providers=[skills],
    ) as agent:
        session = AgentSession()
        response = await agent.run("How many orders did customer 42 place?", session=session)
```

## Why each piece

- **`SkillFrontmatter` is validated at construction.** Lowercase + hyphens only for `name` (regex `^[a-z0-9]([a-z0-9]*-[a-z0-9])*[a-z0-9]*$`, [`_skills.py:L1513`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1513)), `description ≤ 1024` chars, optional `compatibility ≤ 500`. Validation runs **only at construction** — reassignment afterward is *not* re-validated.
- **`@skill.resource` and `@skill.script` decorators** accept both bare (`@skill.resource`) and parameterized (`@skill.resource(name=..., description=...)`) forms ([`_skills.py:L799-L857`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L799-L857) and [`_skills.py:L859-L918`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L859-L918)). The decorated function is returned unchanged.
- **Code-defined scripts run in-process.** No `SkillScriptRunner` is involved — that's only for `FileSkillScript` instances ([`_skills.py:L1427-L1428`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1427-L1428)).
- **`require_script_approval=True`** makes the agent pause and emit a `function_approval_request` instead of running scripts immediately. Your UI/orchestrator must call `request.to_function_approval_response(approved=True)` and pass the response back to `agent.run(approval_response, session=session)`. Strongly recommended for any script that mutates state or hits external services.

## Approval loop (when `require_script_approval=True`)

```python
response = await agent.run("How many orders did customer 42 place?", session=session)
for req in response.user_input_requests:
    print(f"Approve {req.function_name}({req.arguments})? [y/N]")
    decision = input().strip().lower() == "y"
    approval = req.to_function_approval_response(approved=decision)
    response = await agent.run(approval, session=session)
```

(Pattern documented at [`_skills.py:L1744-L1755`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1744-L1755).)

## Cost / token characteristics

Progressive disclosure ([`_skills.py:L1655-L1659`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L1655-L1659)):

1. **Advertise** (~100 tokens / skill) — system prompt only gets `name` + `description`.
2. **Load** — LLM calls the `load_skill` tool when relevant. Full `instructions` body returned.
3. **Read resources / run scripts** — `read_skill_resource` and per-script tools.

You can scale to dozens of skills without bloating the system prompt — only the active skill's body enters context.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Skill name with uppercase, underscores, or starting hyphen | `ValueError` at construction. Use `kebab-case` only. |
| Skill name >64 chars or description >1024 chars | `ValueError`. |
| Adding `@skill.resource` *after* the first `skill.content` access | Cached — won't be reflected. Define all resources/scripts *before* the agent first runs. |
| Forgetting `await` on an async script | The framework awaits it — but if your script forgets to await an inner coroutine, you get a `coroutine was never awaited` warning. |
| Treating `metadata={"owner": "..."}` as a shared dict | Shallow-copied at construction ([`_skills.py:L602-L603`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_skills.py#L602-L603)). Mutating the caller's dict afterward does not affect the skill. |
| Passing a path string to `SkillsProvider(...)` directly | Raises `TypeError`. Use `SkillsProvider.from_paths(...)` for file-backed skills. |
| Production use without pinning exact version | `@experimental` may change between minors. Pin `agent-framework-foundry==1.8.0` (no caret/tilde). |

## Verification

```python
# Smoke test: assert skill builds & SkillsProvider accepts it.
from agent_framework import InlineSkill, SkillFrontmatter, SkillsProvider

skill = InlineSkill(
    frontmatter=SkillFrontmatter(name="x", description="test"),
    instructions="hello",
)
provider = SkillsProvider([skill])
assert skill.frontmatter.name == "x"
assert "hello" in skill.content

# Reject bad name
try:
    SkillFrontmatter(name="Bad_Name", description="x")
except ValueError as e:
    print("validated:", e)
```

## See also

- [`../api-reference/1.8.0/skills.md`](../api-reference/1.8.0/skills.md) — full skill subsystem reference
- [`../api-reference/1.8.0/sessions.md`](../api-reference/1.8.0/sessions.md) — `SkillsProvider` is a `ContextProvider`
- [agentskills.io specification](https://agentskills.io/specification)
