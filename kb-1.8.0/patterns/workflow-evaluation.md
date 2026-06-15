# Pattern: Workflow Evaluation (Per-Agent Breakdown)

> Status: **⚠️ Experimental** (`ExperimentalFeature.EVALS`)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_evaluation.py#L1657-L1724`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1657-L1724)
> Runnable category: **Composes Local + Foundry patterns** — same env-var requirements as the underlying evaluator

## Goal

Evaluate a **multi-agent workflow** so you get both the final overall score **and** a per-sub-agent breakdown — to identify which agent in the pipeline is responsible for a regression.

This page is **narrow and differential**: it covers only what's different from [`agent-evaluation-local.md`](agent-evaluation-local.md) / [`agent-evaluation-foundry.md`](agent-evaluation-foundry.md). Read those first for evaluator setup.

## When to use

| Use this pattern | Use [`agent-evaluation-{local,foundry}.md`](agent-evaluation-foundry.md) instead |
|------------------|----------------------------------------------------------------------------------|
| ≥2 sub-agents wired via `WorkflowBuilder` | Single agent (no workflow) |
| You need **per-agent** pass/fail breakdown | You only care about the final answer |
| You want one call that scores every sub-agent | You're scoring an agent in isolation |

## Prerequisites

Same as the chosen evaluator (`LocalEvaluator` and/or `FoundryEvals`) plus:

- A `Workflow` built with `WorkflowBuilder` containing ≥1 sub-agent (only sub-agents are individually scored — pure function executors are skipped)
- A way to invoke that workflow with a query (`workflow.run(query)`) **or** a captured `WorkflowRunResult` from a previous run

## Code — score every sub-agent + the workflow output

```python
import asyncio
from azure.identity.aio import AzureCliCredential
from agent_framework import WorkflowBuilder, evaluate_workflow
from agent_framework.foundry import FoundryChatClient, FoundryEvals

async def main() -> None:
    async with AzureCliCredential() as cred, \
            FoundryChatClient(credential=cred).as_agent(
                name="researcher",
                instructions="Find relevant facts.",
            ) as researcher, \
            FoundryChatClient(credential=cred).as_agent(
                name="writer",
                instructions="Compose a brief from researcher's facts.",
            ) as writer:

        workflow = (
            WorkflowBuilder(start_executor=researcher)
            .add_edge(researcher, writer)
            .build()
        )

        evals = FoundryEvals(
            client=FoundryChatClient(credential=cred, model="gpt-5-4"),
            evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        )

        results = await evaluate_workflow(
            workflow=workflow,
            queries=["What is Microsoft Agent Framework?"],
            evaluators=evals,
            include_overall=True,
            include_per_agent=True,
        )

        for r in results:
            print(f"{r.provider}: overall {r.passed}/{r.total}")
            for executor_id, sub in r.sub_results.items():
                print(f"  {executor_id}: {sub.passed}/{sub.total}")

asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| `evaluate_workflow(workflow=..., queries=...)` | Run-and-evaluate mode — runs `workflow.run(q)` once per query × `num_repetitions` ([`_evaluation.py:L1724`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1724)) |
| `include_per_agent=True` (default) | Populates `r.sub_results[<executor_id>]` with one `EvalResults` per sub-agent executor. Set `False` to skip the per-agent pass when you only want the overall score |
| `include_overall=True` (default) | Evaluates the workflow's final output as a separate item. Set `False` to skip and only score sub-agents individually. **Setting both `include_overall=False` AND `include_per_agent=False` raises `ValueError`** at [`_evaluation.py:L1796-L1799`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1796-L1799) because nothing is left to evaluate |
| `r.sub_results` | `dict[str, EvalResults]` keyed by **executor ID** populated from `WorkflowRunResult` events at [`_evaluation.py:L1813-L1818`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1813-L1818). When agents are added directly via `add_edge(agent, ...)`, the builder wraps each agent in an `AgentExecutor` and the executor ID defaults to `agent.name` (falling back to `agent.id` if name is empty) via `resolve_agent_id()` at [`_workflows/_agent_utils.py:L6-L17`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_agent_utils.py#L6-L17). So `r.sub_results["researcher"]` works in this example. If you wrap manually (`AgentExecutor(agent, id="custom")`), that `id=` becomes the key |
| No `agent=` kwarg | Unlike `evaluate_agent`, `evaluate_workflow` doesn't need an agent — sub-agents are discovered by walking the workflow graph |

## Variant — post-hoc evaluation of a captured run

When the workflow ran in production and you want to score it later without re-running:

```python
result = await workflow.run("What is Microsoft Agent Framework?")
# ... later, or in a different process ...
eval_results = await evaluate_workflow(
    workflow=workflow,
    workflow_result=result,
    evaluators=evals,
)
```

`num_repetitions` is silently ignored in this mode — the captured `WorkflowRunResult` is scored as-is ([`_evaluation.py:L1698-L1700`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1698-L1700)).

## Variant — ground-truth comparison with `expected_output`

```python
eval_results = await evaluate_workflow(
    workflow=workflow,
    queries=["What year was Azure released?"],
    expected_output=["Azure was released in 2010."],
    evaluators=evals,
)
```

`expected_output` is stamped on each `EvalItem.expected_output` for evaluators that compare against a reference (e.g. `FoundryEvals.SIMILARITY`). Must be the same length as `queries`; **not supported with `workflow_result`** ([`_evaluation.py:L1735-L1741`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1735-L1741)).

## Variant — per-agent only (skip overall)

```python
eval_results = await evaluate_workflow(
    workflow=workflow,
    queries=queries,
    evaluators=evals,
    include_overall=False,        # don't score final output
    include_per_agent=True,
)
```

Useful when sub-agents have very different jobs (e.g. retrieval vs synthesis) and an "overall" score blends signals you'd rather track separately.

## Verification

The output should show:

```
Microsoft Foundry: overall 1/1
  researcher: 2/2
  writer: 2/2
```

- `r.provider` — `"Microsoft Foundry"` for `FoundryEvals` ([`_foundry_evals.py:L631-L632`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L631-L632)); `"Local"` for `LocalEvaluator`
- `r.passed / r.total` — overall pass count (when `include_overall=True`); note `total = passed + failed` only — check `result_counts.get("errored", 0)` separately
- `r.sub_results` — non-empty dict when `include_per_agent=True`, keyed by **executor ID** (defaults to `agent.name` when agents are added via `add_edge` — see "Why each piece" above)
- Each `sub.items` — one item per query × repetition

## Common mistakes

- **Forgetting to materialize agents** before passing them to `WorkflowBuilder` — the builder requires agent instances ([`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md))
- **Setting `include_overall=False` and `include_per_agent=False`** — raises `ValueError` because nothing remains to evaluate ([`_evaluation.py:L1796-L1799`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1796-L1799))
- **Anonymous / duplicate agent `name`s** — when agents are passed directly to `add_edge`, the builder uses `agent.name` (or `agent.id`) as the executor ID via `resolve_agent_id()`. Two agents sharing the same name raise `ValueError("Duplicate executor ID ...")` at [`_workflows/_workflow_builder.py:L215-L219`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow_builder.py#L215-L219). Give every agent a unique meaningful `name=`
- **Treating overall pass-rate as a workflow-quality score when sub-agents have wildly different jobs** — prefer per-agent tracking; reserve the overall score for end-to-end gating
- **Asserting `passed == total` as a CI gate with LLM-judge evaluators** — see [`../anti-patterns/eval-as-test-substitute.md`](../anti-patterns/eval-as-test-substitute.md)

## See also

- API reference: [`../api-reference/1.8.0/evaluation.md`](../api-reference/1.8.0/evaluation.md) (full evaluator catalog)
- Workflows API: [`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md)
- Workflow internals: [`../api-reference/1.8.0/workflow-internals.md`](../api-reference/1.8.0/workflow-internals.md)
- Single-agent local: [`agent-evaluation-local.md`](agent-evaluation-local.md)
- Single-agent foundry: [`agent-evaluation-foundry.md`](agent-evaluation-foundry.md)
- Anti-patterns: [`../anti-patterns/eval-as-test-substitute.md`](../anti-patterns/eval-as-test-substitute.md)

---

**Upstream source:** [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`python/packages/core/agent_framework/_evaluation.py#L1657-L1724`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1657-L1724).
