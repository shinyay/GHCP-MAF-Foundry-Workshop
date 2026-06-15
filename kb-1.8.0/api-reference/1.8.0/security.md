# Security: Information-flow control for prompt injection defense

> [!IMPORTANT]
> **⚠️ The `agent_framework.security` module is experimental — `ExperimentalFeature.FIDES`.** All public **classes** (`SecureAgentConfig`, `LabelTrackingFunctionMiddleware`, `PolicyEnforcementFunctionMiddleware`, `ContentVariableStore`, `VariableReferenceContent`, `LabeledMessage`, `ContentLabel`, `IntegrityLabel`, `ConfidentialityLabel`, `InspectVariableInput`) are decorated with `@experimental(feature_id=ExperimentalFeature.FIDES)` and emit `ExperimentalWarning` when **instantiated or subclassed**. Several module-level **helper / tool functions** (including `combine_labels`, `check_confidentiality_allowed`, `get_current_middleware`, `set_quarantine_client`, `get_quarantine_client`, `store_untrusted_content`, `get_security_tools`, `quarantined_llm`, `inspect_variable`) are exported but **not** individually `@experimental`-decorated in 1.8.0 — they still belong to the FIDES surface and may change. See [`feature-stages.md`](feature-stages.md) for the warning model and how to silence / track the warning.

> Status: **Experimental — FIDES feature**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) at commit `950673b`
> Upstream source: [`python/packages/core/agent_framework/security.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py) (2686 LOC)

The security module implements **information-flow control (IFC)** to defend against prompt injection attacks. Every piece of content flowing through the agent is tagged with `IntegrityLabel` (trusted vs. untrusted) and `ConfidentialityLabel` (public/private/user-identity). Middleware tracks these labels through tool calls; policy enforcement blocks unsafe combinations; and two purpose-built tools (`quarantined_llm`, `inspect_variable`) let agents operate on untrusted data without exposing it to the main conversation.

---

## When to consider this module

| You face… | Use |
|---|---|
| Agent reads untrusted data (web scrapes, third-party APIs, user-uploaded files) | Wrap content in `VariableReferenceContent` via `store_untrusted_content` |
| Agent passes tool output between functions and you need to track if any of it was untrusted | `LabelTrackingFunctionMiddleware` |
| You want to block tools from running once the context is tainted | `PolicyEnforcementFunctionMiddleware` (or `SecureAgentConfig`) |
| You want a one-line drop-in for "secure agent" | [`SecureAgentConfig`](#secureagentconfig-the-drop-in-entry-point) — adds middleware + tools + instructions |
| You need to summarize / extract from untrusted data without polluting context | [`quarantined_llm`](#tools-quarantined_llm-and-inspect_variable) |
| You need to deliberately expose stored untrusted content (use sparingly) | [`inspect_variable`](#tools-quarantined_llm-and-inspect_variable) |

> [!NOTE]
> All of the above is optional. Agents work without any security module imported. The defenses apply only when you opt in.

---

## Public surface

```python
from agent_framework.security import (
    # Constants
    SECURITY_TOOL_INSTRUCTIONS,
    # Enums
    IntegrityLabel,           # TRUSTED / UNTRUSTED
    ConfidentialityLabel,     # PUBLIC / PRIVATE / USER_IDENTITY
    # Value objects
    ContentLabel,
    ContentVariableStore,
    VariableReferenceContent,
    LabeledMessage,
    # Middleware
    LabelTrackingFunctionMiddleware,
    PolicyEnforcementFunctionMiddleware,
    # Drop-in
    SecureAgentConfig,
    # Tool input schemas
    InspectVariableInput,
    # Pure helpers
    combine_labels,
    check_confidentiality_allowed,
    # Tools
    quarantined_llm,
    inspect_variable,
    # Storage helpers
    store_untrusted_content,
    get_security_tools,
    # Runtime helpers
    set_quarantine_client,
    get_quarantine_client,
    get_current_middleware,
)
# Defined in the module but NOT in __all__ (still importable):
# from agent_framework.security import get_variable_store, set_variable_store
```

Cited (`__all__`): [`security.py:L40-L61`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L40-L61). The two storage accessors `get_variable_store` and `set_variable_store` are defined ([`L2644`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2644), [`L2653`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2653)) but **not** in `__all__` — they remain importable directly.

The module is `agent_framework.security` (public package); the contents are still experimental. Symbols are **not** re-exported from the top-level `agent_framework` namespace — you must import via `agent_framework.security.*`.

---

## Labels

### `IntegrityLabel`

```python
class IntegrityLabel(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
```

Cited: [`security.py:L77-L91`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L77-L91). Subclasses `str`, so values compare equal to their string forms.

### `ConfidentialityLabel`

```python
class ConfidentialityLabel(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    USER_IDENTITY = "user_identity"
```

Cited: [`security.py:L94-L110`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L94-L110).

Internal ordering for "most restrictive" comparisons:

| Level | Rank |
|---|---|
| `PUBLIC` | 0 |
| `PRIVATE` | 1 |
| `USER_IDENTITY` | 2 |

Cited (priority table used by `combine_labels` and `check_confidentiality_allowed`): [`security.py:L234-L238`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L234-L238), [`L299-L303`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L299-L303).

### `ContentLabel`

```python
class ContentLabel(SerializationMixin):
    def __init__(
        self,
        integrity: IntegrityLabel = IntegrityLabel.TRUSTED,
        confidentiality: ConfidentialityLabel = ConfidentialityLabel.PUBLIC,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    def is_trusted(self) -> bool: ...
    def is_public(self) -> bool: ...
```

Cited: [`security.py:L113-L195`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L113-L195).

Constructor accepts either enum members or their string equivalents (coerced via the enum constructor). `metadata` is an arbitrary dict for carrying user IDs, source URLs, etc.

```python
from agent_framework.security import (
    ContentLabel,
    IntegrityLabel,
    ConfidentialityLabel,
)

trusted_public = ContentLabel(
    integrity=IntegrityLabel.TRUSTED,
    confidentiality=ConfidentialityLabel.PUBLIC,
)

untrusted_private = ContentLabel(
    integrity=IntegrityLabel.UNTRUSTED,
    confidentiality=ConfidentialityLabel.PRIVATE,
    metadata={"user_id": "user-123", "source": "https://example.com/api"},
)
```

---

## Pure helpers

### `combine_labels(*labels) -> ContentLabel`

```python
def combine_labels(*labels: ContentLabel) -> ContentLabel: ...
```

Cited: [`security.py:L198-L250`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L198-L250).

Most-restrictive policy:

- **Integrity**: `UNTRUSTED` if **any** input is `UNTRUSTED`, else `TRUSTED`.
- **Confidentiality**: `max(...)` by the ranking above (so combining `PRIVATE` and `PUBLIC` gives `PRIVATE`).
- **Metadata**: merged via `dict.update` in argument order; later labels overwrite earlier ones for duplicate keys.

`combine_labels()` with no arguments returns `ContentLabel()` (TRUSTED/PUBLIC).

```python
from agent_framework.security import combine_labels

result = combine_labels(trusted_public, untrusted_private)
# result.integrity == IntegrityLabel.UNTRUSTED
# result.confidentiality == ConfidentialityLabel.PRIVATE
# result.metadata merged from both
```

### `check_confidentiality_allowed(context_label, max_allowed) -> bool`

```python
def check_confidentiality_allowed(
    context_label: ContentLabel,
    max_allowed: ConfidentialityLabel,
) -> bool: ...
```

Cited: [`security.py:L253-L305`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L253-L305).

Returns `True` when `rank(context_label.confidentiality) <= rank(max_allowed)`. Use to prevent data exfiltration: e.g. block a tool that posts to a public webhook when the agent's current context contains `PRIVATE` data.

```python
public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)

assert check_confidentiality_allowed(public_label, ConfidentialityLabel.PUBLIC) is True
assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PUBLIC) is False
assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PRIVATE) is True
```

---

## Containers

### `ContentVariableStore`

In-process storage for untrusted content. `store(content, label)` returns a `variable_id`; `retrieve(variable_id)` returns `(content, label)`. Backed by a global instance (`_global_variable_store`) that can be replaced via `set_variable_store(...)`. `LabelTrackingFunctionMiddleware` keeps its own per-middleware store as well.

Cited: [`security.py:L308-L393`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L308-L393).

### `VariableReferenceContent`

A `Content` subclass that the model sees in place of actual untrusted text:

```
VariableReferenceContent(variable_id='var_abc123', description='Result from fetch_data')
```

Cited: [`security.py:L395-L476`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L395-L476).

The agent cannot read the underlying bytes — only the reference. It must use `quarantined_llm` or `inspect_variable` to operate on the hidden content.

### `LabeledMessage`

Extends `Message` to carry a `ContentLabel`. Inference rules when label is omitted:

| Role | Default label |
|---|---|
| `user` | `TRUSTED` + `PUBLIC` |
| `system` | `TRUSTED` + `PUBLIC` |
| `assistant` | `combine_labels(*source_labels)` (or `TRUSTED` + `PUBLIC` if no sources) |
| `tool` | `UNTRUSTED` + `PUBLIC` |
| unknown / other | `UNTRUSTED` (fail-safe) |

Cited: [`security.py:L478-L665`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L478-L665).

---

## Middleware

Both middleware classes implement `FunctionMiddleware` from [`middleware.md`](middleware.md). They are designed to be installed together (label-tracker first, policy-enforcer second), which is exactly what `SecureAgentConfig` does for you.

### `LabelTrackingFunctionMiddleware`

Propagates labels through tool calls using a **3-tier resolution** (highest precedence first):

| Tier | Source | Where to set |
|---|---|---|
| 1 | Per-content embedded label in `additional_properties["security_label"]` | Set by upstream code that knows the truth (e.g. an HTTP fetcher tagging its response as `UNTRUSTED`) |
| 2 | Tool-declared `source_integrity` | Set on the tool: `@tool(additional_properties={"source_integrity": "untrusted"})` |
| 3 | Join of input argument labels via `combine_labels(...)` | Implicit fallback |

Cited: [`security.py:L792-L1100`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L792-L1100).

Key defaults on construction:

- `auto_hide_untrusted=True` — when `True`, the middleware automatically rewrites tool results whose label exceeds `hide_threshold` (default `IntegrityLabel.UNTRUSTED`) by storing them in the variable store and returning a `VariableReferenceContent` in their place.
- `default_integrity=IntegrityLabel.UNTRUSTED` — applied to tool calls without an explicit declaration.
- `default_confidentiality=ConfidentialityLabel.PUBLIC`.

The middleware also exposes `get_security_tools()`, `get_security_instructions()`, `get_variable_store()`, `get_variable_metadata(var_id)`, `list_variables()`.

Use `get_current_middleware()` to retrieve the currently-active middleware instance from inside a tool (returns `None` if the middleware isn't installed). Cited: [`security.py:L1517-L1525`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L1517-L1525).

### `PolicyEnforcementFunctionMiddleware`

Blocks tool execution when the context is tainted (label is `UNTRUSTED`) unless the tool name is in `allow_untrusted_tools`. Constructor flags:

| Flag | Default | Effect |
|---|---|---|
| `allow_untrusted_tools` | `set()` | Names of tools always allowed to run, even with `UNTRUSTED` input |
| `block_on_violation` | `True` | Raise/terminate the function call instead of executing |
| `approval_on_violation` | `False` | When `True`, **overrides** `block_on_violation` and triggers a function-approval request (UI affordance) instead of hard-blocking |
| `enable_audit_log` | `True` | Append violation records (retrievable via `get_audit_log()`) |

Cited: [`security.py:L1528-L1700`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L1528-L1700).

---

## `SecureAgentConfig` — the drop-in entry point

`SecureAgentConfig` is a `ContextProvider`, so you wire it like any other provider — no extra hooking. It composes label-tracker middleware + policy-enforcer middleware + the two security tools + security instructions, all injected via `before_run`.

```python
class SecureAgentConfig(ContextProvider):
    DEFAULT_SOURCE_ID = "secure_agent"

    def __init__(
        self,
        auto_hide_untrusted: bool = True,
        default_integrity: IntegrityLabel = IntegrityLabel.UNTRUSTED,
        default_confidentiality: ConfidentialityLabel = ConfidentialityLabel.PUBLIC,
        allow_untrusted_tools: set[str] | None = None,
        block_on_violation: bool = True,
        approval_on_violation: bool = False,
        enable_audit_log: bool = True,
        enable_policy_enforcement: bool = True,
        quarantine_chat_client: SupportsChatGetResponse | None = None,
        source_id: str | None = None,
    ) -> None: ...
```

Cited: [`security.py:L1928-L2113`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L1928-L2113).

**What it does in `before_run` (per turn)**:

1. `context.extend_tools(self.source_id, [quarantined_llm, inspect_variable])`
2. `context.extend_instructions(self.source_id, SECURITY_TOOL_INSTRUCTIONS)`
3. `context.extend_middleware(self.source_id, [label_tracker, policy_enforcer])`

If `quarantine_chat_client` is provided at construction, it calls `set_quarantine_client(...)` to register the client globally so `quarantined_llm` makes real isolated LLM calls (otherwise the tool returns a placeholder).

**Two-tool allow-list always active**: `quarantined_llm` and `inspect_variable` are auto-included in `allow_untrusted_tools` so the agent can always use them even in tainted context ([`L2010-L2013`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2010-L2013)).

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.security import SecureAgentConfig
from azure.identity.aio import AzureCliCredential

async def build_secure_agent():
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(
            project_endpoint="<endpoint>",
            model="gpt-5-4",
            credential=credential,
        ) as client,
    ):
        # Optional: separate cheaper client for quarantine
        async with FoundryChatClient(
            project_endpoint="<endpoint>",
            model="gpt-5-4",
            credential=credential,
        ) as quarantine_client:
            security = SecureAgentConfig(
                allow_untrusted_tools={"fetch_external_data"},
                quarantine_chat_client=quarantine_client,
            )

            async with client.as_agent(
                instructions="You are a helpful assistant.",
                tools=[my_tool],
                context_providers=[security],
            ) as agent:
                result = await agent.run("Summarize the latest news from this URL")
```

---

## Tools: `quarantined_llm` and `inspect_variable`

Both are top-level `@tool`-decorated functions that the agent can call.

### `quarantined_llm`

Makes an isolated LLM call (`tool_choice="none"`) with labeled data, using the **module-global** `_quarantine_chat_client`. The result is automatically marked `UNTRUSTED` because the tool's `additional_properties["source_integrity"] = "untrusted"`, so the label-tracker hides the response in the variable store if `auto_hide_untrusted=True`. Cited: [`security.py:L2241-L2473`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2241-L2473).

Signature (as the model sees it):

```text
quarantined_llm(prompt: str, variable_ids: list[str]) -> dict
```

- `prompt`: instruction (e.g. "Summarize the key points from this data")
- `variable_ids`: list of variable IDs whose content should be loaded into the quarantined call

If no quarantine client is registered (`_quarantine_chat_client is None`), the tool returns a **placeholder** result rather than making a real call. Register a client via either `set_quarantine_client(client)` or `SecureAgentConfig(quarantine_chat_client=...)`.

### `inspect_variable`

```text
inspect_variable(variable_id: str, reason: str | None = None) -> dict
```

Cited: [`security.py:L2488-L2593`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2488-L2593).

Decorator config: `approval_mode="never_require"`, `additional_properties={"confidentiality": "private"}`. Deliberately **no `source_integrity` declaration**, so the tool's output inherits the label of the inspected variable via Tier 3.

Reveals stored untrusted content into the agent's context and **taints the context** to `UNTRUSTED` (via Tier 3). Logs a `WARNING`-level audit entry on every call (`"SECURITY AUDIT: Variable {variable_id} inspected. Label: {label}. Reason: {reason}"`).

Returns:

```text
{
    "variable_id": "var_abc123",
    "content": <stored content>,
    "security_label": {"integrity": "untrusted", "confidentiality": "public", "metadata": {...}},
    "warning": "This content has been marked as UNTRUSTED ...",
    "inspected": True,
    "metadata": {"function_name": ..., "turn": ..., "timestamp": ...}  # if middleware available
}
```

Missing variable → returns a dict with `error` and `security_label: None` ([`L2587-L2593`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2587-L2593)) — does **not** raise.

### `SECURITY_TOOL_INSTRUCTIONS`

A multi-paragraph system prompt that teaches the model how to recognize `VariableReferenceContent` and how to call `quarantined_llm` / `inspect_variable` correctly. `SecureAgentConfig.get_instructions()` returns this string and injects it via `context.extend_instructions(...)`. Cited: [`security.py:L2170-L2238`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2170-L2238).

---

## Storage helpers

```python
def store_untrusted_content(
    content: Any,
    label: ContentLabel | None = None,
    description: str | None = None,
) -> VariableReferenceContent: ...

def get_variable_store() -> ContentVariableStore: ...
def set_variable_store(store: ContentVariableStore) -> None: ...
def get_security_tools() -> list[FunctionTool]: ...
def set_quarantine_client(client: SupportsChatGetResponse | None) -> None: ...
def get_quarantine_client() -> SupportsChatGetResponse | None: ...
def get_current_middleware() -> LabelTrackingFunctionMiddleware | None: ...
```

Cited: [`security.py:L2596-L2686`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2596-L2686), [`L2127-L2166`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2127-L2166).

`store_untrusted_content` is the typical entry point for code that fetches external data:

```python
from agent_framework.security import (
    store_untrusted_content,
    ContentLabel,
    IntegrityLabel,
)

api_payload = await client.get("https://example.com/api")
ref = store_untrusted_content(
    api_payload,
    label=ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
    description="External API response",
)
# ref is a VariableReferenceContent — safe to add to the LLM context
```

---

## Common mistakes

| ❌ Wrong | ✅ Right | Why |
|---|---|---|
| `from agent_framework import SecureAgentConfig` | `from agent_framework.security import SecureAgentConfig` | Security symbols are not re-exported at the top level |
| Calling / instantiating without acknowledging the `ExperimentalWarning` | Catch / silence the warning with the standard pattern; document the FIDES dependency | Public **classes** are `@experimental(FIDES)` and warn on instantiation/subclassing — see [`feature-stages.md`](feature-stages.md) |
| Adding `SecureAgentConfig` to `context_providers` *and* manually adding `quarantined_llm` to `tools=[...]` | Add to `context_providers` only; tools/instructions/middleware are auto-injected via `before_run` | The drop-in is comprehensive; double-adding creates duplicate middleware and warnings |
| `SecureAgentConfig(allow_untrusted_tools={"quarantined_llm"})` (already auto-allowed) | Leave them out; `quarantined_llm` + `inspect_variable` are union'd in automatically | Code noise; redundant allowances ([`L2010-L2013`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L2010-L2013)) |
| Using the same chat client for `quarantine_chat_client` as the primary agent | Pass a separate cheaper client (e.g. mini-class model) | The quarantine path processes untrusted content; cost + blast radius reasons (see the constructor docstring at [`L1992-L1996`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py#L1992-L1996)) |
| Trusting `inspect_variable` results in the same context | Treat the agent's context as `UNTRUSTED` after any `inspect_variable` call; defensive instructions for the agent should already be in `SECURITY_TOOL_INSTRUCTIONS` | The tool taints the context via Tier 3 by design |
| Configuring `block_on_violation=False` and `approval_on_violation=False` to silence policy | Either keep `block_on_violation=True`, or set `approval_on_violation=True` for UI approval | With both off, policy violations are reported but **not enforced** — defeats the purpose |
| Wiring `SecureAgentConfig` but **not** marking external-API tools' results — defenses rely on labels existing | Either set `additional_properties["security_label"] = ContentLabel(...)` on returned content, declare `source_integrity` on the tool, or wrap responses with `store_untrusted_content` | Otherwise Tier 1 and Tier 2 silently miss; you fall to Tier 3 (input-join) which under-flags external data |

---

## See also

- [`feature-stages.md`](feature-stages.md) — `@experimental(FIDES)` warning model
- [`middleware.md`](middleware.md) — `FunctionMiddleware` protocol and ordering rules
- [`sessions.md`](sessions.md) — `ContextProvider` lifecycle (`before_run` / `after_run`)
- [`tools-function.md`](tools-function.md) — `@tool` decorator and `additional_properties`

---

**Upstream source**: [`python/packages/core/agent_framework/security.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/security.py) (2686 LOC; all 10 public classes + 8 functions verified)
