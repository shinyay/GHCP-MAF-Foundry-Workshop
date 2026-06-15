# Evaluation: Provider-Agnostic Agent & Workflow Scoring

> Status: **⚠️ Experimental — `ExperimentalFeature.EVALS`**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`_evaluation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py), [`_foundry_evals.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py)

The evaluation subsystem is the framework's seam for **measuring agent and workflow quality** — a provider-agnostic `Evaluator` protocol plus two reference implementations (`LocalEvaluator` for zero-cost deterministic checks, `FoundryEvals` for production LLM-judge scoring), driven by two entry points (`evaluate_agent`, `evaluate_workflow`).

> [!NOTE]
> **1.8.0 NEW — Adaptive Evals consumer surface ([PR #6101](https://github.com/microsoft/agent-framework/pull/6101))**: 1.8.0 ships the **consumer half** of Adaptive Evals — pass a portal-authored rubric evaluator into the existing eval pipeline via `GeneratedEvaluatorRef.latest(name="my-rubric")` (or `GeneratedEvaluatorRef(name=..., version=...)` for pinned), mixed with built-in evaluators in `FoundryEvals(evaluators=[ref, FoundryEvals.RELEVANCE, ...])`. Per-dimension scores land in `EvalScoreResult.dimensions: list[RubricScore]`. Three new CI-gating helpers — `EvalResults.assert_score_at_least`, `assert_dimension_score_at_least`, `assert_no_failed_items` — make threshold-based gates ergonomic. All are `@experimental(feature_id=ExperimentalFeature.EVALS)` and pair with the new `templates/adaptive-evals/` scaffold. The rubric definition itself is authored **out-of-band in the Foundry portal**; the SDK-side `FoundryEvals.generate_rubric(...)` and `load_evaluators_from_yaml(...)` helpers were in PR #6101's plan but did **not** ship in the 1.8.0 tag — track [PR #6101 follow-ups](https://github.com/microsoft/agent-framework/pull/6101) for generator-side helpers in a future minor. See [`feature-stages.md`](feature-stages.md#adaptive-evals-and-mcpskillssource-new-in-180).

> [!WARNING]
> **Every public symbol on this page is decorated `@experimental(feature_id=ExperimentalFeature.EVALS)`** ([`_evaluation.py:181-182`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L181-L182), [`_foundry_evals.py:518-519`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L518-L519)). The shapes may change in any minor release. Pin tightly (`agent-framework-foundry==1.8.0`) and treat regressions as expected on upgrade. See [`feature-stages.md`](feature-stages.md) for the full warning model and how to silence/track `[EVALS] ... ExperimentalWarning`.

## Which evaluation path do I use?

| Goal | Path | Cost | Determinism | LLM judge | Azure required |
|------|------|------|-------------|-----------|----------------|
| Unit-test-style assertions (keyword present, tool called) | [`LocalEvaluator`](#localevaluator) + built-in checks | none | ✅ deterministic | ❌ | ❌ |
| Custom in-process scorer (string distance, regex, your own model) | [`LocalEvaluator`](#localevaluator) + [`@evaluator`](#evaluator-decorator) | none | depends on your fn | optional | ❌ |
| Production quality scoring (relevance, groundedness, safety) | [`FoundryEvals`](#foundryevals) | LLM-judge tokens | ❌ probabilistic | ✅ | ✅ Foundry project |
| Score historical responses (Responses API or OTel traces) | [`evaluate_traces`](#evaluate_traces) | LLM-judge tokens | ❌ probabilistic | ✅ | ✅ Foundry (+ App Insights when using `trace_ids` / `agent_id`) |
| Scheduled / CI eval against a deployed Foundry agent | [`evaluate_foundry_target`](#evaluate_foundry_target) | LLM-judge tokens | ❌ probabilistic | ✅ | ✅ Foundry-deployed target |

The first two run entirely in-process; the last three call the Foundry evals service. `LocalEvaluator` (with bare checks or `@evaluator`-decorated functions) and `FoundryEvals` are **composable** — pass a sequence to `evaluate_agent` / `evaluate_workflow` and each runs independently. `evaluate_traces` and `evaluate_foundry_target` are standalone helpers that **do not compose** through the entry-point list.

## Top-level exports

All these symbols are top-level exports of `agent_framework` ([`core/__init__.py:61-78,320-529`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/__init__.py#L61-L78)). The Foundry-specific symbols are top-level exports of `agent_framework.foundry`.

| Category | Symbol | Module |
|----------|--------|--------|
| Entry points | `evaluate_agent`, `evaluate_workflow` | `agent_framework` |
| Provider Protocol | `Evaluator` | `agent_framework` |
| Built-in providers | `LocalEvaluator`, `FoundryEvals` | `agent_framework` / `agent_framework.foundry` |
| Splitting | `ConversationSplit` (Enum), `ConversationSplitter` (Protocol) | `agent_framework` |
| Value objects | `EvalItem`, `EvalResults`, `EvalItemResult`, `EvalScoreResult`, `CheckResult`, `ExpectedToolCall` | `agent_framework` |
| Check authoring | `@evaluator` (decorator) | `agent_framework` |
| Internal type alias | `EvalCheck` (`Callable[[EvalItem], CheckResult \| Awaitable[CheckResult]]` — defined in `_evaluation.py:L876`, **not** re-exported from `agent_framework`; import directly only if needed for type hints) | `agent_framework._evaluation` |
| Built-in checks | `keyword_check`, `tool_called_check`, `tool_calls_present`, `tool_call_args_match` | `agent_framework` |
| Helper | `AgentEvalConverter` | `agent_framework` |
| Exception | `EvalNotPassedError` | `agent_framework` |
| Foundry helpers | `evaluate_traces`, `evaluate_foundry_target` | `agent_framework.foundry` |

## Core protocol — `Evaluator`

[`_evaluation.py:L507-L552`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L507-L552).

```python
@runtime_checkable
class Evaluator(Protocol):
    name: str
    async def evaluate(self, items: Sequence[EvalItem], *, eval_name: str) -> EvalResults: ...
```

Any provider — `LocalEvaluator`, `FoundryEvals`, or your own — implements this single async method. `evaluate_agent` and `evaluate_workflow` accept one or many of them.

## Value objects

### `EvalItem` — one query/response interaction

[`_evaluation.py:L182-L304`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L182-L304).

The provider-agnostic unit of evaluation. `conversation` is the single source of truth — `query` and `response` are derived via the active `ConversationSplitter`.

```python
class EvalItem:
    conversation: list[Message]
    tools: list[FunctionTool] | None              # typed tool objects (drives tool-related evaluators)
    context: str | None                            # grounding context document
    expected_output: str | None                    # ground-truth reference (similarity / equality)
    expected_tool_calls: list[ExpectedToolCall] | None
    split_strategy: ConversationSplitter           # defaults to ConversationSplit.LAST_TURN
```

You rarely build `EvalItem` by hand — `evaluate_agent` constructs them from `AgentResponse` via `AgentEvalConverter` ([`_evaluation.py:L557+`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L557)).

### `ExpectedToolCall` — pure-data assertion spec

[`_evaluation.py:L140-L154`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L140-L154).

```python
@dataclass
class ExpectedToolCall:
    name: str
    arguments: dict[str, Any] | None = None   # None = don't check args
```

The matching semantics (order, extras allowed, argument equality) is the **evaluator's** responsibility, not this dataclass's — `tool_calls_present` is unordered+extras-OK on names, while `tool_call_args_match` does **subset** argument matching: every expected key/value pair must be present in the actual call, but extra actual arguments are OK ([`_evaluation.py:L1080-L1085`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1080-L1085)).

### `CheckResult` — single check on a single item

[`_evaluation.py:L862-L873`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L862-L873).

```python
@dataclass
class CheckResult:
    passed: bool
    reason: str
    check_name: str
```

What every `EvalCheck` returns. `LocalEvaluator` aggregates many `CheckResult`s into one `EvalResults`.

### `EvalResults` — top-level result per provider

[`_evaluation.py:L370-L505`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L370-L505). One `EvalResults` per evaluator provider per call.

Key fields:

| Field | Type | Notes |
|-------|------|-------|
| `provider` | `str` | e.g. `"Local"`, `"Microsoft Foundry"` |
| `status` | `str` | `"completed"`, `"failed"`, `"canceled"`, `"timeout"` |
| `passed` / `failed` / `total` (properties) | `int` | Convenience accessors over `result_counts`. **`total = passed + failed` and does NOT include `errored`** ([`_evaluation.py:L437-L450`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L437-L450)) — check `result_counts.get("errored", 0)` separately to detect run-time errors |
| `result_counts` | `dict[str, int]` | `{"passed": N, "failed": N, "errored": N}` |
| `per_evaluator` | `dict[str, dict[str, int]]` | Per-check breakdown |
| `items` | `list[EvalItemResult]` | Per-item scores (populated when provider supports it — Foundry does) |
| `sub_results` | `dict[str, EvalResults]` | **Per-agent breakdown for `evaluate_workflow`** |
| `report_url` | `str \| None` | Foundry portal link |

### `EvalItemResult` / `EvalScoreResult`

[`_evaluation.py:L306-L368`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L306-L368). Per-item drill-down. Use these to diagnose specific failures rather than relying on aggregate `passed/total`.

### `EvalNotPassedError`

[`_evaluation.py:L69-L70`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L69-L70).

```python
class EvalNotPassedError(Exception):
    """Raised when evaluation results contain failures."""
```

Exported and **raised by `EvalResults.raise_for_status()`** when any item failed ([`_evaluation.py:L467-L497`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L467-L497)). The orchestration entry points (`evaluate_agent`, `evaluate_workflow`) do **not** auto-raise — they return `EvalResults`. Call `result.raise_for_status()` explicitly to turn failures into an exception (e.g., a CI gate).

## Conversation splitting

### `ConversationSplit` (enum) and `ConversationSplitter` (Protocol)

[`_evaluation.py:L78-L138`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L78-L138).

```python
class ConversationSplit(str, Enum):
    LAST_TURN = "last_turn"   # split at last user message — judge the LAST answer
    FULL = "full"             # split after first user message — judge the WHOLE trajectory
```

Each enum member is callable, satisfying the `ConversationSplitter` protocol:

```python
query_msgs, response_msgs = ConversationSplit.LAST_TURN(conversation)
```

Custom splitters are any callable with the protocol signature ([`_evaluation.py:L78-L107`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L78-L107)):

```python
def split_before_memory(conversation: list[Message]) -> tuple[list[Message], list[Message]]:
    for i, msg in enumerate(conversation):
        for c in msg.contents or []:
            if c.type == "function_call" and c.name == "retrieve_memory":
                return conversation[:i], conversation[i:]
    return ConversationSplit.LAST_TURN(conversation)
```

> [!IMPORTANT]
> **`LAST_TURN` vs `FULL` is a semantic choice, not a default to ignore.** A multi-turn debugging agent evaluated with `LAST_TURN` only judges the last reply — a wrong tool call three turns ago is invisible to relevance scoring. Use `FULL` (or a custom splitter) when the trajectory matters.

## Entry points

### `evaluate_agent`

[`_evaluation.py:L1453-L1556`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1453-L1556).

```python
async def evaluate_agent(
    *,
    agent: SupportsAgentRun | None = None,
    queries: str | Sequence[str] | None = None,
    expected_output: str | Sequence[str] | None = None,
    expected_tool_calls: Sequence[ExpectedToolCall] | Sequence[Sequence[ExpectedToolCall]] | None = None,
    responses: AgentResponse[Any] | Sequence[AgentResponse[Any]] | None = None,
    evaluators: Evaluator | Callable[..., Any] | Sequence[Evaluator | Callable[..., Any]],
    eval_name: str | None = None,
    context: str | None = None,
    conversation_split: ConversationSplitter | None = None,
    num_repetitions: int = 1,
) -> list[EvalResults]: ...
```

Two modes:

1. **Run + evaluate** — pass `agent=` + `queries=`. The framework runs the agent for each query, then submits the responses to every evaluator.
2. **Score only** — pass `responses=` (pre-existing `AgentResponse`s) + `queries=`. The agent is **not** re-run; existing responses are scored. Useful for replay against historical data.

Notable parameters:

| Param | Notes |
|-------|-------|
| `expected_output` | Must be the same length as `queries`. Stamped onto each `EvalItem.expected_output` for reference-based evaluators (e.g. `SIMILARITY`). |
| `expected_tool_calls` | A flat list of `ExpectedToolCall` is wrapped as a one-element nested list. Otherwise nested length must match `queries`. |
| `num_repetitions` | Default `1`. When `> 1`, each query is run independently N times so probabilistic evaluators can measure consistency. **Ignored when `responses=` is provided** ([`_evaluation.py:L1505-L1509`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1505-L1509)). |
| `conversation_split` | Overrides each evaluator's default splitter for this call. |
| `evaluators` | Accepts a single `Evaluator`, a single bare `EvalCheck` callable, or a list mixing both. |

Returns **one `EvalResults` per provider** — composing `[LocalEvaluator(...), FoundryEvals(...)]` yields two result objects.

### `evaluate_workflow`

[`_evaluation.py:L1657-L1724`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1657-L1724).

```python
async def evaluate_workflow(
    *,
    workflow: Workflow,
    workflow_result: WorkflowRunResult | None = None,
    queries: str | Sequence[str] | None = None,
    expected_output: str | Sequence[str] | None = None,
    evaluators: Evaluator | Callable[..., Any] | Sequence[Evaluator | Callable[..., Any]],
    eval_name: str | None = None,
    include_overall: bool = True,
    include_per_agent: bool = True,
    conversation_split: ConversationSplitter | None = None,
    num_repetitions: int = 1,
) -> list[EvalResults]: ...
```

Same two modes (`workflow_result=` post-hoc OR `queries=` run-and-evaluate). The key shape difference is that each returned `EvalResults` populates `sub_results: dict[str, EvalResults]` — one entry per sub-agent/executor whose work the workflow produced ([`_evaluation.py:L388-L389`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L388-L389)).

| Param | Behavior |
|-------|----------|
| `include_overall` | When `True` (default), evaluates the workflow's final output as one item |
| `include_per_agent` | When `True` (default), evaluates each sub-agent individually and reports them in `sub_results` |

See [`workflow-evaluation.md`](../../patterns/workflow-evaluation.md) for the per-agent drill-down pattern.

## `LocalEvaluator` — zero-cost deterministic checks

[`_evaluation.py:L1343-L1450`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1343-L1450).

```python
class LocalEvaluator:
    def __init__(self, *checks: EvalCheck): ...
    async def evaluate(self, items, *, eval_name="Local Eval") -> EvalResults: ...
```

`LocalEvaluator(*checks)` runs every check against every item. An item passes only when **all** checks pass for it ([`_evaluation.py:L1402-L1411`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1402-L1411)). Both sync and async checks are supported — async ones are awaited automatically.

No network, no API keys, no Azure. The fastest feedback loop for "did the agent call the right tool" / "did the response mention the keyword".

### Built-in checks

All four are `@experimental(EVALS)` and exported from `agent_framework`. They return an `EvalCheck` — a callable that takes an `EvalItem` and returns a `CheckResult`.

| Factory / function | Signature | What it checks |
|--------------------|-----------|----------------|
| `keyword_check(*keywords, case_sensitive=False)` | factory | Response contains **all** given keywords ([`_evaluation.py:L886-L911`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L886-L911)) |
| `tool_called_check(*tool_names, mode="all"\|"any")` | factory | The conversation includes function calls matching the names. `mode="all"` requires every name; `"any"` requires at least one ([`_evaluation.py:L915-L991`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L915-L991)) |
| `tool_calls_present(item)` | check fn | Reads `item.expected_tool_calls`. Unordered, extras OK — every expected name must appear among called tools ([`_evaluation.py:L997+`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L997)) |
| `tool_call_args_match(item)` | check fn | Like above but additionally checks each expected tool's `arguments` dict matches the actual call ([`_evaluation.py:L1039+`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1039)) |

Factories (`keyword_check`, `tool_called_check`) take config and return a check; the other two are themselves checks because they read their expectations from the item.

### `@evaluator` decorator

[`_evaluation.py:L1240-L1341`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1240-L1341).

Wraps a plain function as an `EvalCheck`. The parameter names you declare determine what's injected:

| Param name | Type | Source |
|------------|------|--------|
| `query` | `str` | derived via split strategy |
| `response` | `str` | derived via split strategy |
| `expected_output` | `str` | `item.expected_output` (empty `""` if not set) |
| `expected_tool_calls` | `list[ExpectedToolCall]` | `item.expected_tool_calls` (empty list if not set) |
| `conversation` | `list[Message]` | `item.conversation` |
| `tools` | `list[FunctionTool] \| None` | `item.tools` |
| `context` | `str \| None` | `item.context` |

The full set of accepted names is `_KNOWN_PARAMS` ([`_evaluation.py:L1109-L1117`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L1109-L1117)). Declaring any other required parameter raises `TypeError` at decoration time.

Return value handling:

- `bool` → pass/fail directly
- `float` → `≥ 0.5` is pass
- `dict` with `score` or `passed` key
- `CheckResult` → used as-is

Both sync and async functions are supported.

```python
from agent_framework import evaluator

@evaluator
def mentions_weather(response: str) -> bool:
    return "weather" in response.lower()

@evaluator(name="length_check")
def is_short(response: str) -> bool:
    return len(response) < 2000

@evaluator
async def llm_judge(query: str, response: str) -> float:
    score = await my_external_judge.score(query, response)
    return score   # ≥ 0.5 → pass
```

- `EvalCheck` is the **internal** type alias `Callable[[EvalItem], CheckResult | Awaitable[CheckResult]]` defined in [`_evaluation.py:L876-L883`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L876-L883). It is **not** re-exported from `agent_framework` — there is no `from agent_framework import EvalCheck`. Import it from `agent_framework._evaluation` (or just use `Callable[[EvalItem], CheckResult]` directly) only when you need an explicit type hint. Most users never touch the name: the built-in check factories return one, `@evaluator` produces one, and `LocalEvaluator(*checks)` accepts plain callables.

## `FoundryEvals` — production LLM-judge scoring

[`_foundry_evals.py:L519-L760`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L519-L760).

```python
class FoundryEvals:
    def __init__(
        self,
        *,
        client: FoundryChatClient | None = None,
        project_client: AIProjectClient | None = None,
        model: str | None = None,
        evaluators: Sequence[str] | None = None,
        conversation_split: ConversationSplitter = ConversationSplit.LAST_TURN,
        poll_interval: float = 5.0,
        timeout: float = 180.0,
    ): ...
    async def evaluate(self, items, *, eval_name="Agent Framework Eval") -> EvalResults: ...
```

Implements `Evaluator` against the Foundry-hosted `builtin.*` evaluators (the OpenAI evals API on a Foundry endpoint — [`_foundry_evals.py:560-565`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L560-L565)).

When `client` and `project_client` are both `None`, `FoundryEvals()` constructs `FoundryChatClient(model=model or "gpt-4o")` ([`_foundry_evals.py:L633-L635`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L633-L635)). The `model` default is the **hard-coded string `"gpt-4o"`** — it does **not** read `FOUNDRY_MODEL`. The workshop default Foundry project deploys only `gpt-5-4` (see [`docs/foundry-provisioning.md` § Default environment](../../../docs/foundry-provisioning.md)), so an unconfigured `FoundryEvals()` fails with `DeploymentNotFound` against the workshop default. Pass the judge model explicitly (`FoundryEvals(model=os.getenv("FOUNDRY_JUDGE_MODEL", "gpt-5-4"))`) or hand in a pre-built `FoundryChatClient(model="gpt-5-4")`. The `FoundryChatClient` itself still resolves its `project_endpoint` from `FOUNDRY_PROJECT_ENDPOINT` when not supplied.

> [!IMPORTANT]
> **Always pass `model='gpt-5-4'` explicitly** when constructing `FoundryEvals(...)` in this repo. The SDK fallback `"gpt-4o"` is also deprecated as of 2026-03-31 and triggers `ServiceModelDeprecated` even when deployed. The repo convention is the `FOUNDRY_JUDGE_MODEL` env var (defaulting to `gpt-5-4`) — see [Anti-pattern: Calling `FoundryEvals()` without `model=`](../../anti-patterns/eval-as-test-substitute.md#10-calling-foundryevals-without-model-judge-fallback-pitfall) and [foundry-environment-pitfalls.md § P-7](../../anti-patterns/foundry-environment-pitfalls.md#p-7--foundryevals-default-judge-is-gpt-4o-deprecated).

> [!NOTE]
> Using the same model for the agent under test **and** the judge introduces correlation bias (anti-pattern §2 in [eval-as-test-substitute](../../anti-patterns/eval-as-test-substitute.md)). Picking the judge model deliberately — typically larger / different family than the agent — is part of evaluator design, not a deploy detail. The workshop's single-deployment default constrains examples to one model; production setups should provision a separate judge deployment.

### Default evaluator resolution

When `evaluators=None` (the default):

- Always runs: `relevance`, `coherence`, `task_adherence` ([`_foundry_evals.py:L119-L123`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L119-L123))
- Auto-adds: `tool_call_accuracy` when any item has tools ([`_foundry_evals.py:L125-L127`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L125-L127), [`L255-L266`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L255-L266))

When you pass `evaluators=[...]` explicitly, the framework still filters out tool-only evaluators when no items have tools ([`_foundry_evals.py:L269-L288`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L269-L288)) — and raises `ValueError` if filtering would leave zero evaluators.

### Built-in evaluator constants — 19 across 4 categories

Verified at [`_foundry_evals.py:L587-L618`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L587-L618). Use the class constants instead of strings for IDE autocomplete:

```python
from agent_framework.foundry import FoundryEvals
evals = FoundryEvals(evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY])
```

#### Agent behavior (4)

| Constant | What it judges |
|----------|----------------|
| `INTENT_RESOLUTION` | Did the agent correctly resolve what the user actually wanted? |
| `TASK_ADHERENCE` | Did the agent stay on-task vs drifting? (default-on) |
| `TASK_COMPLETION` | Did the agent finish the requested task end-to-end? |
| `TASK_NAVIGATION_EFFICIENCY` | How efficiently did the agent get from query to answer? |

#### Tool usage (5)

| Constant | What it judges |
|----------|----------------|
| `TOOL_CALL_ACCURACY` | Did the agent call the right tools? (auto-added when items have tools) |
| `TOOL_SELECTION` | Of the available tools, did it pick the best one? |
| `TOOL_INPUT_ACCURACY` | Were the arguments passed to tools correct? |
| `TOOL_OUTPUT_UTILIZATION` | Did the agent actually use tool results in its response? |
| `TOOL_CALL_SUCCESS` | Did tool invocations succeed (no errors)? |

#### Quality (6)

| Constant | What it judges |
|----------|----------------|
| `COHERENCE` | Logical flow and consistency of the response (default-on) |
| `FLUENCY` | Natural-language quality |
| `RELEVANCE` | Does the response address the query? (default-on) |
| `GROUNDEDNESS` | Is the response supported by `EvalItem.context`? (needs `context=`) |
| `RESPONSE_COMPLETENESS` | Did the response cover all parts of a multi-part query? |
| `SIMILARITY` | Closeness to `expected_output` (needs ground truth) |

#### Safety (4)

| Constant | What it judges |
|----------|----------------|
| `VIOLENCE` | Violent content score |
| `SEXUAL` | Sexual content score |
| `SELF_HARM` | Self-harm content score |
| `HATE_UNFAIRNESS` | Hateful or unfair content score |

**Total: 4 + 5 + 6 + 4 = 19 evaluators.**

> [!NOTE]
> `RELEVANCE`, `COHERENCE`, `TASK_ADHERENCE` are the **default-on** set when you call `FoundryEvals()` with no `evaluators=` argument. `TOOL_CALL_ACCURACY` is appended automatically when items have tools.

### `eval_name` and `report_url`

`evaluate()` accepts `eval_name="..."` to label the run in the Foundry portal. The returned `EvalResults.report_url` is a deep link to the Foundry portal page for the run — surface it to your operator UI or CI logs for triage.

## Foundry helpers (not on the `Evaluator` protocol)

### `evaluate_traces`

[`_foundry_evals.py:L762-L851`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L762-L851).

```python
async def evaluate_traces(
    *,
    evaluators: Sequence[str] | None = None,
    client: FoundryChatClient | None = None,
    project_client: AIProjectClient | None = None,
    model: str,
    response_ids: Sequence[str] | None = None,
    trace_ids: Sequence[str] | None = None,
    agent_id: str | None = None,
    lookback_hours: int = 24,
    eval_name: str = "Agent Framework Trace Eval",
    poll_interval: float = 5.0,
    timeout: float = 180.0,
) -> EvalResults: ...
```

Evaluate **historical** agent activity. Three selection modes:

- `response_ids=` — score specific Responses API responses by ID (no App Insights required — pulls directly from the OpenAI Responses API on the Foundry endpoint)
- `trace_ids=` — score specific OTel trace IDs from Application Insights
- `agent_id=` + `lookback_hours=` — score recent OTel-traced activity for an agent (default last 24h, also requires App Insights)

This is for **post-hoc quality monitoring** of production traffic. The `trace_ids` / `agent_id` modes additionally require the App Insights export wiring described in [`observability-otel.md`](../../patterns/observability-otel.md); `response_ids` works against any captured response ID without OTel.

### `evaluate_foundry_target`

[`_foundry_evals.py:L853-L910`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py#L853-L910).

```python
async def evaluate_foundry_target(
    *,
    target: dict[str, Any],
    test_queries: Sequence[str],
    evaluators: Sequence[str] | None = None,
    client: FoundryChatClient | None = None,
    project_client: AIProjectClient | None = None,
    model: str,
    eval_name: str = "Agent Framework Target Eval",
    poll_interval: float = 5.0,
    timeout: float = 180.0,
) -> EvalResults: ...
```

Evaluate a **Foundry-registered agent or model deployment**. Foundry itself invokes the target with `test_queries`, captures the output, and scores it. Designed for scheduled evals, red teaming, and CI/CD quality gates against deployed agents (no Python agent instance required on the calling side).

## `AgentEvalConverter`

[`_evaluation.py:L557-L860`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py#L557-L860). The bridge from `AgentResponse` / `WorkflowRunResult` to `EvalItem`. You generally don't call this directly — `evaluate_agent` and `evaluate_workflow` use it internally — but it's useful when you build a custom evaluator that wants to consume agent-framework types.

## Not included on this page (harness primitives)

The `agent_framework._harness` package ships `TodoStore` / `TodoProvider` / `TodoFileStore` and `AgentModeProvider` / `get_agent_mode` / `set_agent_mode`. These are decorated `@experimental(feature_id=ExperimentalFeature.HARNESS)` — a **separate** feature flag from `ExperimentalFeature.EVALS` ([`_feature_stage.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py)). They are testing/orchestration utilities, not evaluation primitives, and will be documented in a future harness-focused KB update — not here.

## Common pitfalls → see anti-pattern

See [`../../anti-patterns/eval-as-test-substitute.md`](../../anti-patterns/eval-as-test-substitute.md) for the catalog of evaluation foot-guns:

- Hardcoding `assert passed == total` as a CI gate on LLM-judge results
- Using the same model for agent and judge (correlation bias)
- `num_repetitions=1` for non-deterministic judgment
- Ignoring `ConversationSplit` (`LAST_TURN` vs `FULL`)
- Over-specifying `expected_output` on open-ended generation
- Mixing deterministic check pass-rates with LLM-judge scores
- Evaluating final answer while ignoring tool trajectory
- Discarding raw items/traces and reporting only aggregate scores

## See also

- Patterns: [`agent-evaluation-local.md`](../../patterns/agent-evaluation-local.md) · [`agent-evaluation-foundry.md`](../../patterns/agent-evaluation-foundry.md) · [`workflow-evaluation.md`](../../patterns/workflow-evaluation.md)
- Anti-pattern: [`eval-as-test-substitute.md`](../../anti-patterns/eval-as-test-substitute.md)
- Related: [`agents.md`](agents.md) · [`workflows.md`](workflows.md) · [`clients.md`](clients.md) · [`observability.md`](observability.md)

---

**Upstream source:** [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`python/packages/core/agent_framework/_evaluation.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_evaluation.py), [`python/packages/foundry/agent_framework_foundry/_foundry_evals.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py).
