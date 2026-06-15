# Pattern — Declarative workflow from YAML (BETA)

> [!WARNING]
> Uses `agent-framework-declarative==1.0.0b260528` (Beta). Pin the exact version. See [`declarative.md`](../api-reference/1.8.0/declarative.md) for the full API surface and the [action kind catalog](../api-reference/1.8.0/declarative.md#action-kind-catalog-34-total) (34 kinds).

## Goal

Author a multi-step workflow (variables, branches, agent invocations, HTTP calls, HITL pauses) in YAML and execute it with the same `Workflow.run(...)` runtime that powers code-defined workflows.

## When to use

- The workflow shape is **data**, not code — owned by domain experts, edited without touching Python.
- You want to ship workflows where the YAML is the canonical source of truth (the Python loader is the runtime).
- You want to compose pre-built Python agents (`SelfServiceAgent`, `TicketingAgent`, etc.) with declarative branching/looping/HITL on top.

## When *not* to use

- Single-shot deterministic logic — `WorkflowBuilder` in Python is more direct.
- Dynamic graph shape (number of edges depends on runtime state) — YAML is static, build the graph imperatively.
- The control flow you need isn't expressible in the 34 supported kinds — extending the catalog requires patching `agent-framework-declarative`.

## Prerequisites

```bash
pip install 'agent-framework-foundry==1.8.0' 'agent-framework-declarative==1.0.0b260528'
az login
```

`.env`:

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com/api/projects/<project-name>
FOUNDRY_MODEL=gpt-5-4
```

---

## Code — minimal workflow

Save as `workflow.yaml`:

```yaml
name: simple-greeting-workflow
description: A simple workflow that greets the user

actions:
  - kind: SetValue
    id: set_greeting
    path: Local.greeting
    value: Hello

  - kind: SetValue
    id: set_name
    path: Local.name
    value: =If(IsBlank(inputs.name), "World", inputs.name)

  - kind: SetValue
    id: build_message
    path: Local.message
    value: =Concat(Local.greeting, ", ", Local.name, "!")

  - kind: SendActivity
    id: send_greeting
    activity:
      text: =Local.message

  - kind: SetValue
    id: set_output
    path: Workflow.Outputs.greeting
    value: =Local.message
```

Run it:

```python
import asyncio
from pathlib import Path
from agent_framework.declarative import WorkflowFactory


async def main() -> None:
    factory = WorkflowFactory()
    workflow = factory.create_workflow_from_yaml_path(
        Path(__file__).parent / "workflow.yaml"
    )

    result = await workflow.run({"name": "Alice"})

    # get_outputs() returns values yielded via ctx.yield_output(...).
    # SendActivity calls yield_output internally (_executors_basic.py:L277),
    # so the "Hello, Alice!" text emitted above appears here.
    # Note: SetValue → Workflow.Outputs.x writes to workflow state but is
    # NOT auto-surfaced in get_outputs() — see pitfall #7.
    for output in result.get_outputs():
        print(f"Output: {output}")  # -> "Hello, Alice!"


if __name__ == "__main__":
    asyncio.run(main())
```

### Why this works

- `actions:` is a top-level list (alternative form: wrap in `kind: Workflow` + `trigger:` block as in the [`customer_support`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/samples/03-workflows/declarative/customer_support) sample).
- `=If(IsBlank(inputs.name), "World", inputs.name)` uses PowerFx — `inputs.*` is the [backward-compat alias for `Workflow.Inputs.*`](../api-reference/1.8.0/declarative.md#workflow-state-scopes).
- `result.get_outputs()` returns values from `ctx.yield_output(...)` calls ([`_workflow.py:L125-L131`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L125-L131)). `SendActivity` calls `yield_output` internally, so its text is surfaced. `SetValue → Workflow.Outputs.greeting` is the cross-runtime declarative convention for "final" values, but in Python 1.8.0 you still need a `SendActivity` to make it visible in `get_outputs()` (1.6.0 also had `EmitEvent`, [removed in 1.8.0 PR #6126](https://github.com/microsoft/agent-framework/pull/6126)). See [pitfall #7](../anti-patterns/declarative-pitfalls.md#7-confusing-state-write-with-output-emit).
- The compiled `Workflow` is identical in shape to one you'd write with `WorkflowBuilder` — same `Executor` graph, same `WorkflowEvent` semantics ([`workflow-internals.md`](../api-reference/1.8.0/workflow-internals.md)).

---

## Variant — control flow (`If` / `ConditionGroup` / `Foreach` / `GotoAction`)

Built-in branching uses `If` + `then` + `else`:

```yaml
- kind: If
  id: check_age
  condition: =Local.age < 18
  then:
    - kind: SetValue
      path: Local.category
      value: minor
  else:
    - kind: SetValue
      path: Local.category
      value: adult
```

For first-match dispatch across many cases, use `ConditionGroup` (used heavily in the [`customer_support`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/03-workflows/declarative/customer_support/workflow.yaml) sample):

```yaml
- kind: ConditionGroup
  id: check_state
  conditions:
    - condition: =Local.resolved
      actions:
        - kind: GotoAction
          actionId: end_when_resolved
    - condition: =Local.needs_escalation
      actions:
        - kind: GotoAction
          actionId: escalate
```

> [!IMPORTANT]
> `GotoAction` is the only jump action in 1.7+ ([catalog](../api-reference/1.8.0/declarative.md#builder-only-control-constructs-6); the alias `Goto` was [removed in 1.8.0 PR #6126](https://github.com/microsoft/agent-framework/pull/6126)). Cycles are allowed and useful for loops like DeepResearch; raise `WorkflowFactory(max_iterations=...)` if the default 100-superstep cap is too low.

---

## Variant — invoking pre-registered agents

Register Python-defined agents on the factory, then call them from YAML via `InvokeAzureAgent` (despite the name, **any** provider works — see the note in [`declarative.md`](../api-reference/1.8.0/declarative.md#workflowfactory--yaml--workflow)):

```python
from agent_framework.foundry import FoundryChatClient
from agent_framework.declarative import WorkflowFactory
from azure.identity.aio import AzureCliCredential


async def main() -> None:
    async with AzureCliCredential() as cred:
        client = FoundryChatClient(credential=cred)

        agents = {
            "ResearchAgent": client.as_agent(
                name="ResearchAgent",
                instructions="Research the user's question with citations.",
            ),
            "WriterAgent": client.as_agent(
                name="WriterAgent",
                instructions="Write a polished answer using the research.",
            ),
        }

        factory = WorkflowFactory(agents=agents)
        workflow = factory.create_workflow_from_yaml_path("workflow.yaml")

        result = await workflow.run({"question": "What is RAG?"})
        for output in result.get_outputs():
            print(output)
```

```yaml
# workflow.yaml (excerpt)
actions:
  - kind: InvokeAzureAgent
    id: research
    agent:
      name: ResearchAgent           # must match a key in WorkflowFactory(agents=...)
    input:
      messages: =UserMessage(inputs.question)
    output:
      responseObject: Local.research

  - kind: InvokeAzureAgent
    id: write
    agent:
      name: WriterAgent
    input:
      messages: '=UserMessage(Concat("Based on this research, answer: ", Local.research))'
    output:
      responseObject: Local.answer

  - kind: SetValue
    path: Workflow.Outputs.final
    value: =Local.answer
```

> [!IMPORTANT]
> If YAML references `agent.name: ResearchAgent` but `WorkflowFactory(agents=...)` doesn't contain that key, the build fails at runtime when the action executes (not at `create_workflow_from_yaml_path` time). Always register every agent name your YAML uses, or fail-fast with a smoke test. See [pitfall #5](../anti-patterns/declarative-pitfalls.md#5-invokeazureagent-with-no-registered-agent).

Alternatively, use the fluent registration form:

```python
factory = (
    WorkflowFactory()
    .register_agent("ResearchAgent", research_agent)
    .register_agent("WriterAgent", writer_agent)
)
```

---

## Variant — checkpoint storage (pause/resume)

Pass `checkpoint_storage` to enable durable pause/resume across process restarts:

```python
from agent_framework import FileCheckpointStorage
from agent_framework.declarative import WorkflowFactory

factory = WorkflowFactory(
    checkpoint_storage=FileCheckpointStorage("./checkpoints"),
)
```

See [`workflow-checkpointing.md`](workflow-checkpointing.md) for the resume mechanics — they're identical for declarative and code-defined workflows.

---

## Human-in-the-loop (HITL)

The 2 HITL action kinds are `Question`, `RequestExternalInput` ([catalog](../api-reference/1.8.0/declarative.md#external-input--human-in-the-loop-2); `Confirmation` and `WaitForInput` were [removed in 1.8.0 PR #6126](https://github.com/microsoft/agent-framework/pull/6126)). Both pause the workflow at `ctx.request_info(...)` and surface a `WorkflowEvent` with `event.type == "request_info"`. The caller resumes with `workflow.run(responses={request_id: ExternalInputResponse(...)})`.

### YAML — verified keys (per executor source)

`Question` action keys read by [`_executors_external_input.py:L70-L105`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_external_input.py#L70-L105):

- `text:` (scalar) **or** `question:` (scalar) — the prompt
- `output.property:` (nested) **or** `property:` (top-level) — where to store the answer; default `Local.answer`
- `defaultValue:` — used if response is missing (note: **not** `default:`)
- `choices:` — optional list of `{value, label}` (or plain scalars)
- `allowFreeText:` — `True`/`False`; default `True`

`RequestExternalInput` action keys read by [`_executors_external_input.py:L285-L320`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_external_input.py#L285-L320):

- `message:` (scalar) — the prompt (note: **not** `prompt.text`)
- `output.property:` **or** `property:` — storage; default `Local.externalInput`
- `requestType:` — discriminator; default `"external"`
- `timeout:`, `requiredFields:`, `metadata:` — optional

> [!WARNING]
> The upstream sample at [`samples/03-workflows/declarative/human_in_loop/workflow.yaml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/03-workflows/declarative/human_in_loop/workflow.yaml) uses different keys (`question.text`, `variable`, `default`, `prompt.text`) which the Python executor does **not** read. The form below matches the executor — verify yourself before using sample-style YAML in production.

```yaml
actions:
  - kind: Question
    id: ask_name
    text: "What is your name?"
    output:
      property: Local.userName
    defaultValue: "Demo User"

  - kind: SendActivity
    activity:
      text: =Concat("Nice to meet you, ", Local.userName, "!")

  - kind: RequestExternalInput
    id: ask_feedback
    message: "Any feedback?"
    output:
      property: Local.feedback

  - kind: SetValue
    path: Workflow.Outputs.summary
    value:
      name: =Local.userName
      feedback: =Local.feedback

  - kind: SendActivity            # surfaces Workflow.Outputs.summary into get_outputs()
    activity:
      text: =Concat("Summary stored for ", Local.userName)
```

### Runner — handling `request_info` events + resuming

```python
import asyncio
from pathlib import Path
from typing import cast

from agent_framework import Workflow
from agent_framework.declarative import (
    ExternalInputRequest,
    ExternalInputResponse,
    WorkflowFactory,
)


async def run_with_hitl(workflow: Workflow, initial: dict[str, object]) -> None:
    """Run a HITL workflow, simulating user responses inline."""
    pending: dict[str, ExternalInputResponse] = {}
    inputs: dict[str, object] | None = initial
    responses: dict[str, ExternalInputResponse] | None = None

    while True:
        any_request = False
        async for event in workflow.run(inputs, stream=True, responses=responses):
            if event.type == "output":
                print(f"[Bot]: {event.data}")
            elif event.type == "request_info":
                req = cast(ExternalInputRequest, event.data)
                any_request = True
                # In production: render req.message to a UI, await user input.
                # Here we simulate.
                pending[req.request_id] = ExternalInputResponse(value="Alice")
        if not any_request:
            break
        inputs, responses = None, pending
        pending = {}


async def main() -> None:
    factory = WorkflowFactory()
    workflow = factory.create_workflow_from_yaml_path(
        Path(__file__).parent / "workflow.yaml"
    )
    await run_with_hitl(workflow, {})


if __name__ == "__main__":
    asyncio.run(main())
```

> [!IMPORTANT]
> Discriminate workflow events on `event.type` (string), **not** `isinstance(event, ...)`. The string discriminators are stable across `1.5+`; the class hierarchy is not. See [`workflow-event-isinstance.md`](../anti-patterns/workflow-event-isinstance.md).

Resume API reference: [`_workflow.py:L247-L255`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L247-L255) — pass `responses={request_id: response_object}` to the SAME `workflow.run(...)` call (NOT a separate `send_response` method).

The full HITL/approval type catalog (`ExternalInputRequest/Response`, `AgentExternalInputRequest/Response`, `ToolApprovalRequest/Response`, `MCPToolApprovalRequest`) is in [`declarative.md`](../api-reference/1.8.0/declarative.md#approval--external-input-types). Combined with `checkpoint_storage`, HITL works across process restarts.

---

## Variant — HTTP and MCP actions

`HttpRequestAction` and `InvokeMcpTool` both require explicit handlers — build fails with `DeclarativeWorkflowError` if you forget:

```python
from agent_framework.declarative import (
    DefaultHttpRequestHandler,
    DefaultMCPToolHandler,
    WorkflowFactory,
)

factory = WorkflowFactory(
    http_request_handler=DefaultHttpRequestHandler(),   # ⚠️ no SSRF guard — dev only
    mcp_tool_handler=DefaultMCPToolHandler(),           # ⚠️ same — dev only
)
```

> [!WARNING]
> The `Default*` handlers apply **no allow-list, no auth resolution, and no SSRF guards** ([source: `_http_handler.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_http_handler.py)). Any URL the YAML names is fetched. For production, supply a custom `HttpRequestHandler` / `MCPToolHandler` with allow-list enforcement. See [pitfall #6](../anti-patterns/declarative-pitfalls.md#6-default-handlers-are-ssrf-unsafe).

---

## Verification

```bash
python3 -c "
from agent_framework.declarative import WorkflowFactory, DeclarativeWorkflowError
try:
    WorkflowFactory().create_workflow_from_yaml_path('workflow.yaml')
    print('YAML loads OK')
except DeclarativeWorkflowError as e:
    print(f'Build failed: {e}')
"
```

Watch the `agent_framework.declarative` logger for `WARNING` messages — unknown `kind:` values are skipped silently otherwise. See [pitfall #2](../anti-patterns/declarative-pitfalls.md#2-unknown-kind-silently-skipped).

```python
import logging
logging.getLogger("agent_framework.declarative").setLevel(logging.WARNING)
```

---

## Common mistakes

| Mistake | Fix |
|---|---|
| Output value missing from `get_outputs()` | Make sure the final write goes to `Workflow.Outputs.*`, not `Local.*` |
| `InvokeAzureAgent` does nothing / `KeyError` | The agent name in YAML must match a key in `WorkflowFactory(agents={...})` |
| `HttpRequestAction` build error | Pass `http_request_handler=...`; defaults are dev-only |
| Workflow exits before HITL pause | Check the caller is using `stream=True` and reacting to `event.type == "request_info"` |
| `=Local.x == 1` always false | PowerFx uses single `=` for equality, not `==` |
| Typo in `kind:` (e.g. `SetVarible`) | Silently skipped — enable WARNING-level logging on `agent_framework.declarative` |

See [`declarative-pitfalls.md`](../anti-patterns/declarative-pitfalls.md) for the full anti-pattern catalog.

---

## See also

- [API ref — `declarative.md`](../api-reference/1.8.0/declarative.md) — `WorkflowFactory` + action catalog + scopes
- [Pattern — `declarative-agent.md`](declarative-agent.md) — agent companion
- [Pattern — `workflow-checkpointing.md`](workflow-checkpointing.md) — pause/resume mechanics
- [Pattern — `multi-agent-workflow.md`](multi-agent-workflow.md) — equivalent imperative pattern
- [Anti-pattern — `declarative-pitfalls.md`](../anti-patterns/declarative-pitfalls.md)
- [API ref — `workflow-internals.md`](../api-reference/1.8.0/workflow-internals.md) — `Executor` graph internals (declarative compiles to this)
- Upstream samples: [`simple_workflow`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/samples/03-workflows/declarative/simple_workflow), [`human_in_loop`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/samples/03-workflows/declarative/human_in_loop), [`customer_support`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/samples/03-workflows/declarative/customer_support)
