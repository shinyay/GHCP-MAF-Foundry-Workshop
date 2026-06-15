# Anti-Pattern: Treating EVALS as a Test Substitute

> Status: **⚠️ Experimental** subsystem (`ExperimentalFeature.EVALS`)
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0)

> [!IMPORTANT]
> Every API referenced on this page (`evaluate_agent`, `FoundryEvals`, `LocalEvaluator`, `@evaluator`, the built-in checks) is decorated `@experimental(feature_id=ExperimentalFeature.EVALS)`. Surface may change between minor releases. See [`../api-reference/1.8.0/feature-stages.md`](../api-reference/1.8.0/feature-stages.md) for the full warning model and how to silence/track `[EVALS] ... ExperimentalWarning`, and [`../api-reference/1.8.0/evaluation.md`](../api-reference/1.8.0/evaluation.md) for the canonical surface.

**Symptom (umbrella):** A team adopts `evaluate_agent` / `FoundryEvals` and starts treating the resulting scores as unit-test assertions: `assert results[0].passed == results[0].total`. CI goes green, scores trend down silently in production, regressions show up only as customer complaints.

The Agent Framework EVALS subsystem is built for **probabilistic quality measurement over time**, not deterministic correctness gating. Confusing the two has ten recurring failure modes — each shown below with a wrong example, why it's wrong, the right approach, and how to detect it in code review.

---

## 1. Hardcoded pass-threshold as a CI gate on LLM-judge results

### ❌ Wrong

```python
results = await evaluate_agent(agent=agent, queries=queries, evaluators=foundry_evals)
assert results[0].passed == results[0].total, "regression!"   # blocks every PR
```

### Why it's wrong

LLM-judge results are inherently probabilistic. A single run is not statistically meaningful — a `RELEVANCE` evaluator can score the same item differently across runs. Treating one run as a hard gate produces flaky CI and trains the team to retry failed pipelines instead of investigating.

### ✅ Right

```python
results = await evaluate_agent(
    agent=agent, queries=queries,
    evaluators=foundry_evals,
    num_repetitions=5,
)
pass_rate = results[0].passed / results[0].total
assert pass_rate >= BASELINE * 0.95, f"regression: {pass_rate:.2f} < {BASELINE * 0.95:.2f}"
```

Use a rolling **baseline** and compare aggregate trends, not single-run absolutes. Persist the baseline in `tests/.eval-baseline.json` and update intentionally.

### How to detect

```bash
grep -rn "assert .* \.passed == .* \.total" tests/
grep -rn "evaluators=.*FoundryEvals" tests/ | xargs grep -l "num_repetitions=1"
```

---

## 2. Same model for agent and judge

### ❌ Wrong

```python
agent = FoundryChatClient(credential=cred, model="gpt-5-4").as_agent(...)
evals = FoundryEvals(client=FoundryChatClient(credential=cred, model="gpt-5-4"))
```

### Why it's wrong

The judge model is biased toward its own outputs — a phenomenon documented in LLM-as-judge research as **self-preference / correlation bias**. The judge will rate the agent's responses higher simply because they share stylistic conventions, hallucinated facts, and reasoning patterns. The score tells you the model agrees with itself, not that the answer is correct.

### ✅ Right

```python
agent = FoundryChatClient(credential=cred, model="gpt-5-4-mini").as_agent(...)   # production
evals = FoundryEvals(client=FoundryChatClient(credential=cred, model="gpt-5-4"))   # judge
```

Pick a judge model from a different family or a higher tier than the production model. Document the choice in the eval setup. The workshop default deploys only `gpt-5-4`; to demonstrate this anti-pattern's fix end-to-end, provision a second deployment named `gpt-5-4-mini` (`gpt-5.4-mini` model family) — see [`docs/foundry-provisioning.md` § Default environment](../../docs/foundry-provisioning.md).

### How to detect

Code review checklist: do `agent`'s `model=` and `FoundryEvals`'s `client`'s `model=` match? Flag as comment-only finding (not auto-rejectable; sometimes intentional during exploration).

---

## 3. `num_repetitions=1` for non-determinism judgment

### ❌ Wrong

```python
results = await evaluate_agent(
    agent=agent, queries=queries,
    evaluators=foundry_evals,
    num_repetitions=1,   # default
)
print(f"Quality: {results[0].passed / results[0].total:.2%}")
```

### Why it's wrong

Both the agent and the LLM judge are stochastic. With `num_repetitions=1` you have a sample size of **1 per query**. A score that came back at 0.7 today could be 0.5 or 0.9 tomorrow purely from sampling variance.

### ✅ Right

```python
results = await evaluate_agent(
    agent=agent, queries=queries,
    evaluators=foundry_evals,
    num_repetitions=5,
)
```

Verified in [`_evaluation.py:L1505-L1509`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1505-L1509): when `num_repetitions=N`, each query is run N times independently and all N×Q items are aggregated. For non-trivial gates, `N ≥ 5`. For exploration / debugging, `N = 1` is fine.

### How to detect

```bash
grep -rn "evaluate_agent\|evaluate_workflow" --include="*.py" | grep -v test_ | xargs grep -L "num_repetitions"
```

(Files that call `evaluate_*` and never mention `num_repetitions` are using the default of 1.)

---

## 4. Over-specifying `expected_output` on generative tasks

### ❌ Wrong

```python
# evaluate_agent supports expected_output for each query
results = await evaluate_agent(
    agent=agent,
    queries=["Summarize the Q3 financial report."],
    expected_output=["Q3 revenue was $45.2M, up 12% YoY, driven by cloud services growth."],
    evaluators=FoundryEvals(client=judge_client, evaluators=[FoundryEvals.SIMILARITY]),
)
```

### Why it's wrong

For open-ended generative tasks the "expected" string is just one of many valid answers. Comparison evaluators like `FoundryEvals.SIMILARITY` will down-rank perfectly correct responses that phrase the same fact differently. You end up testing the agent against your phrasing preference, not against correctness.

### ✅ Right — pick the evaluator that matches the question

```python
from agent_framework import (
    ExpectedToolCall, LocalEvaluator, evaluate_agent, tool_call_args_match,
)
from agent_framework.foundry import FoundryChatClient, FoundryEvals

# For "is the answer relevant and well-formed?":
relevance_evals = FoundryEvals(
    client=FoundryChatClient(credential=cred, model="gpt-5-4"),
    evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
)

# For "is the answer grounded in the source document?":
grounded_evals = FoundryEvals(
    client=FoundryChatClient(credential=cred, model="gpt-5-4"),
    evaluators=[FoundryEvals.GROUNDEDNESS],
)
# Build EvalItem(conversation=..., context=<source-doc>) when going lower-level,
# or stamp context on agent responses before calling evaluate_agent.

# For "did the agent take the right action?":
action_evals = LocalEvaluator(tool_call_args_match)
# With ExpectedToolCall, not expected_output:
results = await evaluate_agent(
    agent=agent,
    queries=["Refund order 42"],
    expected_tool_calls=[[ExpectedToolCall("refund_order", {"order_id": 42})]],
    evaluators=action_evals,
)
```

Reserve `expected_output` for tasks with a true single answer (extraction, classification, math). The `FoundryEvals.*` names are **string constants**, not `Evaluator` instances — they must always be passed inside `FoundryEvals(evaluators=[...])`. Passing them directly to `evaluate_agent(evaluators=[...])` raises `TypeError` from `_resolve_evaluators` at [`_evaluation.py:L1880-L1909`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1880-L1909).

### How to detect

```bash
grep -rn "expected_output=" --include="*.py" | grep -v "extract\|classify\|score"
```

Manual review: does the task have a single right answer? If not, this is the wrong evaluator strategy.

---

## 5. Mixing deterministic and LLM-judge results in one score

### ❌ Wrong

```python
results = await evaluate_agent(
    agent=agent, queries=queries,
    evaluators=[
        LocalEvaluator(keyword_check("required")),
        FoundryEvals(client=...),
    ],
)
total_pass = sum(r.passed for r in results)
total = sum(r.total for r in results)
print(f"Score: {total_pass / total:.2%}")   # nonsense blended score
```

### Why it's wrong

`keyword_check` PASS means a string contains a substring — 100% confidence. `RELEVANCE` PASS means an LLM thought it was relevant this time — probabilistic. Summing them treats both signals as equivalent confidence units, masking which kind of failure is happening.

### ✅ Right

```python
results = await evaluate_agent(...)
for r in results:
    # provider names: "Local" (LocalEvaluator), "Microsoft Foundry" (FoundryEvals)
    kind = "deterministic" if r.provider.lower().startswith("local") else "llm-judge"
    print(f"[{kind}] {r.provider}: {r.passed}/{r.total}")
```

Report and gate on each provider's score separately. `LocalEvaluator` results can be hard CI gates; `FoundryEvals` results should be trends compared against a baseline.

### How to detect

Look for code that aggregates `.passed` across **all** elements of the `evaluate_*` return list without separating by provider type.

---

## 6. Default `ConversationSplit` (LAST_TURN) when trajectory matters

### ❌ Wrong

```python
# Multi-turn debugging agent that issues several tool calls before answering
results = await evaluate_agent(
    agent=debugger_agent,
    queries=multi_turn_conversations,
    evaluators=FoundryEvals(client=judge_client),
    # conversation_split defaults to LAST_TURN
)
```

### Why it's wrong

`ConversationSplit.LAST_TURN` only sends the **last assistant message** to the judge — the entire reasoning trajectory is invisible. A debugging agent that called the wrong tool five turns ago but recovered will score perfectly; a regression in the tool-selection logic will be silent.

### ✅ Right

```python
from agent_framework import ConversationSplit

results = await evaluate_agent(
    agent=debugger_agent,
    queries=multi_turn_conversations,
    evaluators=FoundryEvals(client=judge_client, conversation_split=ConversationSplit.FULL),
)
```

Use `ConversationSplit.FULL` for multi-turn / trajectory-sensitive evaluation; keep `LAST_TURN` for single-shot QA where only the final answer matters.

### How to detect

```bash
grep -rn "conversation_split\|ConversationSplit" --include="*.py"
```

Files using `FoundryEvals` on multi-turn agents that never mention `conversation_split` are using the default.

---

## 7. Final-answer-only eval ignoring tool trajectory

### ❌ Wrong

```python
evaluators = FoundryEvals(
    client=judge_client,
    evaluators=[FoundryEvals.RELEVANCE],   # only judges the final answer string
)
```

### Why it's wrong

An agent that calls the *wrong* tool but produces a *passable* final answer scores well. Worst case: the tool call wrote bad data to a downstream system and the eval never noticed because the chat output read fine.

### ✅ Right

```python
from agent_framework import LocalEvaluator, tool_called_check
from agent_framework.foundry import FoundryChatClient, FoundryEvals

results = await evaluate_agent(
    agent=agent,
    queries=queries,
    evaluators=[
        # FoundryEvals.* constants are strings — wrap them in a FoundryEvals provider
        FoundryEvals(
            client=FoundryChatClient(credential=cred, model="gpt-5-4"),
            evaluators=[
                FoundryEvals.RELEVANCE,
                FoundryEvals.TOOL_CALL_ACCURACY,
            ],
        ),
        # plus a deterministic CI check:
        LocalEvaluator(tool_called_check("expected_tool")),
    ],
)
```

For any agent with tools, include a tool-trajectory evaluator. `TOOL_CALL_ACCURACY` is auto-added to defaults when items have tools (see [`_foundry_evals.py:L125-L127`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L125-L127)) — but if you supply an explicit `evaluators=` list to the `FoundryEvals` constructor, you have to add it yourself. Passing `FoundryEvals.RELEVANCE` (a bare string) directly to `evaluate_agent(evaluators=[...])` raises `TypeError` from `_resolve_evaluators` because strings are neither `Evaluator` instances nor callables ([`_evaluation.py:L1880-L1909`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1880-L1909)).

### How to detect

```bash
grep -rn "FoundryEvals(" --include="*.py" -A5 | grep -B1 "evaluators=" | \
  grep -v "TOOL_CALL_ACCURACY\|TOOL_SELECTION\|TOOL_INPUT_ACCURACY"
```

(Imperfect; falls back to manual review of agents with tools.)

---

## 8. No item/trace retention — only aggregate scores stored

### ❌ Wrong

```python
results = await evaluate_agent(...)
log.info(f"score: {results[0].passed / results[0].total}")
# results, items, AgentResponses all garbage-collected
```

### Why it's wrong

When the next eval run shows a drop, you have nothing to diagnose with — no per-item scores, no responses, no traces, no Foundry portal link. The team is reduced to guessing which change in the last 50 commits caused the regression.

### ✅ Right

```python
from dataclasses import asdict

results = await evaluate_agent(...)
for r in results:
    persist(
        run_id=run_id,
        provider=r.provider,
        passed=r.passed,
        total=r.total,                       # passed + failed only (not errored)
        errored=(r.result_counts or {}).get("errored", 0),
        report_url=r.report_url,             # foundry portal deep-link
        items=[
            {
                "id": it.item_id,
                "status": it.status,
                # EvalScoreResult is a @dataclass, not Pydantic — use dataclasses.asdict
                "scores": [asdict(s) for s in it.scores],
            }
            for it in r.items
        ],
    )
```

Always persist `r.report_url` (when available — `FoundryEvals` sets it; `LocalEvaluator` does not) and at least item-level scores. Tie evaluation runs to commit SHA + agent version for bisection.

### How to detect

Code review: any code that reads `.passed` / `.total` but never reads `.items` or `.report_url` is discarding the diagnostic data.

---

## 9. Using EVALS-stage APIs without `@experimental` opt-in in production

### ❌ Wrong

```python
# production module
from agent_framework import evaluate_agent
from agent_framework.foundry import FoundryEvals
# ... uses them without acknowledging experimental status
```

### Why it's wrong

Every public symbol in `_evaluation.py` and `_foundry_evals.py` is decorated with `@experimental(ExperimentalFeature.EVALS)` (verified at [`_evaluation.py:182`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L182), [`_foundry_evals.py:519`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L519)). Minor version upgrades can break signatures, default behavior, or constant names with no deprecation. Production code that ignores this surfaces silent breakage on every dependency bump.

### ✅ Right

- Pin `agent-framework-foundry` to an exact minor version (`==1.8.0`, not `>=1.7,<2`)
- Centralize all EVALS imports in a single module (`yourapp/_eval_compat.py`) so the blast radius of an upstream change is one file
- Run the eval pipeline in CI against the pinned version on every dependency change
- Document the experimental status in the team's runbook

### How to detect

```bash
grep -rn "from agent_framework\(\\.foundry\)\? import" --include="*.py" | \
  grep -E "(evaluate_agent|evaluate_workflow|FoundryEvals|LocalEvaluator|EvalItem|@evaluator)"
```

Cross-check that all hits flow through a single compat module.

---

## 10. Calling `FoundryEvals()` without `model=` (judge fallback pitfall)

### ❌ Wrong

```python
from agent_framework.foundry import FoundryEvals

# Relies on the SDK fallback judge model
evals = FoundryEvals()
```

### Why it's wrong

`FoundryEvals(...)` in `agent-framework-foundry==1.8.0` hard-codes `"gpt-4o"` as the judge model when `model=` is omitted (verified at [`_foundry_evals.py:L633-L635`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L633-L635)). Against the workshop default Foundry project — which deploys only `gpt-5-4` (see [`docs/foundry-provisioning.md` § Default environment](../../docs/foundry-provisioning.md)) — this fails immediately with `DeploymentNotFound`. Even when `gpt-4o` *is* deployed, it has been deprecated since 2026-03-31 and Foundry returns `ServiceModelDeprecated`. The fallback is **not** picked up from `FOUNDRY_MODEL` — that env var feeds the agent under test, not the judge.

### ✅ Right

```python
import os
from azure.identity.aio import AzureCliCredential
from agent_framework.foundry import FoundryChatClient, FoundryEvals

# ✅ Explicit judge model
evals = FoundryEvals(model="gpt-5-4")

# ✅ Via configured client (preferred — credential + model lifecycle in one place)
async with AzureCliCredential() as cred:
    evals = FoundryEvals(client=FoundryChatClient(credential=cred, model="gpt-5-4"))

# ✅ Best — env-aware via repo convention (FOUNDRY_JUDGE_MODEL, default gpt-5-4)
judge_model = os.environ.get("FOUNDRY_JUDGE_MODEL", "gpt-5-4")
evals = FoundryEvals(model=judge_model)
```

> [!IMPORTANT]
> `FOUNDRY_JUDGE_MODEL` is a **repo convention**, not an SDK-recognized variable. The Foundry SDK does not read it on its own — every call site that constructs `FoundryEvals(...)` must read the env var and pass `model=` explicitly. Setting `FOUNDRY_JUDGE_MODEL=…` in `.env` without code that consumes it does nothing. Each `.env.example` in this repo carries the optional `FOUNDRY_JUDGE_MODEL=gpt-5-4` comment so the convention is discoverable.

See [`foundry-environment-pitfalls.md` § P-7](foundry-environment-pitfalls.md#p-7--foundryevals-default-judge-is-gpt-4o-deprecated) for the environment / provisioning lens on the same pitfall (deployment names, `ServiceModelDeprecated`, `.env.example` rollout).

### How to detect

```bash
# Any FoundryEvals(...) call without an explicit model= or client= is broken at runtime:
rg -n "FoundryEvals\(" --glob "*.py" tests templates examples src | \
  grep -v "model=" | grep -v "client=" | grep -v "FoundryEvals," | grep -v "FoundryEvals\."
# Expected: 0 lines
```

---



## See also

- API reference: [`../api-reference/1.8.0/evaluation.md`](../api-reference/1.8.0/evaluation.md)
- Pattern: [`../patterns/agent-evaluation-local.md`](../patterns/agent-evaluation-local.md)
- Pattern: [`../patterns/agent-evaluation-foundry.md`](../patterns/agent-evaluation-foundry.md)
- Pattern: [`../patterns/workflow-evaluation.md`](../patterns/workflow-evaluation.md)
- Anti-pattern (environment lens): [`./foundry-environment-pitfalls.md` § P-7](./foundry-environment-pitfalls.md#p-7--foundryevals-default-judge-is-gpt-4o-deprecated) — judge model defaults + deployment / `ServiceModelDeprecated` mitigations

---

**Upstream source:** [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`python/packages/core/agent_framework/_evaluation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py), [`python/packages/foundry/agent_framework_foundry/_foundry_evals.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py).
