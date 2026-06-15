# Anti-pattern — Declarative YAML pitfalls (BETA)

> [!WARNING]
> This page covers `agent-framework-declarative==1.0.0b260528` (Beta). Pin the version. See [`declarative.md`](../api-reference/1.8.0/declarative.md) for the public API surface.

8 concrete WRONG/RIGHT pairs you'll hit when authoring YAML agents and workflows.

---

## 1. Treating a Beta API as stable

**Symptom:** Production breaks on minor-version bump of `agent-framework-declarative`; YAML that worked yesterday raises `DeclarativeLoaderError` today.

**Why it's wrong:** The package is `Development Status :: 4 - Beta` ([`pyproject.toml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/pyproject.toml)). Action kinds, YAML keys, and Python APIs may change without semver guarantees. Reproducible builds require an **exact** pin.

```text
# ❌ Wrong — loose version range; surprise upgrades

# requirements.txt
agent-framework-declarative>=1.0.0b0
```

```text
# ✅ Right — exact pin + change-log review before bumping

# requirements.txt
agent-framework-declarative==1.0.0b260528

# CHANGELOG.md (your repo)
# - 2026-05-21: Pinned to 1.0.0b260528. Re-verify YAML samples before bumping.
```

**How to detect:** `pip index versions agent-framework-declarative` regularly; CI test that loads every YAML in your repo via `WorkflowFactory().create_workflow_from_yaml_path(...)` and fails on `DeclarativeWorkflowError`.

---

## 2. Unknown `kind:` silently skipped

**Symptom:** A workflow runs without errors but "missing" steps don't execute. Behavior is mysteriously wrong.

**Why it's wrong:** The builder logs `WARNING` and **skips** any action whose `kind:` isn't in [`ALL_ACTION_EXECUTORS`](../api-reference/1.8.0/declarative.md#action-kind-catalog-34-total) or the builder-inline set ([`_declarative_builder.py:L455-L459`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py#L455-L459)). It does **not** raise. A typo silently removes behavior.

```yaml
# ❌ Wrong — "SetVarible" is a typo. The action vanishes.
actions:
  - kind: SetVarible      # typo!
    id: set_x
    path: Local.x
    value: 42

  - kind: SendActivity
    activity:
      text: =Concat("x = ", Local.x)   # prints "x = " (Local.x never set)
```

```yaml
# ✅ Right — use the exact kind name from the catalog
actions:
  - kind: SetValue        # correct
    id: set_x
    path: Local.x
    value: 42

  - kind: SendActivity
    activity:
      text: =Concat("x = ", Local.x)
```

**How to detect:** Enable WARNING-level logging on `agent_framework.declarative` in CI and grep for `"Unknown action kind"`:

```python
import logging
logging.getLogger("agent_framework.declarative").setLevel(logging.WARNING)
```

Or pre-validate YAML against the catalog in a CI script:

```bash
KINDS="CreateConversation|SetValue|SetVariable|SetTextVariable|SetMultipleVariables|ResetVariable|ClearAllVariables|SendActivity|ParseValue|EditTable|EditTableV2|EndWorkflow|EndDialog|EndConversation|CancelDialog|CancelAllDialogs|InvokeAzureAgent|InvokeFunctionTool|HttpRequestAction|InvokeMcpTool|Question|RequestExternalInput|If|ConditionGroup|Foreach|GotoAction|BreakLoop|ContinueLoop"
grep -hE "^\s*-?\s*kind:" workflows/*.yaml | awk '{print $NF}' | sort -u | grep -vE "^($KINDS)$"
```

---

## 3. Wrong provider name (`AzureOpenAIChat` vs `AzureOpenAI.Chat`)

**Symptom:** `ProviderLookupError: No provider mapping found for 'AzureOpenAIChat'` at agent build time.

**Why it's wrong:** Provider keys are **dot-separated** `Provider.ApiType` ([built-in mapping](../api-reference/1.8.0/declarative.md#built-in-provider-type-mappings)). A run-together name doesn't match the 9 built-in keys and isn't in `additional_mappings`.

```yaml
# ❌ Wrong — provider name has no dot
model:
  id: gpt-5-4
  provider: AzureOpenAIChat
```

```yaml
# ✅ Right — Provider.ApiType
model:
  id: gpt-5-4
  provider: AzureOpenAI
  apiType: Chat
```

**How to detect:** Add a smoke test that loads every YAML and catches `ProviderLookupError`. The valid keys are: `AzureOpenAI`, `AzureOpenAI.Chat`, `AzureOpenAI.Responses`, `Foundry`, `Foundry.Chat`, `OpenAI`, `OpenAI.Chat`, `OpenAI.Responses`, `Anthropic.Chat`.

---

## 4. Using `=Env.X` without disabling `safe_mode`

**Symptom:** YAML loads without error, but credentials/endpoints are empty at runtime. Eventually fails with "401 Unauthorized" or a `RuntimeError` about missing config.

**Why it's wrong:** `AgentFactory(safe_mode=True)` is the default ([`_loader.py:L190`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L190)). In safe mode, **PowerFx cannot read environment variables** — `=Env.X` evaluates to an empty value silently. This is intentional defense-in-depth against untrusted YAML.

```python
# ❌ Wrong — safe_mode=True (default) means =Env.X is invisible to PowerFx
from agent_framework.declarative import AgentFactory
factory = AgentFactory()
agent = factory.create_agent_from_yaml_path("foundry_agent.yaml")
# foundry_agent.yaml uses =Env.AZURE_FOUNDRY_PROJECT_ENDPOINT → empty
```

```python
# ✅ Right (option A — preferred) — rewrite YAML to use standard env var names
# The chat client reads FOUNDRY_PROJECT_ENDPOINT / FOUNDRY_MODEL natively
# Drop =Env.* references from YAML; keep safe_mode=True
```

```yaml
# YAML using option A — no =Env.* needed
model:
  id: gpt-5-4
  provider: Foundry
  # endpoint resolved by FoundryChatClient from FOUNDRY_PROJECT_ENDPOINT env var
```

```python
# ✅ Right (option B — only when consuming trusted external YAML)
from agent_framework.declarative import AgentFactory

factory = AgentFactory(
    safe_mode=False,        # ⚠️ YAML can now read ALL env vars
    env_file_path=".env",
)
agent = factory.create_agent_from_yaml_path("untrusted_partner_sample.yaml")
```

**Why option A wins:** With `safe_mode=False`, a malicious or buggy YAML could exfiltrate any environment variable (`=Env.AZURE_OPENAI_API_KEY`, `=Env.GITHUB_TOKEN`, etc.) into an action output. Option A keeps the blast radius bounded to what `FoundryChatClient` actually needs.

**How to detect:** Grep YAML for `=Env\.` and require justification; CI check that fails on any `=Env.` reference unless `safe_mode=False` is explicitly set in code with a `# noqa: trusted-yaml` comment.

---

## 5. `InvokeAzureAgent` with no registered agent

**Symptom:** Workflow build succeeds but execution fails at the first `InvokeAzureAgent` action with `KeyError` or a generic `DeclarativeActionError`.

**Why it's wrong:** `InvokeAzureAgent` looks up `agent.name` in the `WorkflowFactory(agents=...)` dict or names registered via `register_agent(...)`. The lookup happens at **action execution**, not at YAML load — so a missing registration sails through `create_workflow_from_yaml_path`.

```python
# ❌ Wrong — YAML references "ResearchAgent" but factory has no registration
factory = WorkflowFactory()           # no agents
workflow = factory.create_workflow_from_yaml_path("workflow.yaml")  # OK
result = await workflow.run({"query": "..."})                       # fails here
```

```python
# ✅ Right — every name referenced by YAML is registered up-front
agents = {
    "ResearchAgent": research_agent,
    "WriterAgent": writer_agent,
}
factory = WorkflowFactory(agents=agents)
workflow = factory.create_workflow_from_yaml_path("workflow.yaml")
```

**How to detect:** Parse YAML, extract every `agent.name:` value, and assert each one is in your registered dict before calling `run(...)`. Add this to your test suite:

```python
import yaml

doc = yaml.safe_load(open("workflow.yaml"))
needed = {a["agent"]["name"] for a in doc["actions"] if a.get("kind") == "InvokeAzureAgent"}
assert needed.issubset(set(agents.keys())), f"Missing: {needed - set(agents.keys())}"
```

---

## 6. Default handlers are SSRF-unsafe in production

**Symptom:** A YAML you don't fully control (partner-supplied, AI-generated, user-edited) calls `HttpRequestAction` against an internal IP (`http://169.254.169.254/...` — AWS IMDS, or `http://localhost:6379` — internal Redis), exfiltrating data or pivoting.

**Why it's wrong:** `DefaultHttpRequestHandler` and `DefaultMCPToolHandler` apply **no URL allow-list, no host filtering, no IP-block filtering** ([`_http_handler.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_http_handler.py)). They're convenience defaults for development.

```python
# ❌ Wrong — no SSRF guard in production
from agent_framework.declarative import (
    DefaultHttpRequestHandler,
    WorkflowFactory,
)

factory = WorkflowFactory(http_request_handler=DefaultHttpRequestHandler())
```

```python
# ✅ Right — allow-list enforced for production
from ipaddress import ip_address
from urllib.parse import urlparse
import socket

from agent_framework.declarative import (
    HttpRequestHandler,
    HttpRequestInfo,
    HttpRequestResult,
    WorkflowFactory,
)
import httpx


class GuardedHttpHandler:
    ALLOWED_HOSTS = {"api.partner.com", "weather.example.com"}

    def __init__(self) -> None:
        self._client = httpx.AsyncClient()

    async def send(self, info: HttpRequestInfo) -> HttpRequestResult:
        parsed = urlparse(info.url)
        host = parsed.hostname or ""
        if host not in self.ALLOWED_HOSTS:
            raise PermissionError(f"URL not in allow-list: {info.url}")
        # Also block resolution to private IPs
        try:
            resolved = ip_address(socket.gethostbyname(host))
            if resolved.is_private or resolved.is_loopback or resolved.is_link_local:
                raise PermissionError(f"Host resolves to private IP: {host}")
        except (ValueError, socket.gaierror):
            raise PermissionError(f"Cannot resolve host: {host}")

        r = await self._client.request(
            info.method, info.url, headers=info.headers, content=info.body
        )
        return HttpRequestResult(
            status_code=r.status_code,
            is_success_status_code=r.is_success,
            body=r.text,
            headers={k.lower(): [v] for k, v in r.headers.items()},
        )


factory = WorkflowFactory(http_request_handler=GuardedHttpHandler())
```

> [!IMPORTANT]
> `HttpRequestHandler` is a Protocol with method **`send(info) -> HttpRequestResult`** ([`_http_handler.py:L90-L120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_http_handler.py#L90-L120)) — **not** `__call__`. `HttpRequestResult` requires **all four** fields: `status_code: int`, `is_success_status_code: bool`, `body: str`, `headers: dict[str, list[str]]` ([`L68-L87`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_http_handler.py#L68-L87)). Keys in `headers` must be lowercase; values are always lists (to preserve multi-value headers).

The same caveat and pattern applies to `MCPToolHandler` for `InvokeMcpTool` actions.

**How to detect:** Code-review checklist — any production deployment that constructs `WorkflowFactory` with a `Default*Handler` is a finding. CI grep:

```bash
grep -rn "DefaultHttpRequestHandler\|DefaultMCPToolHandler" --include="*.py" src/ \
  | grep -v "# dev-only" \
  && echo "FINDING: default handler used without dev-only justification"
```

---

## 7. Confusing state-write with output-emit

**Symptom:** `result.get_outputs()` returns `[]` even though your YAML clearly writes the final result to `Workflow.Outputs.answer`. Downstream code that depended on the workflow's "output" sees nothing.

**Why it's wrong:** In Python 1.8.0, `Workflow.get_outputs()` returns `[event.data for event in self if event.type == "output"]` ([`_workflow.py:L125-L131`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/core/agent_framework/_workflows/_workflow.py#L125-L131)). `"output"` events are produced **only** when an executor calls `ctx.yield_output(...)`. `SetValueExecutor` (used by `SetValue`) just mutates state and sends `ActionComplete` — it **never yields output** ([`_executors_basic.py:L40-L63`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_basic.py#L40-L63)).

The actions that **do** call `ctx.yield_output(...)`:

| Action `kind` | What it yields | Source |
|---|---|---|
| `SendActivity` | The rendered `activity.text` | [`_executors_basic.py:L277`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_basic.py#L277) |
| `InvokeAzureAgent` | The agent's final response | [`_executors_agents.py:L676`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_executors_agents.py#L676) |

> [!NOTE]
> 1.8.0 removed the `EmitEvent` action ([PR #6126](https://github.com/microsoft/agent-framework/pull/6126)). Before 1.8.0 there was a third yielding action (`EmitEvent` at `_executors_basic.py:L318`); in 1.8.0 only the two above remain. Use `SendActivity` to surface a value to `get_outputs()`.

`Workflow.Outputs.*` is the **convention** for "final" values (matching .NET / cross-runtime declarative semantics), but in Python 1.8.0 the path to `get_outputs()` requires an action that yields.

```yaml
# ❌ Wrong — SetValue mutates state but never yields. result.get_outputs() == []
actions:
  - kind: SetValue
    path: Local.computed
    value: 42

  - kind: SetValue
    path: Workflow.Outputs.answer
    value: '=Concat("Result: ", Local.computed)'
```

```yaml
# ✅ Right (Option A — yield the value via SendActivity)
actions:
  - kind: SetValue
    path: Local.computed
    value: 42

  - kind: SetValue
    path: Workflow.Outputs.answer       # cross-runtime convention; portable
    value: '=Concat("Result: ", Local.computed)'

  - kind: SendActivity                  # yields → surfaced by get_outputs()
    activity:
      text: =Workflow.Outputs.answer
```

```yaml
# ✅ Right (Option B — use SendActivity directly when state-write isn't needed)
actions:
  - kind: SetValue
    path: Local.computed
    value: 42

  - kind: SendActivity
    activity:
      text: '=Concat("Result: ", Local.computed)'   # yielded → in get_outputs()
```

```python
result = await workflow.run({})
for o in result.get_outputs():
    print(o)   # "Result: 42"
```

**How to detect:** Add a unit test that asserts `len(result.get_outputs()) > 0` for every workflow expected to produce a caller-visible result. Failing means no action called `ctx.yield_output(...)` — usually a chain of `SetValue` writes with no `SendActivity`/`InvokeAzureAgent` at the end.

```bash
# Quick smell test: workflows that write Workflow.Outputs.* without any SendActivity/InvokeAzureAgent
for f in workflows/*.yaml; do
  if grep -q 'Workflow\.Outputs\.' "$f" && ! grep -qE 'kind:\s*(SendActivity|InvokeAzureAgent)' "$f"; then
    echo "SMELL: $f writes Workflow.Outputs.* but never yields output"
  fi
done
```

---

## 8. PowerFx syntax traps

**Symptom:** Conditions never match (or always match); expressions evaluate to empty / `Blank()`; `=` literals leak into output as the string `"=Concat(...)"`.

**Why it's wrong:** PowerFx is **not Python**. The registered PowerFx helper set lives in [`_powerfx_functions.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_powerfx_functions.py) — confirm any helper by inspecting that file.

| Trap | Wrong | Right |
|---|---|---|
| Missing prefix | `Concat(a, b)` (treated as literal string) | `=Concat(a, b)` (leading `=` triggers evaluation, [`_state.py:L342`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_state.py#L342)) |
| None / null check | `=Local.x = None` (Python `None` literal) | `=IsBlank(Local.x)` ([`_powerfx_functions.py:L183`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_powerfx_functions.py#L183)) |
| String functions | `=str.lower(x)` / `=x.lower()` (Python attribute syntax) | `=Lower(x)` ([`_powerfx_functions.py:L343`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_powerfx_functions.py#L343)) |
| Collection length | `=len(Local.items)` (Python builtin) | `=CountRows(Local.items)` ([`_powerfx_functions.py:L245`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_powerfx_functions.py#L245)) |
| Equality | `=Local.x == 1` (Python operator; **untested in this workshop** — your PowerFx engine may reject or always-false) | `=Local.x = 1` (canonical PowerFx single-`=`) |
| Boolean literal | `=True`, `=False` (**capitalization untested in this workshop**; PowerFx convention is `true`/`false`) | `=true`, `=false` |

> [!NOTE]
> The first 4 rows are verifiable against the registered PowerFx helpers — `Lower`, `IsBlank`, `CountRows`, `Concat`, `Upper`, `If`, `Or`, `And`, `Not`, `Find`, `First`, `Last`, `ForAll`, `Search` all exist (see [`_powerfx_functions.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_powerfx_functions.py)). The last 2 rows (`==` vs `=` operator, `True`/`true` casing) follow PowerFx documentation but the **exact parser behavior is provided by the upstream `powerfx` Python package** — write a smoke test if your workflow depends on either to fail-fast.

**Example fixes:**

```yaml
# ❌ Wrong — Python-style equality (parser behavior depends on powerfx wheel)
- kind: If
  condition: =Local.status == "ready"
  then: [...]
```

```yaml
# ✅ Right — canonical PowerFx single-=
- kind: If
  condition: =Local.status = "ready"
  then: [...]
```

```yaml
# ❌ Wrong — missing = prefix, treated as literal
- kind: SetValue
  path: Local.msg
  value: Concat("Hello, ", inputs.name)
```

```yaml
# ✅ Right — PowerFx expression
- kind: SetValue
  path: Local.msg
  value: =Concat("Hello, ", inputs.name)
```

**How to detect:** Code review — grep for `==`, `True`, `False`, `None`, `str.` inside `value:` and `condition:` fields:

```bash
grep -En "value:\s*=.*(==|True|False|None|str\.)" workflows/*.yaml
grep -En "condition:\s*=.*==" workflows/*.yaml
```

> [!NOTE]
> Python 3.14 has no `powerfx` wheel ([`pyproject.toml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/pyproject.toml) — `powerfx>=0.0.32,<0.0.35; python_version < '3.14'`). All `=expr` evaluation falls back / fails on 3.14. The workshop venv pins Python 3.12 to avoid this.

---

## See also

- [API ref — `declarative.md`](../api-reference/1.8.0/declarative.md) — full surface, action catalog, scopes
- [Pattern — `declarative-agent.md`](../patterns/declarative-agent.md)
- [Pattern — `declarative-workflow.md`](../patterns/declarative-workflow.md)
- [Anti-pattern — `workflow-event-isinstance.md`](workflow-event-isinstance.md) — `event.type` discrimination (relevant to HITL handling)
- [Anti-pattern — `missing-async-with-cleanup.md`](missing-async-with-cleanup.md) — `async with agent:` for resource cleanup
- Upstream source: [`_declarative_builder.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_declarative_builder.py), [`_loader.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py), [`_state.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_workflows/_state.py)
