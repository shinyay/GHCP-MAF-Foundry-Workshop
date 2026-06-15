# Pattern: Agent-as-Tool Handoff (Coordinator + Specialists)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: upstream sample [`02-agents/tools/agent_as_tool_with_session_propagation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/tools/agent_as_tool_with_session_propagation.py) and source [`_agents.py:L478-L572`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L478-L572)
> See also: [API ref — `composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md)

## Goal

Build a **coordinator agent** that delegates to one or more **specialist agents** via `BaseAgent.as_tool()`. The coordinator's LLM decides at runtime when (and whether) to invoke each specialist — this is the **handoff** pattern, distinct from the deterministic-flow `WorkflowBuilder` pattern.

## When to use

| Need | This pattern? |
|---|---|
| LLM picks **at runtime** which specialist to call (or none) | ✅ |
| You want each specialist to share session state (collaborative findings) | ✅ — with `propagate_session=True` |
| You want a **deterministic** pipeline (research → write → review) | ❌ → use [`multi-agent-workflow.md`](multi-agent-workflow.md) |
| You need to expose the agent to **external** processes / hosts | ❌ → use [`agent-as-mcp-server.md`](agent-as-mcp-server.md) |
| You need a multi-step planner inside another workflow | ❌ → use [`workflow-as-agent-nesting.md`](workflow-as-agent-nesting.md) |

## Prerequisites

- `agent-framework-core==1.8.0` (transitively via `agent-framework-foundry==1.8.0`)
- Either `OpenAIChatClient` (cheaper, easier local dev) or `FoundryChatClient` (production) — this template's canonical client is `FoundryChatClient`, but the upstream-verified sample uses `OpenAIChatClient` for brevity. Agents created with either client expose the same `as_tool` API (it lives on `BaseAgent` via the agent's MRO); only the underlying chat completions provider differs.
- `.env` configured with chat-client credentials (see [`canonical-agent-creation.md`](canonical-agent-creation.md))

## Architecture

```text
                 ┌──────────────────────────┐
                 │   CoordinatorAgent       │
   user query →  │   (decides who to call)  │
                 └──┬─────────┬─────────┬───┘
                    │         │         │
              as_tool        as_tool   as_tool
                    │         │         │
                    ▼         ▼         ▼
            ┌───────────┐ ┌─────────┐ ┌─────────┐
            │ Research  │ │ Recall  │ │ Store   │
            │  Agent    │ │ Tool    │ │ Tool    │
            └────┬──────┘ └────┬────┘ └────┬────┘
                 │             │           │
                 └─── shared session.state ┘
                     (propagate_session=True)
```

## Worked example (Foundry-flavored, mirrors upstream sample)

```python
# pattern: agent-as-tool handoff with shared session
# Verified against samples/02-agents/tools/agent_as_tool_with_session_propagation.py

import asyncio
from collections.abc import Awaitable, Callable

from agent_framework import (
    Agent,
    AgentContext,
    AgentSession,
    FunctionInvocationContext,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv(override=False)


async def log_session(
    context: AgentContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Agent middleware — visible proof that session_id is shared."""
    session: AgentSession | None = context.session
    agent_name = context.agent.name or "unknown"
    if session is None:
        print(f"  [{agent_name}] no session attached")
    else:
        print(
            f"  [{agent_name}] session_id={session.session_id}, "
            f"state_keys={list(session.state.keys())}"
        )
    await call_next()


@tool(description="Store findings so that other agents can reason over them.")
def store_findings(findings: str, ctx: FunctionInvocationContext) -> None:
    if ctx.session is None:
        return
    current = ctx.session.state.get("findings")
    ctx.session.state["findings"] = (
        findings if current is None else f"{current}\n{findings}"
    )


@tool(description="Recall current findings gathered by any agent.")
def recall_findings(ctx: FunctionInvocationContext) -> str:
    if ctx.session is None:
        return "No session available"
    return ctx.session.state.get("findings") or "Nothing yet"


async def main() -> None:
    async with AzureCliCredential() as credential:
        # FoundryChatClient is NOT a context manager in 1.8.0; just instantiate.
        client = FoundryChatClient(credential=credential)
        # 1) Specialist: focused, has its own instructions and tools.
        research_agent = Agent(
            client=client,
            name="ResearchAgent",
            instructions=(
                "You are a research assistant. Answer concisely and call "
                "store_findings to persist your conclusions."
            ),
            middleware=[log_session],
            tools=[store_findings, recall_findings],
        )

        # 2) Wrap specialist as a tool. Explicit name + production approval mode.
        research_tool = research_agent.as_tool(
            name="research",
            description="Research a topic and store findings in the shared session.",
            arg_name="query",
            arg_description="The research question",
            approval_mode="never_require",   # change to "always_require" for production
            propagate_session=True,          # share session.state with coordinator
        )

        # 3) Coordinator: routes work to the specialist + has the same memory tools.
        coordinator = Agent(
            client=client,
            name="CoordinatorAgent",
            instructions=(
                "You coordinate research. Use the 'research' tool to investigate, "
                "then use recall_findings to consolidate the answer."
            ),
            tools=[research_tool, store_findings, recall_findings],
            middleware=[log_session],
        )

        # 4) Create one session and reuse it — the specialist will see the same one.
        session = coordinator.create_session()
        session.state["findings"] = None
        print(f"Session ID: {session.session_id}\n")

        result = await coordinator.run(
            "What are the latest developments in quantum computing and in AI?",
            session=session,
        )
        print(f"\nCoordinator → {result}\n")
        print(f"Final state: {session.state}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

| Line | What it does | Why it matters |
|---|---|---|
| `tools=[store_findings, recall_findings]` (on `ResearchAgent`) | Specialist owns its own write/read tools | Tools are scoped to the agent — coordinator's identically-named tools are **separate** function objects, not aliases. |
| `as_tool(name="research", ...)` | Wraps the agent as a `FunctionTool` ([`_agents.py:L478-L572`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L478-L572)) | The coordinator's LLM now sees `research` as just another function. **Explicit `name=`** dodges `_sanitize_agent_name` collisions. |
| `arg_name="query"` | Single string parameter the LLM passes | The wrapper exposes exactly one required string property ([`L533-L543`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L533-L543)). |
| `approval_mode="never_require"` | Default — auto-runs without prompting | **Sample brevity only.** Production agents that have write side-effects should use `"always_require"` so the human/parent approves each call ([`L485`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L485)). |
| `propagate_session=True` | Shares `ctx.session` between coordinator and specialist ([`L499-L501, L555`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L499-L555)) | Both agents see and can mutate `session.state["findings"]`. **Without this**, the specialist gets a fresh empty session each call. |
| `coordinator.create_session()` + `session.state[...] = ...` | Sets shared scratchpad before the run | The specialist will see this state on its first invocation **only if** `propagate_session=True`. |
| `middleware=[log_session]` (both agents) | Logs `session_id` per agent on each call | Verification — you should see the **same** `session_id` in both `[ResearchAgent]` and `[CoordinatorAgent]` log lines. |
| `async with credential, client:` | Cleans up HTTP sessions, credential token caches | Avoid `Unclosed connector` warnings; see [`anti-patterns/missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md). |

## Variants

### 1) Stream the specialist's output back to the coordinator's UI

```python
async def stream_callback(update):
    print(update.text, end="", flush=True)

research_tool = research_agent.as_tool(
    name="research",
    description="...",
    arg_name="query",
    stream_callback=stream_callback,   # fires on each AgentResponseUpdate
)
```

The wrapper always calls `self.run(stream=True)` internally and `with_transform_hook(stream_callback)` is applied on the stream ([`L552-L559`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L552-L559)). You only see updates if you pass the callback — the final string result is unchanged.

### 2) Multiple specialists with disjoint state

When specialists should **not** share state, omit `propagate_session=True`. Each specialist gets a fresh session per call:

```python
writer_tool = writer_agent.as_tool(
    name="write",
    description="Write a draft from notes.",
    arg_name="notes",
    # propagate_session=False is the default → independent sessions
)
```

### 3) Approval-gated delegation

For sub-agents that perform real side effects (DB writes, billing, sending email), wire an approval handler in the coordinator's run loop:

```python
research_tool = research_agent.as_tool(
    name="research",
    description="...",
    arg_name="query",
    approval_mode="always_require",
)
# In production: catch FunctionApprovalRequiredException at the coordinator
# and prompt human-in-the-loop before calling.
```

See `samples/02-agents/tools/function_tool_with_approval.py` upstream for the approval workflow.

### 4) Coordinator handles sub-agent's user-input requests

When a specialist asks the user for input, the wrapper **re-raises** `UserInputRequiredException` at the tool boundary ([`L561-L562`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L561-L562)). The coordinator must catch it:

```python
from agent_framework import UserInputRequiredException

try:
    result = await coordinator.run(query, session=session)
except UserInputRequiredException as exc:
    # Prompt the human, then resume the conversation.
    user_reply = input("Specialist needs input: ")
    # Pass user_reply back via the coordinator's next turn.
```

## Common mistakes

### Auto-name collision when registering multiple display-name-only specialists

```python
# ❌ Wrong — all three sanitize to the same tool name "Research_Agent"
tools = [
    Agent(client=c, name="Research Agent").as_tool(),
    Agent(client=c, name="Research-Agent").as_tool(),
    Agent(client=c, name="Research.Agent").as_tool(),
]
# Coordinator sees three tools competing for the same key → unpredictable routing
```

```python
# ✅ Right — pass explicit, stable, machine-safe names
tools = [
    Agent(client=c, name="Research Agent").as_tool(name="research_topic"),
    Agent(client=c, name="Research-Agent").as_tool(name="research_paper"),
    Agent(client=c, name="Research.Agent").as_tool(name="research_news"),
]
```

See [`anti-patterns/composition-pitfalls.md#4-tool-name-collisions-from-sanitization`](../anti-patterns/composition-pitfalls.md#4-tool-name-collisions-from-sanitization).

### Forgetting to catch `UserInputRequiredException` at the coordinator

If the specialist signals `user_input_requests`, the tool call **fails** — the coordinator's run terminates with an unhandled exception unless you wrap it.

### Sharing session for unrelated specialists

`propagate_session=True` is intentional **collaboration**. Unrelated specialists that mutate the same `session.state` keys produce state-pollution bugs. Either namespace your keys (`state["research_findings"]`, `state["writer_findings"]`) or leave session propagation off.

### Treating `as_tool` as deterministic flow

The LLM decides whether to call the tool. If the coordinator's instructions are vague, the LLM may **not** delegate. For guaranteed execution order, use [`multi-agent-workflow.md`](multi-agent-workflow.md) — that's what `WorkflowBuilder` is for.

## Verification

Run the script and confirm:

1. ✅ The two `[CoordinatorAgent]` and `[ResearchAgent]` middleware lines log the **same** `session_id`.
2. ✅ After the run, `session.state["findings"]` contains the text the specialist stored.
3. ✅ No `Unclosed connector` / `ResourceWarning` at exit (proves `async with` is wired correctly).

Smoke test the import surface (works without credentials):

```bash
python -c "from agent_framework import Agent, AgentContext, AgentSession, FunctionInvocationContext, tool; print('OK')"
python -c "from agent_framework.foundry import FoundryChatClient; print('OK')"
```

## See also

- [API ref — `composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md) — full directional matrix
- [Pattern — `agent-as-mcp-server.md`](agent-as-mcp-server.md) — same agent, cross-process
- [Pattern — `multi-agent-workflow.md`](multi-agent-workflow.md) — deterministic flow alternative
- [Pattern — `workflow-as-agent-nesting.md`](workflow-as-agent-nesting.md) — wrap a workflow as an agent (then `as_tool` it)
- [Anti-pattern — `composition-pitfalls.md`](../anti-patterns/composition-pitfalls.md) — 13 things to avoid
- [Anti-pattern — `missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md) — credential/client lifecycle
