# Pattern: Local Agent Evaluation (Zero-Cost Deterministic Checks)

> Status: **⚠️ Experimental** (`ExperimentalFeature.EVALS`)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_evaluation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py)
> Runnable category: **Local checks — fully runnable without Azure when you pre-supply responses.** The main example below drives a live `FoundryChatClient` agent (so it needs `FOUNDRY_PROJECT_ENDPOINT` + `FOUNDRY_MODEL` + `az login`). See the "score pre-existing responses" variant below for the fully no-Azure path: it requires only the `agent-framework-foundry` install and replays `AgentResponse` objects you already captured.

## Goal

Score agent behavior with **deterministic, in-process checks** — no LLM judge, no Foundry, no API costs. The fastest possible feedback loop for "did the agent call the right tool" / "did the response mention the keyword" / "did my custom rule fire".

## When to use

| Use this pattern | Use [`agent-evaluation-foundry.md`](agent-evaluation-foundry.md) instead |
|------------------|--------------------------------------------------------------------------|
| Regression test in CI / `pytest` | Production quality scoring |
| Tool-call correctness check | LLM-judged relevance / coherence / groundedness |
| Keyword / regex / length assertion | Safety scoring (violence / hate / self-harm) |
| Custom rule (your own scorer fn) | Tracking quality trends over time in Foundry portal |

The two patterns **compose** — pass both `LocalEvaluator` and `FoundryEvals` to a single `evaluate_agent` call to get both signals from one run.

## Prerequisites

- `agent-framework-foundry==1.8.0` installed
- Either an agent you can actually run (then `FOUNDRY_PROJECT_ENDPOINT` + `FOUNDRY_MODEL` + `az login`) **or** pre-existing `AgentResponse`s to score (no Azure required)

## Code — three deterministic checks against one agent

```python
import asyncio
from azure.identity.aio import AzureCliCredential
from agent_framework import (
    LocalEvaluator,
    evaluate_agent,
    keyword_check,
    tool_called_check,
    evaluator,
)
from agent_framework.foundry import FoundryChatClient

def get_weather(location: str) -> str:
    """Return the current weather for a location."""
    return f"Sunny in {location}"

@evaluator
def is_concise(response: str) -> bool:
    """Custom rule: weather replies should be short."""
    return len(response) < 200

async def main() -> None:
    async with AzureCliCredential() as cred, \
            FoundryChatClient(credential=cred).as_agent(
                name="weather-bot",
                instructions="Answer weather questions using get_weather.",
                tools=[get_weather],
            ) as agent:

        local = LocalEvaluator(
            keyword_check("weather"),
            tool_called_check("get_weather"),
            is_concise,
        )

        results = await evaluate_agent(
            agent=agent,
            queries=[
                "What's the weather in Tokyo?",
                "How's the weather in Paris today?",
            ],
            evaluators=local,
        )

        for r in results:
            print(f"{r.provider}: {r.passed}/{r.total} passed")
            for item in r.items:
                print(f"  item {item.item_id}: {item.status}")
                for score in item.scores:
                    print(f"    {score.name}: {'✅' if score.passed else '❌'}")

asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| `keyword_check("weather")` | Asserts the response actually contains the word "weather" — defends against tool-skipping ([`_evaluation.py:L886-L911`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L886-L911)) |
| `tool_called_check("get_weather")` | Asserts the agent **actually called** the tool, not just hallucinated an answer ([`_evaluation.py:L915-L991`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L915-L991)) |
| `@evaluator` on `is_concise` | Wraps a plain function as an `EvalCheck`. Parameter names (`response`) determine what's injected ([`_evaluation.py:L1240-L1341`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1240-L1341)) |
| `LocalEvaluator(*checks)` | Aggregates all three checks. An item passes only when **all** checks pass for it ([`_evaluation.py:L1402-L1411`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1402-L1411)) |
| `async with ... .as_agent(...)` | Ensures the agent's chat client and credential are cleaned up — without this you'll see `Unclosed connector` warnings (see [`../anti-patterns/missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md)) |
| `evaluators=local` (not `evaluators=[local]`) | `evaluate_agent` accepts a single `Evaluator` or a sequence — both are fine ([`_evaluation.py:L1459`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1459)) |

## Variant — score pre-existing responses (no agent run)

If you already have `AgentResponse`s — replayed from logs, captured in a previous test run — skip the agent invocation:

```python
results = await evaluate_agent(
    agent=agent,                       # still needed to extract tool definitions
    responses=cached_responses,        # pre-existing; no re-run
    queries=original_queries,          # required to construct conversation
    evaluators=local,
)
```

`num_repetitions` is silently ignored in this mode — the existing responses are scored as-is ([`_evaluation.py:L1505-L1509`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1505-L1509)).

## Variant — assert expected tool calls with arguments

For tool argument correctness, use the data-driven checks:

```python
from agent_framework import ExpectedToolCall, tool_call_args_match

results = await evaluate_agent(
    agent=agent,
    queries=["What's the weather in Tokyo?"],
    expected_tool_calls=[ExpectedToolCall("get_weather", {"location": "Tokyo"})],
    evaluators=LocalEvaluator(tool_call_args_match),
)
```

`tool_call_args_match` reads `item.expected_tool_calls` and verifies the agent called each expected tool by name, with **every expected argument key/value present in the actual call** ([`_evaluation.py:L1042-L1085`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1042-L1085)) — extra arguments on the actual call are **not** a failure (subset match). For unordered name-only checks, use `tool_calls_present` instead. If you need strict-equality argument matching, write a custom `@evaluator` that compares the dicts directly.

## Variant — custom async check with external scorer

```python
from agent_framework import evaluator

@evaluator(name="external_relevance")
async def external_relevance(query: str, response: str) -> float:
    score = await my_external_judge.score(query, response)
    return score   # float ≥ 0.5 is treated as pass
```

Return types accepted by `@evaluator`: `bool`, `float` (≥ 0.5 = pass), `dict` with `score`/`passed`, or `CheckResult` ([`_evaluation.py:L1257-L1262`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1257-L1262)).

## Verification

Run the script:

```bash
python local_eval.py
```

You should see one `EvalResults` per provider, with `passed/total` and per-item, per-check breakdowns.

To verify the imports against the pinned version:

```bash
python -c "
from agent_framework import (
    LocalEvaluator, evaluate_agent, keyword_check,
    tool_called_check, tool_calls_present, tool_call_args_match,
    ExpectedToolCall, evaluator, CheckResult,
)
print('all eval imports resolve ✅')
"
```

## Common mistakes

- **Treating LocalEvaluator results as production quality signal.** It only knows the rules you wrote. For "is the answer actually good?" use `FoundryEvals` ([`agent-evaluation-foundry.md`](agent-evaluation-foundry.md)).
- **Mixing pass-rates of deterministic checks with LLM-judge scores in one number.** See [`../anti-patterns/eval-as-test-substitute.md`](../anti-patterns/eval-as-test-substitute.md).
- **Skipping `async with`** on the credential / agent — your test will pass but leak connections.
- **Asserting `passed == total`** as a unit-test gate when one of your checks is an async LLM call — that's no longer deterministic, treat it like a Foundry score.

## See also

- API reference: [`../api-reference/1.8.0/evaluation.md`](../api-reference/1.8.0/evaluation.md)
- Production scoring: [`agent-evaluation-foundry.md`](agent-evaluation-foundry.md)
- Multi-agent: [`workflow-evaluation.md`](workflow-evaluation.md)
- Anti-patterns: [`../anti-patterns/eval-as-test-substitute.md`](../anti-patterns/eval-as-test-substitute.md)

---

**Upstream source:** [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`python/packages/core/agent_framework/_evaluation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py).
