# Feature stages: stable, experimental, and release candidate APIs

> Status: **Stable** — the staging mechanism itself has been stable since 1.0; the **APIs** it gates change between minor versions.
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: upstream tag [`python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) at commit `950673b`
> Upstream source: [`python/packages/core/agent_framework/_feature_stage.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py)

This page answers three operational questions:

1. **"Is this API stable?"** → check the per-symbol staging tag in the source / KB; see the matrix below.
2. **"Why am I seeing `[FOUNDRY_TOOLS] ... ExperimentalWarning`?"** → see [Warning hierarchy](#warning-hierarchy) and [Managing warnings](#managing-warnings).
3. **"What changes when an API moves out of experimental?"** → see [Lifecycle](#lifecycle) — short answer: the warning disappears, the API stays.

---

## Three stages, two enums, one decorator family

Agent Framework 1.8.0 publicly exports **two** feature-stage enums and **zero** decorators / warning classes at the package root:

```python
from agent_framework import ExperimentalFeature, ReleaseCandidateFeature  # ✅ public
```

The decorators (`@experimental`, `@release_candidate`) and the warning classes (`ExperimentalWarning`, `FeatureStageWarning`) live in the **private** module `agent_framework._feature_stage` and are intentionally not re-exported. See [Filtering experimental warnings](#filtering-experimental-warnings) for what to do when you need them anyway.

### Adaptive Evals and MCPSkillsSource — NEW in 1.8.0

Two `@experimental` features were added in 1.8.0 that you will see flagged by the warning hierarchy:

| Symbol | Stage | Feature id | Where |
|---|---|---|---|
| Adaptive Evals consumer surface — `GeneratedEvaluatorRef`, `RubricScore`, `EvalResults.assert_*` helpers, `FoundryEvals(evaluators=[ref, ...])` ([PR #6101](https://github.com/microsoft/agent-framework/pull/6101)) | `@experimental` | `ExperimentalFeature.EVALS` | [`evaluation.md`](evaluation.md) |
| `MCPSkillsSource` (load Foundry / external skill catalogues over MCP — uppercase `MCP`, top-level export of `agent_framework`) | `@experimental` | `ExperimentalFeature.SKILLS` | [`skills.md`](skills.md) |

Both emit one `ExperimentalWarning` per `(category, feature_id)` per process — silence individually with `warnings.filterwarnings("ignore", category=ExperimentalWarning, module=r"agent_framework\._feature_stage")` or track upgrades by leaving the warning enabled in CI.

| Stage | Decorator | Warning at runtime? | Stage attr |
|---|---|---|---|
| **Stable** | none | no | `__feature_stage__` not set |
| **Experimental** | `@experimental(feature_id=...)` | yes — once per `(category, feature_id)` per process | `"experimental"` |
| **Release candidate** | `@release_candidate(feature_id=...)` | **no** in 1.8.0 (decorator's `warning_category` is `None`) | `"release_candidate"` |

Cited: `_feature_stage.py:`[`L181-L228`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L181-L228) (`experimental`), [`L231-L257`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L231-L257) (`release_candidate`), [`L112-L129`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L112-L129) (warn-once dedup).

---

## `ExperimentalFeature` — 8 categories in 1.8.0

Source: [`_feature_stage.py:L39-L56`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L39-L56)

| Feature ID | Subsystem | KB page | Where the decorator is applied |
|---|---|---|---|
| `EVALS` | LLM evaluation framework | [`evaluation.md`](evaluation.md) | every public symbol in `core/_evaluation.py` + `foundry/_foundry_evals.py` |
| `FILE_HISTORY` | File-backed conversation history | — | history provider primitives |
| `FIDES` | Threat/abuse detection (`agent_framework.security`) | `security.md` *(coming in PR-I)* | `core/security.py` |
| `FOUNDRY_TOOLS` | Foundry hosted tools (lower preview tier) | [`tools-hosted.md`](tools-hosted.md) | `get_bing_grounding_tool`, `get_azure_ai_search_tool` |
| `FOUNDRY_PREVIEW_TOOLS` | Foundry hosted tools (higher preview tier) | [`tools-hosted.md`](tools-hosted.md) | `get_bing_custom_search_tool`, `get_sharepoint_tool`, `get_fabric_tool`, `get_memory_search_tool`, `get_computer_use_tool`, `get_browser_automation_tool`, `get_a2a_tool` |
| `FUNCTIONAL_WORKFLOWS` | `@workflow` / `@executor` decorators | [`workflow-internals.md`](workflow-internals.md) | `core/_workflows/_functional.py` |
| `HARNESS` | Agent test harness (memory provider, mode, todo store) | — | `core/_harness/{_memory,_mode,_todo}.py` |
| `SKILLS` | Skill registry & loaders | [`skills.md`](skills.md) | `core/_skills.py` |

**`FOUNDRY_TOOLS` vs `FOUNDRY_PREVIEW_TOOLS`** — Both are experimental in 1.8.0. The split exists so callers can suppress one tier without the other; the source does not explicitly grade one as "safer than" the other. Treat both as subject to change.

---

## `ReleaseCandidateFeature` — empty in 1.8.0

Source: [`_feature_stage.py:L59-L67`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L59-L67)

```python
class ReleaseCandidateFeature(str, Enum):
    """Identifiers for features in release candidate stage."""
```

The enum is exported and documented for forward compatibility, but contains **no members** in 1.8.0. The `@release_candidate(...)` decorator also does **not emit a runtime warning** (its `warning_category` is `None`); it only attaches the `__feature_stage__ = "release_candidate"` attribute and adds a `.. warning:: Release Candidate` block to the docstring.

If you grep for `@release_candidate` in `python-1.8.0`, you will find **zero hits**. The slot exists for 1.x → 2.0 transitions; no API is currently using it.

---

## Warning hierarchy

```
Warning                         (built-in)
  └── FutureWarning             (built-in)
      └── FeatureStageWarning   agent_framework._feature_stage (private)
          └── ExperimentalWarning  agent_framework._feature_stage (private)
```

Cited: [`_feature_stage.py:L94-L103`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L94-L103)

Two consequences:

1. **`warnings.filterwarnings(category=FutureWarning, ...)` already catches every experimental warning.** This is the simplest cross-version-safe filter — no private import required, no risk if `_feature_stage` is refactored.
2. **`warnings.filterwarnings(category=ExperimentalWarning, ...)` is more precise but requires importing from a private module.** See the trade-off below.

### Warning message format

Every `ExperimentalWarning` message starts with `[<FEATURE_ID>]` and names the wrapped symbol. Verified in upstream tests ([`test_feature_stage.py:L72-L74`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/tests/core/test_feature_stage.py#L72-L74)):

```
[FOUNDRY_TOOLS] FoundryChatClient.get_bing_grounding_tool is experimental and may change or be removed in future versions without notice.
```

The `[FEATURE_ID]` prefix is what enables the message-based filter recipe below.

### Warn-once-per-feature semantics

The decorator uses a module-level `_WARNED_FEATURES: set[tuple[type[Warning], str]]` keyed on `(warning category, feature_id value)`. Cited: [`_feature_stage.py:L112-L129`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L112-L129).

**What this means in practice:**

* The **first** call to any `@experimental(FOUNDRY_TOOLS)` API emits one warning. **Every subsequent** call to any `FOUNDRY_TOOLS`-tagged symbol — same one or a different one — emits **nothing** for the rest of the process.
* `warnings.catch_warnings(): warnings.simplefilter("ignore")` does **not** restore the dedup set. If the first use happens inside a suppression block, the warning is silently consumed and never re-fires outside the block either. **Install your filters before the first experimental API call.**
* Convert-to-error mode (`warnings.simplefilter("error")`) raises **before** `_WARNED_FEATURES.add(...)` runs, so subsequent calls keep raising — useful for CI. Cited: [`_feature_stage.py:L122-L129`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L122-L129).
* The cache is **per interpreter process**: subprocesses (`multiprocessing`, `subprocess.Popen` of a fresh Python), pytest workers (e.g. `pytest-xdist`), and import-isolated test runs each get their own empty cache. Threads within one process **share** the same cache (and so share the warn-once gate).

---

## Introspection

Decorated functions and classes carry two attributes you can probe at runtime to audit a codebase or write a custom lint:

```python
from agent_framework.foundry import FoundryChatClient

stage = getattr(FoundryChatClient.get_bing_grounding_tool, "__feature_stage__", None)
feature = getattr(FoundryChatClient.get_bing_grounding_tool, "__feature_id__", None)

assert stage == "experimental"
assert feature == "FOUNDRY_TOOLS"
```

Verified in [`test_feature_stage.py:L75-L76`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/tests/core/test_feature_stage.py#L75-L76).

**Caveats from the source docstring** ([`_feature_stage.py:L186-L194`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L186-L194)):

> The `__feature_stage__` and `__feature_id__` markers are best-effort metadata. They are useful for static introspection and CI gating, **but they may disappear when a feature is released to stable** (the decorator is simply removed in source). Do not depend on them as a long-lived contract.

For Protocol classes (e.g. those that need to remain `runtime_checkable`), wrapping is skipped entirely to preserve `isinstance()` / `issubclass()` semantics — and the framework also **does not** attach `__feature_stage__` / `__feature_id__` to them. The docstring is still annotated, but you cannot introspect Protocol classes the same way as other decorated objects. Cited: [`_feature_stage.py:L253-L256`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L253-L256).

---

## Managing warnings

The default Python warning behavior is `"default"` — show each warning once per call site. Combined with the framework's per-feature dedup, that means you typically see **one** line per experimental subsystem in a long-running process. Most apps can leave that alone.

You need to manage warnings explicitly when:

* You want to **silence** them in a controlled scope (e.g. you have audited an experimental API and are intentionally relying on it).
* You want to **upgrade** them to errors in CI to catch silent reliance on experimental APIs before deployment.
* You want to **route** them somewhere other than stderr (e.g. logging).

### Filtering experimental warnings

There are two filter styles. **Prefer the message-regex form** because it does not require importing from a private module.

#### Recipe 1 — message regex (no private import; recommended)

```python
import warnings

# Silence everything tagged FOUNDRY_TOOLS (typical: you've audited the
# Bing grounding factory and accept the API churn risk for this app).
warnings.filterwarnings(
    "ignore",
    message=r"^\[FOUNDRY_TOOLS\]",
    category=FutureWarning,  # parent class — works without private import
)
```

The `[FOUNDRY_TOOLS]` prefix is part of the warning message format (verified above), so this is stable as long as the prefix convention is kept. It is also future-proof against the warning class being re-homed.

#### Recipe 2 — category filter (precise; requires private import)

```python
import warnings

# Private import — see WARNING below
from agent_framework._feature_stage import ExperimentalWarning

warnings.filterwarnings("ignore", category=ExperimentalWarning)
```

> [!WARNING]
> `agent_framework._feature_stage` is a **private** module (leading underscore). Importing `ExperimentalWarning` from it works in 1.8.0 but is not part of the public API contract; it may move, get renamed, or be re-exported elsewhere in a future minor version. If you take this path, pin `agent-framework-foundry` to an exact version and re-verify on upgrade.
>
> The category-form is also wider than the message-form: it suppresses **every** feature ID (`FOUNDRY_TOOLS`, `EVALS`, `SKILLS`, …) in a single filter unless you also pass `message=`.

### Warnings-as-errors for CI

Catch silent reliance on experimental APIs by turning the parent `FutureWarning` into an error during tests.

> [!IMPORTANT]
> The framework emits its warnings with `stacklevel=3` ([`_feature_stage.py:L153,L174,L188,L203`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py#L153)), so each warning is attributed to **your call site** — not to `agent_framework`. A `module:agent_framework` warning filter will **not** match. Use **message-based** filtering instead — every framework experimental warning starts with `[FEATURE_ID]`:

```toml
# pyproject.toml [tool.pytest.ini_options]
filterwarnings = [
    # Promote every framework experimental warning to an error in CI
    "error:^\\[[A-Z_]+\\].*:FutureWarning",
]
```

Or narrow to a single subsystem:

```toml
filterwarnings = [
    "error:^\\[FOUNDRY_TOOLS\\].*:FutureWarning",
    "error:^\\[EVALS\\].*:FutureWarning",
]
```

Once an experimental dependency leaks into a test, the first call raises a `FutureWarning` and the test fails with the `[FEATURE_ID] symbol is experimental and may change …` message — telling you exactly which subsystem to audit.

> [!IMPORTANT]
> When `FutureWarning` is raised as an error, the framework's warn-once cache is **not** updated (the `_WARNED_FEATURES.add(...)` line runs after `warnings.warn(...)`). Subsequent calls keep raising. That's the intended behavior for CI — every call site is flagged independently.

### Routing warnings to a logger

```python
import logging
import warnings

logging.captureWarnings(True)  # warnings → "py.warnings" logger
logging.getLogger("py.warnings").setLevel(logging.INFO)
```

This works for any `FutureWarning` subclass, including the framework's experimental warnings, without needing the private classes.

### Scoped suppression with `catch_warnings`

```python
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=FutureWarning)
    tool = client.get_bing_grounding_tool(connection_id=conn_id)  # silent

# Outside the block, the per-process dedup may already mark FOUNDRY_TOOLS as warned,
# so future calls to other FOUNDRY_TOOLS APIs will still be silent in this process.
```

This is the **only** correct usage that doesn't subtly mislead. The dedup set is process-global and is not restored when you exit the `catch_warnings` block. If you need a truly "first call here, then warn for other call sites" guarantee, that's not what 1.8.0 provides — file an upstream issue rather than working around it.

---

## Audit recipe: find experimental dependencies in your code

A naive grep for `@experimental` only finds local definitions. To audit **uses** of upstream-experimental APIs, walk your imports and check the `__feature_stage__` attribute:

```python
# audit_experimental.py — best-effort developer audit
import importlib
import inspect
from typing import Iterable

def walk_experimental(modules: Iterable[str]) -> list[tuple[str, str, str]]:
    """Return (qualname, stage, feature_id) for every imported symbol tagged
    experimental or release-candidate.
    """
    out: list[tuple[str, str, str]] = []
    for modname in modules:
        try:
            mod = importlib.import_module(modname)
        except Exception as e:
            print(f"skip {modname}: {e}")
            continue
        for name, obj in inspect.getmembers(mod):
            stage = getattr(obj, "__feature_stage__", None)
            if stage:
                feature_id = getattr(obj, "__feature_id__", "<unknown>")
                out.append((f"{modname}.{name}", stage, feature_id))
    return out


if __name__ == "__main__":
    rows = walk_experimental([
        "agent_framework",
        "agent_framework_foundry",
        "my_app.agents",  # your code
    ])
    for qualname, stage, feature_id in rows:
        print(f"{stage:18s} [{feature_id:22s}] {qualname}")
```

> [!NOTE]
> This is a **developer audit aid**, not static analysis. It imports modules eagerly — optional dependencies will trigger `ImportError`, and modules with import-time side effects (HTTP clients, env-var checks) will run them. For a production CI gate, prefer combining the warnings-as-errors recipe above with a representative integration test pass.

---

## Lifecycle: what happens when an experimental API moves toward stable

Upstream is explicit that experimental APIs **may change or be removed in future versions without notice**. There is no guaranteed transition path. When an API does graduate (in practice, often a quiet decorator removal in a future release):

1. The `@experimental(...)` decorator is removed in source — runtime warnings stop firing.
2. The `__feature_stage__` / `__feature_id__` attributes disappear. Your audit script returns fewer rows.

**No guarantees about what else stays the same.** A graduation may also come with renames, signature changes, module moves, or behavioral changes — these are normal for APIs that were explicitly marked unstable. Treat every minor upgrade as a re-verification opportunity:

* Read the [release notes](https://github.com/microsoft/agent-framework/releases) for any feature you were using under `@experimental`.
* Pin your `agent-framework-foundry` version exactly (`==1.8.0`, not `>=1.7,<2`).
* Re-run your CI with warnings-as-errors **after** the upgrade — anything that was experimental and is now silent has either graduated cleanly or changed shape; either way, audit it.
* If you depended on the `__feature_stage__` attribute (e.g. in the audit script above), expect rows to disappear when symbols graduate — that's the signal that you should re-check them, not that they're permanently safe.

The reliable signal is the **upstream release notes** for the version range you're crossing — the `__feature_stage__` attribute only tells you "this is still in flux today."

---

## Cross-references

| If you're looking for… | See |
|---|---|
| Which Foundry hosted tools are experimental and which are stable | [`tools-hosted.md`](tools-hosted.md#stability-tiers) |
| Shell tool stability (separate `agent-framework-tools` package) | [`tools-shell.md`](tools-shell.md) |
| Evaluation framework experimental scope | [`evaluation.md`](evaluation.md#status-experimental) |
| Skills experimental scope | [`skills.md`](skills.md) |
| Sessions, harness, security stages | [`sessions.md`](sessions.md), [`packages.md`](packages.md) |
| Workflow `@workflow` / `@executor` decorators | [`workflow-internals.md`](workflow-internals.md#functional-workflows-experimental) |
| The anti-pattern of blanket-suppressing all warnings | [Inline anti-pattern](#anti-pattern-blanket-warning-suppression) below |

---

## Anti-pattern: blanket warning suppression

❌ **Wrong**

```python
import warnings
warnings.filterwarnings("ignore")  # global, all categories, all modules
```

**Why it's wrong:**

* You lose the framework's "this API may change" signal — when 1.6 → 1.7 changes a `@experimental(FOUNDRY_TOOLS)` factory's signature, you get a runtime `TypeError` instead of a heads-up warning during testing.
* You also suppress unrelated `DeprecationWarning`, `ResourceWarning`, `RuntimeWarning` (e.g. asyncio "coroutine was never awaited") — bugs that the standard library was trying to tell you about.
* The filter applies process-wide and to every dependency, not just `agent_framework`.

✅ **Right — scoped by category and module**

```python
import warnings

# Only suppress AgentFramework experimental warnings, only when emitted
# from agent_framework / agent_framework_foundry modules.
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module=r"agent_framework(_foundry)?(\.|$)",
)
```

✅ **Better — narrow to specific feature IDs you've audited**

```python
import warnings

# You've reviewed the Bing grounding hosted factory and accept the churn.
# Other experimental subsystems still warn.
warnings.filterwarnings(
    "ignore",
    message=r"^\[FOUNDRY_TOOLS\]",
    category=FutureWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"^\[FOUNDRY_PREVIEW_TOOLS\]",
    category=FutureWarning,
)
```

**How to detect this anti-pattern in your codebase:**

```bash
# Catch bare ignore-all filters
grep -rn 'warnings.filterwarnings\("ignore"\)' --include="*.py"
grep -rn 'warnings.simplefilter\("ignore"\)' --include="*.py"

# Catch bare logging.captureWarnings without level set
grep -rn 'captureWarnings(True)' --include="*.py" -A2 | grep -v 'setLevel'
```

---

## See also

* [`packages.md`](packages.md) — which packages contain experimental code (`agent-framework-tools` is alpha, `agent-framework-monty` is experimental, etc.)
* [`tools-hosted.md`](tools-hosted.md) — the per-factory stability table this page is the foundation for
* [`tools-shell.md`](tools-shell.md) — separate `agent-framework-tools` package (alpha-versioned, not gated by `@experimental` decorator)
* Upstream source: [`_feature_stage.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_feature_stage.py) (286 LOC)
* Upstream tests: [`test_feature_stage.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/tests/core/test_feature_stage.py)
