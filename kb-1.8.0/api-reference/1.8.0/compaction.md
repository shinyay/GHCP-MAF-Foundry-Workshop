# Message Compaction: strategies, providers, and the group model

> Status: **Stable** — public API since the `_compaction` symbols were re-exported at top level.
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) at commit `950673b`
> Upstream source: [`python/packages/core/agent_framework/_compaction.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py) (1429 LOC)

Message compaction trims an agent's conversation history before it reaches the model — by truncating, windowing, summarizing, or collapsing tool calls — so that long-running sessions don't blow past the model's context window or your token budget.

> [!NOTE]
> Compaction is **opt-in**. Agents created without a `CompactionProvider` send the full message history every turn. There is no built-in default.

> [!IMPORTANT]
> **1.8.0 FIX — Message-id collisions in summarization compaction ([PR #6299](https://github.com/microsoft/agent-framework/pull/6299))**: `SummarizationStrategy` and `ContextWindowCompactionStrategy` could previously reuse the same synthetic `message_id` across two compacted summaries inside one session, which made downstream history-providers (and any consumer keying off `message_id`) silently drop or overwrite earlier summaries. 1.8.0 makes the synthesized summary id unique per invocation. No API change; upgrade and re-run.

---

## Quick decision table

| You want… | Use |
|---|---|
| Hard cap on count or tokens, drop oldest groups first | [`TruncationStrategy`](#truncationstrategy) |
| Keep last N user/assistant turns, drop older | [`SlidingWindowStrategy`](#slidingwindowstrategy) |
| Keep last N tool-call sequences, drop older (chat unchanged) | [`SelectiveToolCallCompactionStrategy`](#selectivetoolcallcompactionstrategy) |
| Collapse old tool calls into one-line summary placeholder | [`ToolResultCompactionStrategy`](#toolresultcompactionstrategy) |
| LLM-generated summary of old conversation | [`SummarizationStrategy`](#summarizationstrategy) |
| Combine several strategies under a single token budget | [`TokenBudgetComposedStrategy`](#tokenbudgetcomposedstrategy) |
| Token-budget compaction tuned to a model's context window (tool eviction → truncation) | [`ContextWindowCompactionStrategy`](#contextwindowcompactionstrategy) |
| Compact loaded context **before** the model runs **and** persisted history **after** | Wrap any of the above in [`CompactionProvider`](#compactionprovider) |
| One-shot compaction without a provider | [`apply_compaction(...)`](#apply_compactionmessages--strategy-tokenizernone) |

---

## Top-level exports

All of these are importable from `agent_framework` directly:

```python
from agent_framework import (
    CharacterEstimatorTokenizer,
    CompactionProvider,
    CompactionStrategy,
    ContextWindowCompactionStrategy,
    SelectiveToolCallCompactionStrategy,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    TokenizerProtocol,
    ToolResultCompactionStrategy,
    TruncationStrategy,
    annotate_message_groups,
    apply_compaction,
    included_messages,
    included_token_count,
    COMPACTION_STATE_KEY,
    EXCLUDED_KEY,
    EXCLUDE_REASON_KEY,
    GROUP_ANNOTATION_KEY,
    GROUP_HAS_REASONING_KEY,
    GROUP_ID_KEY,
    GROUP_INDEX_KEY,
    GROUP_KIND_KEY,
    GROUP_TOKEN_COUNT_KEY,
    SUMMARIZED_BY_SUMMARY_ID_KEY,
    SUMMARY_OF_GROUP_IDS_KEY,
    SUMMARY_OF_MESSAGE_IDS_KEY,
)
```

The following are defined in `_compaction.py` but are **private** — accessible only via `from agent_framework._compaction import ...` and treated as internal implementation details:

| Symbol | Why |
|---|---|
| `GroupKind` | `TypeAlias = Literal["system", "user", "assistant_text", "tool_call"]` — used in metadata; you usually compare string values |
| `group_messages(messages)` | Lower-level helper used by `annotate_message_groups` |
| `annotate_token_counts(messages, *, tokenizer)` | Companion to `annotate_message_groups`; called automatically by token-aware strategies |
| `project_included_messages(messages)` | Returns the filtered list `apply_compaction` returns; useful only if you're orchestrating compaction by hand |
| `extend_compaction_messages(state, messages)` / `append_compaction_message(state, message)` | Lower-level state-mutation helpers for `COMPACTION_STATE_KEY` |

Cited (`__all__` list): [`_compaction.py:L1395-L1429`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1395-L1429); top-level re-exports verified against [`agent_framework/__init__.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/__init__.py).

---

## The group model

Compaction operates on **groups of messages**, not individual messages — a single `tool_call` group typically contains the assistant's tool-call message *plus* the tool result message that must travel together. Splitting them would break the model's response contract.

A *group* is a contiguous run of messages assigned the same `_group.id` annotation. The four `GroupKind` values are:

| Kind | Example contents |
|---|---|
| `system` | A `Message(role="system", ...)` |
| `user` | A `Message(role="user", ...)` |
| `assistant_text` | An assistant message with no tool calls and no reasoning-only content |
| `tool_call` | An assistant message containing tool calls + its matching tool-result messages |

Cited: [`_compaction.py:L24`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L24) (the `GroupKind` alias) and [`L107-L218`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L107-L218) (`group_messages` implementation).

Strategies **never split a group**. They flip the per-message flag `additional_properties["_excluded"] = True` (key constant `EXCLUDED_KEY`) on every message inside an entire group at once.

### Annotation keys (constants)

Stored under each message's `additional_properties` dict:

| Constant | Where stored | Meaning |
|---|---|---|
| `GROUP_ANNOTATION_KEY` (`"_group"`) | per-message | Dict containing `GROUP_ID_KEY`, `GROUP_KIND_KEY`, `GROUP_INDEX_KEY`, optionally `GROUP_HAS_REASONING_KEY` / `GROUP_TOKEN_COUNT_KEY` |
| `EXCLUDED_KEY` (`"_excluded"`) | per-message | `True` ⇒ projection helpers skip this message |
| `EXCLUDE_REASON_KEY` (`"_exclude_reason"`) | per-message | Short string like `"truncation"`, `"sliding_window"`, `"summarized"`, `"token_budget_fallback"` |
| `SUMMARY_OF_MESSAGE_IDS_KEY` (`"_summary_of_message_ids"`) | summary message | List of original `message_id`s a summary replaces |
| `SUMMARY_OF_GROUP_IDS_KEY` (`"_summary_of_group_ids"`) | summary message | List of original group ids |
| `SUMMARIZED_BY_SUMMARY_ID_KEY` (`"_summarized_by_summary_id"`) | original message | Reverse pointer to summary that replaced it |
| `COMPACTION_STATE_KEY` (`"_compaction_messages"`) | session state | Where the provider's working buffer lives |

Cited: [`_compaction.py:L25-L36, L1152`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L25-L36).

---

## Strategies

All strategies satisfy the `CompactionStrategy` protocol:

```python
@runtime_checkable
class CompactionStrategy(Protocol):
    async def __call__(self, messages: list[Message]) -> bool: ...
```

The return value is `True` if any message inclusion or content changed during the call; `False` if nothing was touched. Cited: [`_compaction.py:L50-L63`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L50-L63).

Strategies are async because [`SummarizationStrategy`](#summarizationstrategy) calls a chat client; the others are CPU-bound but the protocol unifies them.

### `TruncationStrategy`

Drops whole groups oldest-first until a metric falls back to `compact_to`.

```python
class TruncationStrategy:
    def __init__(
        self,
        *,
        max_n: int,
        compact_to: int,
        tokenizer: TokenizerProtocol | None = None,
        preserve_system: bool = True,
    ) -> None: ...
```

Cited: [`_compaction.py:L623-L691`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L623-L691).

| Arg | Notes |
|---|---|
| `max_n` | Trigger threshold. Tokens if `tokenizer` given, else included-message count. Must be `> 0` ([`L653-L654`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L653-L654)) |
| `compact_to` | Target after trimming. Must satisfy `0 < compact_to <= max_n` ([`L655-L658`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L655-L658)) |
| `tokenizer` | Token-mode if supplied; count-mode otherwise |
| `preserve_system` | If `True` (default), system groups are never excluded |

```python
from agent_framework import CharacterEstimatorTokenizer, TruncationStrategy

# Trim when included tokens exceed 8000; bring back down to 4000
strategy = TruncationStrategy(
    max_n=8000,
    compact_to=4000,
    tokenizer=CharacterEstimatorTokenizer(),
)
```

### `SlidingWindowStrategy`

Keeps the last *N* non-system groups; drops older ones.

```python
class SlidingWindowStrategy:
    def __init__(self, *, keep_last_groups: int, preserve_system: bool = True) -> None: ...
```

Cited: [`_compaction.py:L694-L737`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L694-L737).

- `keep_last_groups` must be `> 0` ([`L714-L715`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L714-L715))
- System groups are kept as stable "anchors" when `preserve_system=True`

```python
from agent_framework import SlidingWindowStrategy

strategy = SlidingWindowStrategy(keep_last_groups=20)
```

### `SelectiveToolCallCompactionStrategy`

Targets **only `tool_call` groups**. Keeps the last *N* tool-call sequences; drops older. Leaves user/assistant chat untouched. Useful when tool chatter dominates token usage but you want to preserve the human conversation.

```python
class SelectiveToolCallCompactionStrategy:
    def __init__(self, *, keep_last_tool_call_groups: int = 1) -> None: ...
```

Cited: [`_compaction.py:L740-L790`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L740-L790).

- Default keeps **1** tool-call group
- Set `keep_last_tool_call_groups=0` to remove all included tool-call groups
- Must be `>= 0` ([`L762-L763`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L762-L763))

### `ToolResultCompactionStrategy`

Like the selective variant, but **replaces** old tool-call groups with a one-line summary message (e.g. `"[Tool results: get_weather: sunny, 18°C]"`) instead of just dropping them. Preserves a readable trace while reclaiming token overhead.

```python
class ToolResultCompactionStrategy:
    def __init__(self, *, keep_last_tool_call_groups: int = 1) -> None: ...
```

Cited: [`_compaction.py:L793-L892`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L793-L892).

### `SummarizationStrategy`

LLM-driven. When included non-system message count exceeds `target_count + threshold`, summarize the oldest groups with a chat client and replace them with a single summary message.

```python
class SummarizationStrategy:
    def __init__(
        self,
        *,
        client: SupportsChatGetResponse[Any],
        target_count: int = 4,
        threshold: int | None = 2,
        prompt: str | None = None,
    ) -> None: ...
```

Cited: [`_compaction.py:L922-L1061`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L922-L1061).

| Arg | Notes |
|---|---|
| `client` | Any object satisfying `SupportsChatGetResponse` — typically a `FoundryChatClient` |
| `target_count` | Aim to retain this many non-system messages after summarization. Must be `> 0` ([`L959-L960`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L959-L960)) |
| `threshold` | Extra messages allowed above `target_count` before triggering. `None` is normalized to `0`. Must be `>= 0` when given ([`L961-L962`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L961-L962)) |
| `prompt` | Custom system prompt; falls back to `DEFAULT_SUMMARIZATION_PROMPT` ([`L904-L919`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L904-L919)) |

> [!NOTE]
> If the chat client raises or returns empty text, the strategy logs a warning ("`Skipping summarization compaction: …`") and returns `False` without modifying messages ([`L1026-L1036`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1026-L1036)). Compaction is best-effort, not fail-fast.

### `TokenBudgetComposedStrategy`

Composes other strategies under a single token budget. Runs each in order, refreshing token counts between steps. If budget is still exceeded after every strategy, a deterministic fallback excludes oldest non-system groups; a strict-mode fallback eventually excludes system anchors too.

```python
class TokenBudgetComposedStrategy:
    def __init__(
        self,
        *,
        token_budget: int,
        tokenizer: TokenizerProtocol,
        strategies: Sequence[CompactionStrategy],
        early_stop: bool = True,
    ) -> None: ...
```

Cited: [`_compaction.py:L1064-L1133`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1064-L1133).

- `early_stop=True` (default): stop as soon as the budget is satisfied
- Fallback exclude-reasons: `"token_budget_fallback"` then `"token_budget_fallback_strict"`

```python
from agent_framework import (
    CharacterEstimatorTokenizer,
    SelectiveToolCallCompactionStrategy,
    SlidingWindowStrategy,
    TokenBudgetComposedStrategy,
)

tokenizer = CharacterEstimatorTokenizer()
strategy = TokenBudgetComposedStrategy(
    token_budget=6000,
    tokenizer=tokenizer,
    strategies=[
        SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=2),
        SlidingWindowStrategy(keep_last_groups=10),
    ],
)
```

---

### `ContextWindowCompactionStrategy`

> **NEW in 1.8.0** ([PR #6041](https://github.com/microsoft/agent-framework/pull/6041))

A token-budget compaction strategy tuned to a model's **context window**. Runs a two-phase pipeline internally — first evicting older tool results, then truncating older message groups — so prompts stay within the model's effective input budget without dropping the most recent tool-call group(s).

Used by [`create_harness_agent(...)`](../../patterns/harness-agent.md) as the default `before_strategy` (see harness source `_harness/_agent.py:L79`; new in 1.8.0 per PR #6041).

**Two-phase pipeline:**

1. **Tool-result eviction** — wraps [`ToolResultCompactionStrategy`](#toolresultcompactionstrategy) in a [`TokenBudgetComposedStrategy`](#tokenbudgetcomposedstrategy) keyed at `tool_eviction_threshold × max_input_tokens`. Trips first; preserves message structure while shedding heavy tool payloads.
2. **Truncation** — wraps [`TruncationStrategy`](#truncationstrategy) in a `TokenBudgetComposedStrategy` keyed at `truncation_threshold × max_input_tokens`. Trips only after tool eviction was insufficient.

The input budget is computed once at construction:

```
max_input_tokens = max_context_window_tokens - max_output_tokens
```

**Signature (keyword-only):**

```python
from agent_framework import ContextWindowCompactionStrategy, CompactionProvider

strategy = ContextWindowCompactionStrategy(
    max_context_window_tokens=128_000,   # required
    max_output_tokens=16_384,            # required
    # optional kwargs:
    tokenizer=None,                      # defaults to CharacterEstimatorTokenizer()
    tool_eviction_threshold=0.5,         # class default DEFAULT_TOOL_EVICTION_THRESHOLD
    truncation_threshold=0.8,            # class default DEFAULT_TRUNCATION_THRESHOLD
    keep_last_tool_call_groups=4,        # forwarded to ToolResultCompactionStrategy
)

provider = CompactionProvider(before_strategy=strategy)
```

**Construction-time validation** (raises `ValueError` on violation):

| Check | Rule |
|---|---|
| `max_context_window_tokens > 0` | Must be a positive integer |
| `0 <= max_output_tokens < max_context_window_tokens` | Output budget must leave room for input |
| `0.0 < tool_eviction_threshold <= 1.0` | Fraction of input budget |
| `0.0 < truncation_threshold <= 1.0` | Fraction of input budget |
| `truncation_threshold >= tool_eviction_threshold` | Truncation is the heavier hammer; trip later |

**Threshold semantics:**

| Threshold | Default | Meaning |
|---|---|---|
| `tool_eviction_threshold` | `0.5` | Tool-result eviction trips when the prompt would consume ≥ 50% of the input budget. |
| `truncation_threshold` | `0.8` | Truncation trips when the prompt would still consume ≥ 80% of the input budget after eviction. |

`async def __call__(messages) -> bool` returns `True` if compaction changed which messages are included (either eviction or truncation fired), `False` if the budget was already satisfied.

Cited: [`_compaction.py:L1280-L1392`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1280-L1392)

---

## Tokenizers

### `TokenizerProtocol`

```python
@runtime_checkable
class TokenizerProtocol(Protocol):
    def count_tokens(self, text: str) -> int: ...
```

Cited: [`_compaction.py:L41-L47`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L41-L47).

### `CharacterEstimatorTokenizer`

Heuristic: 4 characters ≈ 1 token. Cheap, always available, no dependency.

```python
class CharacterEstimatorTokenizer:
    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
```

Cited: [`_compaction.py:L66-L70`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L66-L70).

For production use, swap in a real BPE tokenizer (e.g. `tiktoken`) that satisfies the protocol.

---

## Helpers

### `included_messages(messages)`

```python
def included_messages(messages: list[Message]) -> list[Message]: ...
```

Returns messages where `additional_properties["_excluded"]` is not `True`. Useful for inspection. Cited: [`_compaction.py:L542-L544`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L542-L544).

### `included_token_count(messages)`

```python
def included_token_count(messages: list[Message]) -> int: ...
```

Sum of `_group["token_count"]` annotations across included messages. Requires `annotate_token_counts` to have run first (token-aware strategies do this automatically). Cited: [`_compaction.py:L546-L552`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L546-L552).

### `annotate_message_groups(messages, *, from_index=0, force_reannotate=False)`

Walks the messages and writes the `_group` annotation onto each, returning the ordered list of group ids. Idempotent unless `force_reannotate=True`. Cited: [`_compaction.py:L402-L463`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L402-L463). You rarely call this directly; strategies and `apply_compaction` do.

### `apply_compaction(messages, *, strategy, tokenizer=None)`

```python
async def apply_compaction(
    messages: list[Message],
    *,
    strategy: CompactionStrategy | None,
    tokenizer: TokenizerProtocol | None = None,
) -> list[Message]: ...
```

Annotates groups (and tokens if a tokenizer is given), runs the strategy in place, then **returns the projected included-messages list** (the original list still contains everything, with `_excluded` flags). Returns `messages` unchanged if `strategy is None`. Cited: [`_compaction.py:L1136-L1149`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1136-L1149).

```python
from agent_framework import apply_compaction, SlidingWindowStrategy

projected = await apply_compaction(
    messages=conversation,
    strategy=SlidingWindowStrategy(keep_last_groups=10),
)
# Pass `projected` to the model. `conversation` still has all messages
# with annotations for later inspection.
```

---

## `CompactionProvider`

Wraps two strategies into a `ContextProvider` ([`sessions.md`](sessions.md)) so the agent applies compaction automatically before and after each run.

```python
class CompactionProvider(ContextProvider):
    def __init__(
        self,
        *,
        before_strategy: CompactionStrategy | None = None,
        after_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        source_id: str = "compaction",
        history_source_id: str = "in_memory",
    ) -> None: ...
```

Cited: [`_compaction.py:L1155-L1278`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1155-L1278).

| Hook | What it does | Source |
|---|---|---|
| `before_run` | Reads messages currently in `context` (loaded by upstream providers like a history provider), annotates + applies `before_strategy`, then **filters** `context.context_messages[sid]` down to the projected set | [`L1222-L1246`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1222-L1246) |
| `after_run` | Reads stored messages from `session.state[history_source_id]["messages"]`, annotates + applies `after_strategy`. Keeps excluded messages in storage so annotations persist — the history provider's `skip_excluded` flag controls whether they are loaded next turn | [`L1248-L1277`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1248-L1277) |

Either strategy may be `None` to skip that phase.

### Canonical wiring

```python
from agent_framework import (
    CompactionProvider,
    InMemoryHistoryProvider,
    SlidingWindowStrategy,
    ToolResultCompactionStrategy,
)

history = InMemoryHistoryProvider()
compaction = CompactionProvider(
    before_strategy=SlidingWindowStrategy(keep_last_groups=20),
    after_strategy=ToolResultCompactionStrategy(keep_last_tool_call_groups=1),
    history_source_id=history.source_id,
)

agent = Agent(
    client=client,
    name="assistant",
    context_providers=[history, compaction],
)
```

**Order matters.** `history` runs first so it loads previous messages into the context; then `compaction.before_run` trims them. After the model runs, `compaction.after_run` shrinks the persisted history before the next turn.

> [!IMPORTANT]
> The `history_source_id` must match the history provider's `source_id` (default `"in_memory"` for `InMemoryHistoryProvider`). If it doesn't, `after_run` silently no-ops because `session.state[history_source_id]` returns `None` ([`L1261-L1263`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1261-L1263)).

---

## Common mistakes

| ❌ Wrong | ✅ Right | Why |
|---|---|---|
| `TruncationStrategy(max_n=8000)` (no `compact_to`) | `TruncationStrategy(max_n=8000, compact_to=4000)` | `compact_to` is a required keyword arg ([`L637-L638`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L637-L638)) |
| `TruncationStrategy(max_n=4000, compact_to=8000)` | `compact_to <= max_n` always | Raises `ValueError("compact_to must be less than or equal to max_n.")` ([`L657-L658`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L657-L658)) |
| `SlidingWindowStrategy(keep_last_groups=0)` | `keep_last_groups >= 1` (use `SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0)` for "drop all of kind X") | Raises `ValueError` ([`L714-L715`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L714-L715)) |
| Calling `included_token_count(messages)` without first running a tokenizer-aware strategy or `annotate_token_counts` | Use a token-aware strategy, or wrap in `apply_compaction(..., tokenizer=...)` | Returns 0 because the `token_count` annotation isn't written |
| `CompactionProvider(after_strategy=..., history_source_id="memory")` while using `InMemoryHistoryProvider` (whose default `source_id` is `"in_memory"`) | Pass `history_source_id=history.source_id` | After-run hook reads `session.state[history_source_id]` and silently no-ops on mismatch |
| Calling a strategy directly (`await TruncationStrategy(...)(messages)`) without first annotating groups | Wrap with `apply_compaction(...)`, or call `annotate_message_groups(messages)` first | Strategies assume groups are already annotated ([protocol note, `L56-L58`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L56-L58)) |
| Treating `SummarizationStrategy` failure as fatal | Treat compaction as best-effort | LLM failure is caught, logged, and skipped ([`L1026-L1036`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py#L1026-L1036)) |
| Reusing the same chat client for summarization that the agent uses | Pass a smaller/cheaper client to `SummarizationStrategy` (e.g. mini-class model) | The agent burns tokens summarizing with the same expensive model as primary inference |

---

## See also

- [`sessions.md`](sessions.md) — `ContextProvider` lifecycle, `before_run` / `after_run` hooks
- [`history-providers.md`](history-providers.md) — Why `history_source_id` must match
- [`serialization.md`](serialization.md) — Group annotations survive `to_dict()` because they live in `additional_properties`
- [`feature-stages.md`](feature-stages.md) — Stage / experimental terminology
- [`../../patterns/session-history-persistence.md`](../../patterns/session-history-persistence.md) — Canonical history + compaction wiring

---

**Upstream source**: [`python/packages/core/agent_framework/_compaction.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_compaction.py) (1429 LOC; all 7 strategies + `CompactionProvider` + `apply_compaction` covered)
