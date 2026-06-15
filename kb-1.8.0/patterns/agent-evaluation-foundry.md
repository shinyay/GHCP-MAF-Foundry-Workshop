# Pattern: Foundry-Hosted Agent Evaluation (LLM-as-Judge)

> Status: **⚠️ Experimental** (`ExperimentalFeature.EVALS`)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_foundry_evals.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py)
> Runnable category: **Foundry — operationally runnable once env vars supplied**

## Goal

Score agent quality with Foundry's hosted **LLM-as-judge** evaluators — relevance, coherence, groundedness, tool-call accuracy, safety, and more. Designed for production quality measurement, not for unit-test-style gating.

## When to use

| Use this pattern | Use [`agent-evaluation-local.md`](agent-evaluation-local.md) instead |
|------------------|----------------------------------------------------------------------|
| Track quality trends over time (Foundry portal) | CI regression assertion |
| Score open-ended responses (no ground truth) | Tool-call name/argument verification |
| Safety screening (violence / hate / self-harm) | Custom rule (your own scorer fn) |
| Groundedness against retrieval context | Keyword / regex check |

The two patterns **compose** — pass both to one `evaluate_agent` call to get deterministic CI signal plus probabilistic quality signal in one run.

## Prerequisites

| Env var | Required for | Source |
|---------|-------------|--------|
| `FOUNDRY_PROJECT_ENDPOINT` | Auto-creating the inner `FoundryChatClient` when no client passed to `FoundryEvals` | [`_foundry_evals.py:L633-L635`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L633-L635) |
| Azure CLI login (`az login`) | `AzureCliCredential` auth to Foundry | — |
| Foundry project with `builtin.*` evaluators enabled | Foundry-side requirement | [`_foundry_evals.py:560-565`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L560-L565) |

> [!IMPORTANT]
> `FoundryEvals()` does **not** read `FOUNDRY_MODEL`. When `model=` is omitted, it hard-codes the judge model to `"gpt-4o"` ([`_foundry_evals.py:L633-L635`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L633-L635)). Since the workshop default project deploys only `gpt-5-4` (see [`docs/foundry-provisioning.md` § Default environment](../../docs/foundry-provisioning.md)), unconfigured `FoundryEvals()` fails with `DeploymentNotFound`; `gpt-4o` is also deprecated as of 2026-03-31 (`ServiceModelDeprecated`). **Always pass `FoundryEvals(model="gpt-5-4")`** — or use the repo convention `os.environ.get("FOUNDRY_JUDGE_MODEL", "gpt-5-4")` — and hand in a pre-built `FoundryChatClient(model="gpt-5-4")` when you need lifecycle control. The **judge model** can (and should) be different from the agent's model when a second deployment is available — see [Variant: independent judge model](#variant--independent-judge-model). See also [`../anti-patterns/eval-as-test-substitute.md` § 10](../anti-patterns/eval-as-test-substitute.md#10-calling-foundryevals-without-model-judge-fallback-pitfall).

## Code — score an agent with relevance + tool-call accuracy + groundedness

```python
import asyncio
from azure.identity.aio import AzureCliCredential
from agent_framework import evaluate_agent, ConversationSplit
from agent_framework.foundry import FoundryChatClient, FoundryEvals

def search_docs(query: str) -> str:
    """Search internal docs (placeholder for real RAG)."""
    return "Document excerpt about Azure AI Foundry."

async def main() -> None:
    async with AzureCliCredential() as cred, \
            FoundryChatClient(credential=cred).as_agent(
                name="docs-assistant",
                instructions="Answer questions using search_docs results.",
                tools=[search_docs],
            ) as agent:

        evals = FoundryEvals(
            client=FoundryChatClient(credential=cred, model="gpt-5-4"),
            evaluators=[
                FoundryEvals.RELEVANCE,
                FoundryEvals.TOOL_CALL_ACCURACY,
                FoundryEvals.GROUNDEDNESS,
            ],
            conversation_split=ConversationSplit.LAST_TURN,
            timeout=300.0,
        )

        results = await evaluate_agent(
            agent=agent,
            queries=[
                "What is Azure AI Foundry?",
                "How do I deploy a Foundry agent?",
            ],
            context="Azure AI Foundry is Microsoft's unified AI platform...",  # for GROUNDEDNESS
            evaluators=evals,
            num_repetitions=3,
        )

        for r in results:
            print(f"{r.provider}: {r.passed}/{r.total} passed (status={r.status})")
            if r.report_url:
                print(f"  Portal: {r.report_url}")
            for evaluator_name, counts in r.per_evaluator.items():
                print(f"  {evaluator_name}: {counts}")

asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| Separate `FoundryChatClient` for `FoundryEvals` | The judge is independent infrastructure from the agent. Reusing one client works, but a dedicated judge client makes it possible to switch judge models (see variant below) ([`_foundry_evals.py:L619-L646`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L619-L646)) |
| `FoundryEvals.RELEVANCE` (class constant) | IDE autocomplete + typo prevention. All 19 names live as class constants on `FoundryEvals` ([`_foundry_evals.py:L587-L618`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L587-L618)) |
| `GROUNDEDNESS` + `context=` | Groundedness needs the source-of-truth document. Without `context=` the evaluator has nothing to ground against |
| `ConversationSplit.LAST_TURN` | The default — judges only the **last** answer. Use `ConversationSplit.FULL` when trajectory matters (see [Common mistakes](#common-mistakes)) |
| `num_repetitions=3` | LLM-judge scores are probabilistic — averaging 3 independent runs measures consistency. Aggregated across N×Q items in `EvalResults` ([`_evaluation.py:L1505-L1509`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1505-L1509)) |
| `timeout=300.0` | Foundry runs poll until completion. Default 180s is sometimes too short for large batches ([`_foundry_evals.py:L619-L646`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L619-L646)) |
| `r.report_url` | Foundry portal deep-link for human triage of judge outputs |
| `r.per_evaluator` | Pass/fail breakdown per evaluator, not just per item — surfaces "tool_call_accuracy is failing more than relevance" patterns |

## Variant — independent judge model

Use a stronger / cheaper model for the **judge** than the agent uses for production:

```python
evals = FoundryEvals(
    client=FoundryChatClient(credential=cred, model="gpt-5-4"),   # judge
    evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
)

agent = FoundryChatClient(credential=cred, model="gpt-5-4-mini").as_agent(...)   # production
```

Why separate them: judging an agent with the **same** model that produced the answer introduces correlation bias — the judge tends to agree with its own style. See [`../anti-patterns/eval-as-test-substitute.md`](../anti-patterns/eval-as-test-substitute.md).

> [!NOTE]
> The workshop default Foundry project deploys only `gpt-5-4` ([`docs/foundry-provisioning.md` § Default environment](../../docs/foundry-provisioning.md)). To demonstrate this variant end-to-end, provision a second deployment named `gpt-5-4-mini` (`gpt-5.4-mini` model family) alongside the default. Without that, the runnable workshop examples elsewhere on this page intentionally use `gpt-5-4` for **both** agent and judge — runnable simplicity over correlation-bias separation. Production evaluation pipelines should always provision an independent judge model.

## Variant — default evaluators (no `evaluators=`)

```python
evals = FoundryEvals(client=FoundryChatClient(credential=cred, model="gpt-5-4"))
# Defaults to: relevance, coherence, task_adherence
# Auto-adds tool_call_accuracy when items have tools
# (see _foundry_evals.py:L119-L127 + L249-L267)
```

## Variant — compose with `LocalEvaluator`

Combine deterministic CI signal with LLM-judge quality signal in one run:

```python
from agent_framework import LocalEvaluator, keyword_check, tool_called_check

results = await evaluate_agent(
    agent=agent,
    queries=queries,
    evaluators=[
        LocalEvaluator(keyword_check("foundry"), tool_called_check("search_docs")),
        FoundryEvals(client=FoundryChatClient(credential=cred, model="gpt-5-4")),
    ],
)
# Returns one EvalResults per provider — local + foundry
for r in results:
    print(f"{r.provider}: {r.passed}/{r.total}")
```

## Variant — minimal-config from env vars

When `FOUNDRY_PROJECT_ENDPOINT` is set, `FoundryEvals()` builds its own `FoundryChatClient`. **Note the judge model is hard-coded to `"gpt-4o"`** — there is no `FOUNDRY_MODEL` env fallback for the judge. This repo's convention is `FOUNDRY_JUDGE_MODEL` (default `gpt-5-4`); each call site must read it and pass `model=` explicitly:

```python
import os
evals = FoundryEvals(model=os.environ.get("FOUNDRY_JUDGE_MODEL", "gpt-5-4"))   # endpoint from env; judge model explicit
```

Convenient for local exploration; in production prefer the explicit-client form (`FoundryEvals(client=FoundryChatClient(credential=cred, model=...))`) so credential lifetime and judge model choice are both visible ([`_foundry_evals.py:L633-L635`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L633-L635)).

## Verification

Run the script and watch for:

1. `status=completed` (not `failed` / `canceled` / `timeout`)
2. `report_url` populated — click it to inspect the per-item judge reasoning in the Foundry portal
3. `per_evaluator` shows non-zero counts for each evaluator you requested

If `status=timeout`, raise `timeout=` on the `FoundryEvals` constructor. If `status=failed`, inspect `EvalResults.error` for the Foundry-side error message.

## Common mistakes

- **Using the same model for agent and judge.** Correlation bias — the judge agrees with its own outputs. Use a different judge model.
- **Hardcoding `assert passed == total` as a CI gate.** LLM-judge results are probabilistic; one run is not statistically meaningful. Use `num_repetitions > 1` and compare aggregate trends to a baseline.
- **Forgetting `context=` for `GROUNDEDNESS`.** Without source-of-truth context the evaluator has nothing to ground against.
- **Ignoring `ConversationSplit`.** `LAST_TURN` only judges the **last** answer — a multi-turn debugging agent with a wrong tool call three turns ago is invisible. Use `ConversationSplit.FULL` when trajectory matters.
- **Tracking only aggregate scores.** Without retaining per-item `EvalItemResult` data + traces, you cannot diagnose regressions. Always persist `r.items` and the corresponding `AgentResponse`s.

See [`../anti-patterns/eval-as-test-substitute.md`](../anti-patterns/eval-as-test-substitute.md) for the full anti-pattern catalog.

## See also

- API reference: [`../api-reference/1.8.0/evaluation.md`](../api-reference/1.8.0/evaluation.md) (full 19-evaluator catalog)
- Deterministic check pattern: [`agent-evaluation-local.md`](agent-evaluation-local.md)
- Multi-agent: [`workflow-evaluation.md`](workflow-evaluation.md)
- Production trace eval: see [`../api-reference/1.8.0/evaluation.md#evaluate_traces`](../api-reference/1.8.0/evaluation.md#evaluate_traces)
- Observability prerequisite: [`observability-otel.md`](observability-otel.md)

---

**Upstream source:** [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`python/packages/foundry/agent_framework_foundry/_foundry_evals.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py).
