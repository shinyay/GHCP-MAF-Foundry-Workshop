# Settings: `load_settings` + `SecretString`

> Status: **Stable** — public top-level re-exports since 1.0; the internal module is `agent_framework._settings`.
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) at commit `950673b`
> Upstream source: [`python/packages/core/agent_framework/_settings.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py)

`load_settings` is the **canonical** way to pull configuration into Agent Framework apps. It replaces the older pydantic-settings-based `AFBaseSettings` (since 1.0). Two symbols are exported from the package root:

```python
from agent_framework import load_settings, SecretString  # ✅ public
```

Cited: top-level re-export at [`agent_framework/__init__.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/__init__.py) (`from ._settings import SecretString, load_settings`).

---

## Why a dedicated loader?

| Pain point | What `load_settings` does about it |
|---|---|
| Explicit constructor overrides mixed with env-var fallbacks gets messy fast | **`None` overrides are explicitly filtered out** ([`_settings.py:L221`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L221)) so callers can pass `None` for "use the env var if available" semantics. |
| Codespaces / Dev Containers inject env vars as `""` → silently masks real values | ⚠️ `load_settings` does **not** normalize empty strings — it accepts any value that is `is not None` ([`_settings.py:L243-L259`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L243-L259)), and `required_fields` only rejects `None` ([`L269-L276`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L269-L276)). See the canonical fill-only loader fix in [`anti-patterns/empty-env-vars-codespaces.md`](../../anti-patterns/empty-env-vars-codespaces.md) — apply that fix **before** calling `load_settings`. |
| Secrets in `repr()` leak into logs, traceback frames, Sentry breadcrumbs | `SecretString.__repr__` returns the literal string `"SecretString('**********')"` ([`_settings.py:L72-L74`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L72-L74)). **str(s) / f-string interpolation still print the real value** — this is a leak guard for `repr()` only, not a hard secret guard. |
| Mutually exclusive fields ("exactly one of `model_name` or `model_deployment`") need ad-hoc validation | `required_fields=[("model_name", "model_deployment")]` enforces it with a clear `SettingNotFoundError` ([`_settings.py:L280-L291`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L280-L291)). |

---

## Resolution priority

`load_settings` resolves each field independently. Highest priority wins; later sources are consulted only if the previous one didn't provide a value.

| Rank | Source | Notes |
|---|---|---|
| 1 | Explicit keyword `**overrides` | `None` values are **filtered out** (`_settings.py:L221`) so callers can pass `param=os.getenv("FOO")` without masking lower priorities. |
| 2 | `.env` file at `env_file_path` | **Only** consulted when `env_file_path=` is explicitly passed (`_settings.py:L213`). The function does not auto-discover `.env`. Missing file → `FileNotFoundError`. |
| 3 | Process environment (`<env_prefix><FIELD_NAME>`) | Field name is upper-cased (`_settings.py:L241`). Prefix is concatenated literally — include the trailing underscore yourself: `env_prefix="OPENAI_"`. |
| 4 | TypedDict class-level default | If the TypedDict has a class-level attribute matching the field name (`_settings.py:L263-L264`). |
| 5 | `None` | Used when none of the above resolved a value (`_settings.py:L266`). |

> [!IMPORTANT]
> `dotenv` is consulted **before** process env (rank 2 before rank 3). If you pass an explicit `.env` file path, its values override the parent process's environment. Pass `env_file_path=None` (the default) to leave precedence with `os.environ`.

---

## `load_settings` signature

```python
def load_settings(
    settings_type: type[SettingsT],
    *,
    env_prefix: str = "",
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
    required_fields: Sequence[str | tuple[str, ...]] | None = None,
    **overrides: Any,
) -> SettingsT: ...
```

Cited: [`_settings.py:L164-L172`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L164-L172).

| Parameter | Required | Behavior |
|---|---|---|
| `settings_type` | yes | A `TypedDict` subclass. Field names + type hints drive resolution. `total=False` is normal — most settings are optional. |
| `env_prefix` | no | Prefix concatenated onto `field_name.upper()`. Default `""`. |
| `env_file_path` | no | Path to a `.env` file. If passed but the file doesn't exist → `FileNotFoundError`. |
| `env_file_encoding` | no | Default `"utf-8"`. |
| `required_fields` | no | Sequence of `str` (must be non-`None`) or `tuple[str, ...]` (exactly one). |
| `**overrides` | no | Per-field values. `None` is dropped before merge (`_settings.py:L221`). |

### Type coercion (`_coerce_value`)

`_settings.py:L85-L115` performs minimal coercion from strings (since env vars are always strings):

- `int(value)` for `int` fields
- `float(value)` for `float` fields
- `value.lower() in ("true", "1", "yes", "on")` for `bool` fields
- `SecretString(value)` if the annotation `is` or `issubclass(..., SecretString)`
- Union types (`str | None`): tries each non-`None` arm until one coerces successfully
- Anything else: returned as-is (str)

### Override validation (`_check_override_type`)

`_settings.py:L118-L161` performs *override-only* validation (env-var values are never type-checked this strictly, since they're always strings):

| Override is… | Result |
|---|---|
| `None` | Accepted (then filtered out at `L221` anyway) |
| Callable (lazy token provider, etc.) | Accepted regardless of `field_type` |
| `str` for a `SecretString` field | Accepted (then coerced via `_coerce_value`) |
| `int` for a `float` field | Accepted (numeric promotion) |
| Any other type-mismatch | `ValueError("Invalid type for setting '<name>': expected <T>, got <U>.")` |

---

## `SecretString`

```python
class SecretString(str):
    def __repr__(self) -> str:
        return "SecretString('**********')"

    def get_secret_value(self) -> str:
        return str(self)
```

Cited: [`_settings.py:L52-L82`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L52-L82).

- Inherits from `str` — works anywhere a `str` is expected.
- `__repr__` masks; **everything else does not**. `print(secret)`, `f"key: {secret}"`, `json.dumps(secret)`, `logger.info("key=%s", secret)` all expose the real value.
- `get_secret_value()` is a thin compatibility shim for `pydantic.SecretStr` migrations — it returns `str(self)`.

> [!WARNING]
> `SecretString` is a **leak guard for `repr()`**, not a hard secret guard. If you log a settings dict via `logger.info("%s", settings)`, you're calling `__str__` on the dict which calls `__repr__` on the values — that path IS protected. But `logger.info("key=%s", settings["api_key"])` calls `__str__` on the SecretString directly and leaks the value. Use sparingly.

---

## Worked example: minimal

```python
from typing import TypedDict
from agent_framework import load_settings, SecretString


class OpenAISettings(TypedDict, total=False):
    api_key: SecretString | None
    model: str | None
    organization: str | None


settings = load_settings(
    OpenAISettings,
    env_prefix="OPENAI_",
    required_fields=["api_key", "model"],
)
# Reads OPENAI_API_KEY (coerced to SecretString), OPENAI_MODEL, OPENAI_ORGANIZATION
# Raises SettingNotFoundError if OPENAI_API_KEY or OPENAI_MODEL is unset.
```

## Worked example: mutually exclusive Foundry model fields

```python
from typing import TypedDict
from agent_framework import load_settings


class FoundrySettings(TypedDict, total=False):
    project_endpoint: str | None
    model_name: str | None
    model_deployment: str | None


# Exactly one of model_name / model_deployment must be set
settings = load_settings(
    FoundrySettings,
    env_prefix="FOUNDRY_",
    required_fields=["project_endpoint", ("model_name", "model_deployment")],
)
```

If both are set: `SettingNotFoundError("Only one of 'model_name', 'model_deployment' may be provided, but multiple were set: 'model_name', 'model_deployment'.")` ([`_settings.py:L286-L291`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L286-L291)).

If neither is set: `SettingNotFoundError("Exactly one of 'model_name', 'model_deployment' must be provided, but none was set.")` ([`_settings.py:L283-L285`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L283-L285)).

## Worked example: explicit `.env` file

```python
from typing import TypedDict
from pathlib import Path
from agent_framework import load_settings


class AppSettings(TypedDict, total=False):
    api_key: str | None
    model: str | None


env_path = Path(__file__).parent.parent / ".env"
settings = load_settings(
    AppSettings,
    env_prefix="APP_",
    env_file_path=str(env_path),  # required for `.env` to be consulted
)
```

The function does **not** auto-discover `.env` files (unlike `python-dotenv.load_dotenv()` with no args). You must pass the path explicitly.

## Worked example: lazy token provider override

```python
from typing import TypedDict, Callable
from agent_framework import load_settings


class ClientSettings(TypedDict, total=False):
    endpoint: str | None
    token_provider: Callable[[], str] | None


def get_token() -> str:
    return "fresh-token-each-call"


settings = load_settings(
    ClientSettings,
    endpoint="https://example.com",
    token_provider=get_token,  # callable accepted regardless of annotation arms
)
# settings["token_provider"]() => "fresh-token-each-call"
```

Cited: callable-override allowance at [`_settings.py:L128-L130`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L128-L130).

---

## Common mistakes

| ❌ Wrong | ✅ Right | Why |
|---|---|---|
| `os.environ["OPENAI_API_KEY"]` → `KeyError` | `load_settings(..., required_fields=["api_key"])` → clean `SettingNotFoundError` with actionable message | Provides a single error path with the env-var name in the message |
| `load_dotenv()` then `os.getenv("X")` returning `""` for blank values | First apply the fill-only fix from [`anti-patterns/empty-env-vars-codespaces.md`](../../anti-patterns/empty-env-vars-codespaces.md) to scrub `os.environ`, **then** call `load_settings(MyTypedDict)` *without* `env_file_path` | `load_settings` filters `None` overrides only — empty strings are accepted as if they were real values. **`.env` is checked before process env** ([`_settings.py:L243-L259`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L243-L259)), so passing `env_file_path=...` after a fill-only fix would let blank `.env` values override the cleaned process env |
| `repr(SecretString("x"))` *expected* to mask in `logger.info("%s", x)` | Use `logger.info("%r", settings)` so the dict's `__repr__` recurses into `SecretString.__repr__` | `__str__` (which `%s` calls) on a `SecretString` returns the raw value |
| `load_settings(MyType, env_file_path="/missing/.env")` → silent fallback expected | Wrap with `try: ... except FileNotFoundError:` or pass the path conditionally | If the path is passed but doesn't exist, the function raises `FileNotFoundError` ([`_settings.py:L214-L215`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py#L214-L215)) |
| `load_settings(MyType, model_deployment=None, model_name="gpt-5-4")` and assuming `None` masks env-var lookup for `model_deployment` | Same call works correctly | `None` overrides are filtered out (`L221`) so env-var resolution runs normally |
| Field `count: int` set via env var `APP_COUNT="3.5"` → expect `ValueError` | Use a `float` annotation or pre-validate | `_coerce_value` calls `int(value)` which raises; `load_settings` catches it and falls back to the raw string (`L258-L259`) |

---

## Relationship to provider-specific settings

Individual Agent Framework providers wrap `load_settings` for their own surfaces (e.g., `OpenAISettings`, `AzureOpenAISettings`). When you construct a `FoundryChatClient(...)` without explicit kwargs, it calls `load_settings(FoundrySettings, env_prefix="FOUNDRY_")` internally and resolves missing parameters from `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, etc.

The **practical implication**: setting `FOUNDRY_PROJECT_ENDPOINT` in your environment is sufficient — you don't need to read it yourself and pass it to the client constructor.

See [`clients.md`](clients.md) for the full per-provider env-var list.

---

## See also

- [`anti-patterns/empty-env-vars-codespaces.md`](../../anti-patterns/empty-env-vars-codespaces.md) — the canonical example of why this loader exists
- [`clients.md`](clients.md) — per-provider env-var mappings
- [`exceptions.md`](exceptions.md) — `SettingNotFoundError` in the framework exception hierarchy

---

**Upstream source**: [`python/packages/core/agent_framework/_settings.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_settings.py) (293 LOC, fully verified)
