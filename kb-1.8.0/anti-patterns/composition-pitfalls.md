# Anti-Patterns: Composition Pitfalls (`as_tool` / `as_mcp_server` / `as_agent`)

> Status: **Active hazard**
> Affects: 1.0.0 → 1.8.0 (composition adapters were stabilized in 1.0; behavior verified for 1.8.0)
> Severity: **Medium → High** depending on item — covers security (#1, #2, #9), correctness (#3, #5, #8, #10, #12, #13), portability (#7), naming hygiene (#4), resource hygiene (#6), and design (#11)

Companion to [`api-reference/1.8.0/composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md) and the two pattern pages ([handoff](../patterns/agent-as-tool-handoff.md), [MCP server](../patterns/agent-as-mcp-server.md)). Each entry below shows the **minimal wrong code**, the **fix**, and a **detection recipe** (grep / code-review checklist).

---

## 1. `approval_mode="never_require"` for write-effecting agent tools

### Symptom

A sub-agent performs DB writes, sends emails, or charges money — and the coordinator's LLM is free to call it at any time without human/parent approval.

### ❌ Wrong

```python
from agent_framework import Agent, tool

@tool
def charge_card(amount_usd: float, customer_id: str) -> str:
    """Charge the customer's card."""
    # ... real Stripe call ...
    return f"Charged ${amount_usd} to {customer_id}"

billing_agent = Agent(client=client, name="BillingAgent", tools=[charge_card])

# The coordinator can invoke this any time the LLM decides to
billing_tool = billing_agent.as_tool(
    name="bill_customer",
    description="Bill a customer.",
    arg_name="instruction",
    # approval_mode defaults to "never_require"  ← _agents.py:L485
)
```

### Why it's wrong

`as_tool`'s default `approval_mode="never_require"` is sample brevity, not a production default ([`_agents.py:L485`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L485)). Any prompt-injection attack on the coordinator's context can trigger the billing agent.

### ✅ Right

```python
billing_tool = billing_agent.as_tool(
    name="bill_customer",
    description="Bill a customer.",
    arg_name="instruction",
    approval_mode="always_require",   # parent / human must approve each call
)
# Coordinator's run loop must handle FunctionApprovalRequiredException.
```

### How to detect

```bash
# Find every as_tool call that uses the default approval mode
grep -rn '\.as_tool(' --include='*.py' | grep -v 'approval_mode='

# Find explicit "never_require" on tools wrapping non-trivial agents
grep -rn 'approval_mode="never_require"' --include='*.py'
```

---

## 2. `propagate_session=True` across unrelated coordinator/specialist

### Symptom

Two specialists that have nothing to do with each other are wrapped as tools on the same coordinator with `propagate_session=True`. State written by one specialist surfaces unexpectedly to the other.

### ❌ Wrong

```python
billing_tool = billing_agent.as_tool(name="bill", arg_name="i", propagate_session=True)
research_tool = research_agent.as_tool(name="research", arg_name="i", propagate_session=True)

# Both write to session.state["last_result"]:
#   billing_agent → state["last_result"] = {"charged": 99.00}
#   research_agent → state["last_result"] = "Quantum computing summary..."
# → Whoever ran last clobbers the other.
```

### Why it's wrong

`propagate_session=True` forwards the **parent's `ctx.session` object** to the sub-agent ([`_agents.py:L499-L501, L555`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L499-L555)). Both agents see and mutate the same `state` dict. Use it only when agents are intentionally collaborating on shared findings (per the upstream sample).

### ✅ Right

```python
# Option A: independent sessions (default) — safest for unrelated specialists
billing_tool = billing_agent.as_tool(name="bill", arg_name="i")          # propagate_session=False
research_tool = research_agent.as_tool(name="research", arg_name="i")    # propagate_session=False

# Option B: shared session BUT namespaced keys — collaboration without collision
@tool
def store_billing(result: dict, ctx: FunctionInvocationContext) -> None:
    if ctx.session: ctx.session.state["billing_result"] = result

@tool
def store_research(text: str, ctx: FunctionInvocationContext) -> None:
    if ctx.session: ctx.session.state["research_findings"] = text
```

### How to detect

```bash
# Audit: every propagate_session=True needs a "we are intentionally collaborating" comment
grep -rn 'propagate_session=True' --include='*.py'
```

Code review: if two `as_tool` calls in the same scope use `propagate_session=True`, the agents must share a documented collaboration contract.

---

## 3. Wrapping an anonymous agent without an explicit `name=`

### Symptom

```text
ValueError: Agent tool name cannot be None
```

### ❌ Wrong

```python
agent = Agent(client=client)    # no name=
tool = agent.as_tool(            # no explicit name= either
    description="...",
    arg_name="query",
)
```

### Why it's wrong

`as_tool` falls back to `_sanitize_agent_name(self.name)` ([`_agents.py:L527`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L527)). If `self.name` is `None` and no explicit `name=` was passed, the wrapper raises `ValueError("Agent tool name cannot be None")` ([`L528-L529`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L528-L529)).

### ✅ Right

```python
# Either give the agent a name at construction:
agent = Agent(client=client, name="ResearchAgent")
tool = agent.as_tool(description="...", arg_name="query")

# Or pass an explicit tool name:
agent = Agent(client=client)
tool = agent.as_tool(name="research", description="...", arg_name="query")
```

### How to detect

```bash
# Likely-broken pattern: Agent(...) with no name= near an as_tool() with no name=
grep -B2 -A2 -rn '\.as_tool(' --include='*.py' | grep -v 'name='
```

---

## 4. Tool name collisions from sanitization

### Symptom

A coordinator is given 2+ specialists with different display names that collapse to the same machine-safe tool name. The LLM's tool registry has only one of them (whichever was added last).

### ❌ Wrong

```python
tools = [
    Agent(client=c, name="Research Agent").as_tool(description="..."),
    Agent(client=c, name="Research-Agent").as_tool(description="..."),
    Agent(client=c, name="Research.Agent").as_tool(description="..."),
]
# All three sanitize to the same tool name "Research_Agent".
# The coordinator's tool registry sees one entry — routing is unpredictable.
```

### Why it's wrong

`_sanitize_agent_name` ([`_agents.py:L129-L163`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L129-L163)) replaces every non-`[a-zA-Z0-9_]` character with `_`, collapses runs, strips edges, and falls back to `"agent"` for fully sanitized empty strings:

| `self.name` | Auto-derived tool name |
|---|---|
| `"Research Agent"` | `"Research_Agent"` |
| `"Research-Agent"` | `"Research_Agent"` |
| `"Research.Agent"` | `"Research_Agent"` |
| `"  Research   Agent  "` | `"Research_Agent"` |
| `"!!!"` | `"agent"` |
| `"???"` | `"agent"` |
| `"2nd-helper"` | `"_2nd_helper"` (leading digit gets `_` prefix) |

### ✅ Right

```python
tools = [
    Agent(client=c, name="Research Agent").as_tool(name="research_topic"),
    Agent(client=c, name="Research-Agent").as_tool(name="research_paper"),
    Agent(client=c, name="Research.Agent").as_tool(name="research_news"),
]
```

Always pass an **explicit, stable, machine-safe** `name=` for any agent wrapped as a tool. Display names belong to humans; tool names belong to the LLM's tool registry.

### How to detect

```bash
# Find as_tool calls that omit name= and rely on auto-derivation
grep -rn '\.as_tool(' --include='*.py' | grep -v 'name='
```

Code review: when 2+ `as_tool`-wrapped agents appear together, confirm each has an explicit `name=`.

---

## 5. Calling `as_mcp_server()` without installing `mcp`

### Symptom

```text
ModuleNotFoundError: `mcp` is required to use `Agent.as_mcp_server()`. Please install `mcp`.
```

Raised at the `as_mcp_server()` call site, **not** at module import time.

### ❌ Wrong

```bash
pip install agent-framework-core   # mcp is NOT a transitive dep here
```

```python
from agent_framework import Agent
agent = Agent(client=client, name="MyAgent")
server = agent.as_mcp_server()    # ModuleNotFoundError raised HERE
```

### Why it's wrong

`as_mcp_server` lazy-imports `mcp` inside the method body ([`_agents.py:L1480-L1483`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1480-L1483)) — this keeps `agent-framework-core` slim for users who never expose agents over MCP. `mcp` is **not** declared as a hard dependency. The workshop venv pins `mcp==1.27.0` transitively (verified via `pip show mcp`).

### ✅ Right

```bash
pip install agent-framework-foundry==1.8.0 mcp
```

```python
from agent_framework import Agent
agent = Agent(client=client, name="MyAgent")
async with agent:
    server = agent.as_mcp_server()   # works
```

### How to detect

```bash
# Confirm mcp is installed in the active venv
pip show mcp || echo "mcp NOT installed — as_mcp_server() will fail"

# Find uses of as_mcp_server to audit
grep -rn '\.as_mcp_server(' --include='*.py'
```

---

## 6. MCP server without agent lifecycle (`async with agent:`)

### Symptom

`ResourceWarning: unclosed <ssl.SSLSocket ...>`, `Unclosed connector`, or leaked credential token caches when the MCP server shuts down. Long-running servers accumulate sockets until the OS ulimit hits.

### ❌ Wrong (the upstream sample omits `async with` — do not copy verbatim into production)

```python
async def run() -> None:
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        agent = Agent(client=client, name="RestaurantAgent", tools=[...])

        # Agent never enters async with — its __aexit__ never runs
        server = agent.as_mcp_server()

        from mcp.server.stdio import stdio_server
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())
```

### Why it's wrong

The agent holds references to the chat client and credential. Without `async with agent:`, the agent's `__aexit__` never fires when the MCP server exits — so the chat client's HTTP session and the credential's token cache are not explicitly released. The outer `async with credential:` does eventually clean up at the **outer** scope, but only after MCP's `server.run` returns. For long-lived MCP servers, this means resources stay pinned for the whole server lifetime even when they could be released earlier — and any cleanup-during-server-run bugs become latent.

### ✅ Right

```python
async def run() -> None:
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        agent = Agent(client=client, name="RestaurantAgent", tools=[...])
        async with agent:                # ← add this
            server = agent.as_mcp_server()
            from mcp.server.stdio import stdio_server
            async with stdio_server() as (r, w):
                await server.run(r, w, server.create_initialization_options())
```

### How to detect

```bash
# Find as_mcp_server calls and verify each is inside an `async with <agent>:` block
grep -B5 '\.as_mcp_server(' --include='*.py' -rn | grep -E 'async with|\.as_mcp_server'
```

See also: [`missing-async-with-cleanup.md`](missing-async-with-cleanup.md).

---

## 7. Expecting rich-content forwarding through MCP

### Symptom

An MCP host calls your image-generating or audio-generating agent. The host receives only the agent's text commentary; the actual image / audio bytes never arrive. Server logs show:

```text
WARNING agent_framework._agents: Unsupported content type dropped from MCP response: ImageContent
```

### ❌ Wrong

```python
image_agent = Agent(
    client=client,
    name="ImageGen",
    tools=[client.get_image_generation_tool().as_dict()],
)
async with image_agent:
    server = image_agent.as_mcp_server()   # only text gets through
    # ...
```

### Why it's wrong

`as_mcp_server`'s response forwarding loops over the tool invocation result and only emits `TextContent` items; non-text items (image, audio, data, uri) are dropped with the warning `"MCP server does not yet forward rich content (images, audio) in tool results. Rich content items will be omitted."` ([`_agents.py:L1554-L1564`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1554-L1564)). The MCP protocol itself supports richer content types, but the framework's current adapter does not bridge them.

### ✅ Right

Either:

1. **Return URLs.** Upload the image to blob storage in your tool, return the URL as text. The MCP host fetches it.
2. **Use a different transport.** For in-process rich-content scenarios, use [`agent-as-tool-handoff.md`](../patterns/agent-as-tool-handoff.md) instead — full `AgentRunResponse` content is preserved.

### How to detect

```bash
# Find agents that use rich-content hosted tools AND get exposed over MCP
grep -B10 '\.as_mcp_server(' --include='*.py' -rn | \
    grep -E 'image_generation|audio_generation|file_search'
```

---

## 8. `Workflow.as_agent()` on a workflow whose start executor cannot handle `list[Message]`

### Symptom

```text
ValueError: Workflow's start executor cannot handle list[Message]
```

Raised at `WorkflowAgent.__init__` ([`_workflows/_agent.py:L120-L121`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent.py#L120-L121)).

### ❌ Wrong

```python
class MyJobSpec(BaseModel):
    domain: str
    keywords: list[str]

class Planner(Executor):
    @handler
    async def plan(self, spec: MyJobSpec, ctx: WorkflowContext[..., str]) -> None:
        await ctx.yield_output("ok")

workflow = WorkflowBuilder(name="planner_v1", start_executor=Planner(id="planner")).build()
agent = workflow.as_agent(name="PlannerAgent")     # ValueError
```

### Why it's wrong

`WorkflowAgent` normalizes agent-facing input (`str`, `Message`, `list[Message]`) into `list[Message]` before invoking the workflow. If the start executor only declares `MyJobSpec` in its `input_types`, the conversion fails. The validation runs at construction so the failure is loud and immediate.

### ✅ Right

Add a normalizing executor at the front, or widen the start executor's input types:

```python
class Normalize(Executor):
    @handler
    async def normalize(self, messages: list[Message], ctx: WorkflowContext[MyJobSpec]) -> None:
        text = "\n".join(m.text for m in messages)
        await ctx.send_message(MyJobSpec.model_validate_json(text))

workflow = (
    WorkflowBuilder(name="planner_v1", start_executor=Normalize(id="normalize"))
    .add_edge("normalize", Planner(id="planner"))
    .build()
)
agent = workflow.as_agent(name="PlannerAgent")     # works
```

### How to detect

```bash
# Find Workflow.as_agent() calls and audit each workflow's start_executor.input_types
grep -rn '\.as_agent(' --include='*.py' | grep -i workflow
```

See also: [`patterns/workflow-as-agent-nesting.md`](../patterns/workflow-as-agent-nesting.md).

---

## 9. Default `context_mode="full"` for sensitive multi-agent handoffs

### Symptom

A downstream agent in a workflow sees the **entire** prior conversation — including system instructions for upstream agents, prior user PII, and reasoning traces. No data leak alert fires because this is technically working as designed.

### ❌ Wrong

```python
from agent_framework import WorkflowBuilder, AgentExecutor

triage_exec = AgentExecutor(agent=triage_agent, id="triage")
# AgentExecutor default context_mode="full" — see _agent_executor.py:L142-L185
specialist_exec = AgentExecutor(agent=specialist_agent, id="specialist")

workflow = (
    WorkflowBuilder(name="pii_pipeline", start_executor=triage_exec)
    .add_edge("triage", "specialist")
    .build()
)
# specialist_agent sees ALL of triage_agent's context: original PII + system prompt
```

### Why it's wrong

`AgentExecutor.context_mode` defaults to `"full"` ([`_workflows/_agent_executor.py:L142-L185`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent_executor.py#L142-L185)) — the executor accumulates the full conversation in `_full_conversation` and replays it to each subsequent agent. For privacy-sensitive boundaries (PII / billing / medical), this leaks far more than the downstream agent needs.

### ✅ Right

```python
# Option A: only the latest agent's response carries forward
specialist_exec = AgentExecutor(
    agent=specialist_agent,
    id="specialist",
    context_mode="last_agent",
)

# Option B: custom filter — drop messages with PII markers
def redact_filter(messages: list[Message]) -> list[Message]:
    return [m for m in messages if not m.metadata.get("contains_pii")]

specialist_exec = AgentExecutor(
    agent=specialist_agent,
    id="specialist",
    context_mode="custom",
    context_filter=redact_filter,   # required when context_mode="custom"
)
```

> Note: `context_mode="custom"` without `context_filter` raises `ValueError("context_filter must be provided when context_mode is set to 'custom'.")` ([`L184-L185`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent_executor.py#L184-L185)).

### How to detect

```bash
# Find AgentExecutor instantiations and audit context_mode
grep -rn 'AgentExecutor(' --include='*.py'
# Lines that don't include "context_mode=" → using default "full"
```

---

## 10. Transforming `AgentExecutorResponse` → plain `str` between executors

### Symptom

A downstream agent in a workflow has no idea what the upstream agent said — its prompt only contains a bare string with no role / metadata / tool-call history.

### ❌ Wrong

```python
class Router(Executor):
    @handler
    async def route(self, resp: AgentExecutorResponse, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(resp.agent_response.text)   # ← drops the conversation chain
```

### Why it's wrong

The string contains only the text of the latest message. The downstream `AgentExecutor` re-wraps it as a fresh user message, losing the role / tool-call / context-provider state that `AgentExecutorResponse` carries (it bundles `agent_response: AgentResponse` and `full_conversation: list[Message]`).

### ✅ Right

```python
class Router(Executor):
    @handler
    async def route(self, resp: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        # Forward the full response so the downstream executor can reconstruct context
        await ctx.send_message(resp.with_text(f"[routed] {resp.agent_response.text}"))
```

When you must inject text, use `AgentExecutorResponse.with_text(...)` so the chain is preserved.

### How to detect

```bash
# Find handlers that consume AgentExecutorResponse and emit str
grep -B2 -A5 -rn 'AgentExecutorResponse' --include='*.py' | grep -E 'send_message.*\.text'
```

---

## 11. Confusing handoff (`as_tool`) with orchestration (`WorkflowBuilder`)

### Symptom

Either:
- "My pipeline is flaky — sometimes the writer agent runs, sometimes the LLM skips it" (used `as_tool` when you needed `WorkflowBuilder`)
- "My agents always run in lock-step even when one's output makes the next irrelevant" (used `WorkflowBuilder` when you needed `as_tool`)

### ❌ Wrong (case A: handoff expected, orchestration used)

```python
# You wanted: research → write → review (always all three in order)
# But you wrote:
coordinator = Agent(
    client=client,
    name="Coordinator",
    tools=[
        research_agent.as_tool(name="research", arg_name="q"),
        writer_agent.as_tool(name="write", arg_name="q"),
        reviewer_agent.as_tool(name="review", arg_name="q"),
    ],
    instructions="Research then write then review.",
)
# The LLM may decide to skip steps, reorder them, or run only one.
```

### ❌ Wrong (case B: orchestration expected, handoff used)

```python
# You wanted: LLM decides whether the request needs research or just a quick answer
# But you wrote:
workflow = (
    WorkflowBuilder(name="qa", start_executor=research_agent)
    .add_edge("research_agent", writer_agent)
    .build()
)
# research_agent ALWAYS runs, even for trivial questions like "what time is it?"
```

### Why it's wrong

The two adapters serve different control-flow paradigms:

| | `as_tool` (handoff) | `WorkflowBuilder` (orchestration) |
|---|---|---|
| **Who decides execution?** | LLM (non-deterministic) | Builder (deterministic graph) |
| **Order guarantee?** | None — LLM may skip / reorder | Strict — follows `add_edge` topology |
| **Trace easy to read?** | Sometimes — depends on LLM's tool choice | Always — the graph IS the trace |
| **Best for** | Triage, conditional routing | Pipelines, fan-out/fan-in, structured stages |

### ✅ Right

```python
# Case A → use WorkflowBuilder for guaranteed order
workflow = (
    WorkflowBuilder(name="rwr_pipeline", start_executor=research_agent)
    .add_edge("research_agent", writer_agent)
    .add_edge("writer_agent", reviewer_agent)
    .build()
)

# Case B → use as_tool for LLM-decided delegation
coordinator = Agent(
    client=client,
    name="Coordinator",
    tools=[research_agent.as_tool(name="research", arg_name="q")],
    instructions="Use 'research' only when the user's question requires looking up facts.",
)
```

### How to detect

Code review: every multi-agent design should declare in a comment which paradigm it follows and **why**. If the design doc says "we want guaranteed order" but the code uses `as_tool`, that's a mismatch.

---

## 12. Expecting independent state from reused agent

### Symptom

The same `Agent` object is referenced in two `WorkflowBuilder.add_edge` calls, and the developer assumes each edge gets its own `AgentExecutor` with isolated session/cache. Instead, both edges share state — caching from edge 1 leaks into edge 2, session is bleeded.

### ❌ Wrong

```python
researcher = Agent(client=client, name="Researcher", instructions="Research a topic.")

workflow = (
    WorkflowBuilder(name="two_pass", start_executor=researcher)
    .add_edge(researcher, summarizer)
    .add_edge(summarizer, researcher)   # ← same object, same wrapper, shared state
    .build()
)
```

### Why it's wrong

`WorkflowBuilder._maybe_wrap_agent` dedupes by `id(candidate)` ([`_workflow_builder.py:L209-L213`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L209-L213)). The **same agent object** reused across edges → **same `AgentExecutor`** → shared `_cache`, `_session`, `_full_conversation`. Different agent objects with duplicate `resolve_agent_id` go the other way and raise `ValueError("Duplicate executor ID ...")` ([`L215-L219`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L215-L219)).

### ✅ Right

```python
# Option A: create two distinct Agent instances
researcher_first_pass = Agent(client=client, name="Researcher_Pass1", instructions="Research the topic broadly.")
researcher_second_pass = Agent(client=client, name="Researcher_Pass2", instructions="Refine based on the summary.")

workflow = (
    WorkflowBuilder(name="two_pass", start_executor=researcher_first_pass)
    .add_edge(researcher_first_pass, summarizer)
    .add_edge(summarizer, researcher_second_pass)
    .build()
)

# Option B: explicit AgentExecutor wrappers with distinct ids and isolated state
researcher_first = AgentExecutor(agent=researcher, id="researcher_first")
researcher_second = AgentExecutor(agent=researcher, id="researcher_second")
# (Note: still shares the underlying Agent.client — for full isolation use Option A)
```

> [!NOTE]
> Reusing the same agent across edges is **intentional and correct** when you want shared state (e.g., a memory-holding agent that should remember across edges). The anti-pattern is using it when you **expect** isolation.

### How to detect

```bash
# Find WorkflowBuilder chains where the same agent variable appears 2+ times
# (manual review — grep for the agent name)
grep -rn 'add_edge(' --include='*.py'
```

Code review: when an agent variable appears in 2+ `add_edge` calls, confirm the design intent is shared state.

---

## 13. Circular agent-tool delegation (A → B → A or self-as-tool)

### Symptom

A specialist's `as_tool`-wrapped form is somehow accessible from inside its own coordinator chain — either directly (self-as-tool) or transitively (A's tools include B; B's tools include A). The behavior at runtime is **not** documented by the framework.

### ❌ Wrong (design pattern)

```python
# Self-as-tool — construct the cycle at build time
research = Agent(
    client=client,
    name="Research",
    tools=[],   # placeholder
)
# Then later try to mutate tools to include itself:
# research.tools = [research.as_tool(...)]   # ← see "Why it's wrong" — silent no-op

# Or transitively, attempting the same:
agent_a = Agent(client=client, name="A", tools=[])
agent_b = Agent(client=client, name="B", tools=[])
# agent_a.tools = [agent_b.as_tool(name="b", arg_name="q")]
# agent_b.tools = [agent_a.as_tool(name="a", arg_name="q")]   # cycle: A→B→A→B...
```

### Why it's wrong

Two distinct failure modes — both equally bad:

1. **Post-construction mutation does not wire tools.** `Agent.__init__` stores the `tools` argument inside `default_options["tools"]` ([`_agents.py:L758`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L758)); setting `agent.tools = [...]` after construction does **not** route through the run pipeline. The tools attribute on `BaseAgent` is informational only — the runtime reads from `default_options`. So the cycle code above silently no-ops, masking the bug rather than failing loudly.

2. **Even if you constructed the cycle correctly** (e.g., by building A first with no tools, then constructing B with `tools=[a.as_tool(...)]`, then mutating A's `default_options` directly, or by registering both via a workflow), Agent Framework does not provide a construction-time cycle guard for agent-as-tool delegation — there is no validator in `as_tool` ([`_agents.py:L478-L572`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L478-L572)) that inspects the sub-agent's tool list. Runtime depends entirely on whether the LLM chooses to recurse, on token/cost limits, and on the chat client's request budget.

This is a **design-time** responsibility, not something the framework will catch for you. Self-referential or mutually-referential agent compositions should be rejected during design review.

### ✅ Right

- Audit `as_tool` chains during design review. Draw the directed graph; ensure it is acyclic.
- If you need iterative refinement, use `WorkflowBuilder` with explicit edges and a termination condition (`output_from`, `max_iterations`, or a cycle-breaking executor) instead of LLM-driven recursion.
- For self-improvement loops, use [`agent-evaluation-local.md`](../patterns/agent-evaluation-local.md) + a refine-on-fail wrapper rather than self-as-tool.

### How to detect

Manual review — there is no automated check in the framework and there is no stable public API for walking an `Agent` instance's tool list back to its source agents (the `FunctionTool` produced by `as_tool` does not expose the wrapped sub-agent through a documented attribute). Treat detection as a **design-time** activity:

- Maintain an explicit agent dependency diagram in the project's docs.
- During PR review, flag any change that lets an `as_tool`-wrapped agent end up reachable from its own coordinator.
- Prefer construction-time wiring (`Agent(..., tools=[other.as_tool(...)])`) over post-construction mutation — it makes the dependency graph readable at the call site.

---

## Common mistakes (NOT anti-patterns, but worth flagging)

These are misconceptions developers run into; they're correct framework behavior, not bugs to avoid:

- **`as_tool` re-raises `UserInputRequiredException` at the tool boundary.** ([`_agents.py:L561-L562`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L561-L562)) — The coordinator's run loop must catch it, prompt the human, and resume. This is by design; treating it as an anti-pattern would mean asking the framework to silently swallow user-input requests, which is worse. See [`agent-as-tool-handoff.md`](../patterns/agent-as-tool-handoff.md#4-coordinator-handles-sub-agents-user-input-requests).

- **`stream_callback` only fires when explicitly passed.** ([`L552-L559`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L552-L559)) — The wrapper always runs the sub-agent with `stream=True` internally, but you only observe updates via the callback. No callback → silent (but correct) execution.

- **`as_mcp_server` exposes one tool, not the agent's internal tools.** ([`L1497`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_agents.py#L1497)) — Hosts see one tool whose name is the agent's name. The agent's internal `tools=[...]` are not fanned out. This is intentional encapsulation, not a limitation to work around.

---

## See also

- [API ref — `composition-adapters.md`](../api-reference/1.8.0/composition-adapters.md) — the full directional matrix and method signatures
- [Pattern — `agent-as-tool-handoff.md`](../patterns/agent-as-tool-handoff.md) — coordinator + specialist recipe
- [Pattern — `agent-as-mcp-server.md`](../patterns/agent-as-mcp-server.md) — agent exposed over MCP
- [Pattern — `workflow-as-agent-nesting.md`](../patterns/workflow-as-agent-nesting.md) — nested workflows
- [Anti-pattern — `missing-async-with-cleanup.md`](missing-async-with-cleanup.md) — general lifecycle hygiene
- [Anti-pattern — `workflow-event-isinstance.md`](workflow-event-isinstance.md) — companion `event.type` guidance for workflow-driven composition
