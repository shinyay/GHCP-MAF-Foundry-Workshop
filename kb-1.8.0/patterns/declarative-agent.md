# Pattern — Declarative agent from YAML (BETA)

> [!WARNING]
> Uses `agent-framework-declarative==1.0.0b260528` (Beta). Pin the exact version; expect breaking changes between minor versions. See [`declarative.md`](../api-reference/1.8.0/declarative.md) for the full API surface.

## Goal

Load a `PromptAgent` definition from a YAML file (or string) and run it like any code-defined `Agent`.

## When to use

- **Operational reuse** — multiple agents share an authoring template; agent definitions are owned by non-Python authors (PM/researcher) or stored in a CMS / package manifest.
- **A/B and config-driven tuning** — switching `instructions`, `temperature`, `outputSchema` between environments without redeploying Python.
- **YAML-as-source-of-truth** — version-control the agent definition itself; rebuild/redeploy by editing YAML, not code.

## When *not* to use

- The agent is built and torn down inside one Python file → keep it imperative.
- You need IDE autocomplete / type checking on agent fields → YAML is opaque to mypy/pyright.
- The agent definition depends on values that aren't representable in YAML (e.g. dynamically constructed tool list, callables) → use Python.

## Prerequisites

```bash
pip install 'agent-framework-foundry==1.8.0' 'agent-framework-declarative==1.0.0b260528'
az login   # default credential chain for FoundryChatClient
```

`.env` (in the workshop, this is already wired by [`docs/quickstart.md`](../README.md)):

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com/api/projects/<project-name>
FOUNDRY_MODEL=gpt-5-4
```

> [!IMPORTANT]
> Use the **standard** env var names that `FoundryChatClient` reads natively (`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`). The reason is explained in the next section — it lets you stay on `safe_mode=True` (the secure default).

---

## Code — the safe pattern (recommended)

Save the agent as `agent.yaml`:

```yaml
kind: Prompt
name: Researcher
description: Answers technical questions with citations.
instructions: |
  You are a helpful research assistant. Cite at least one source per claim.
model:
  id: gpt-5-4
  provider: Foundry
  options:
    temperature: 0.2
    topP: 0.95
outputSchema:
  properties:
    answer:
      type: string
      required: true
      description: The answer text.
    sources:
      type: array
      required: true
      description: List of source URLs.
```

Load and run it:

```python
import asyncio
from agent_framework.declarative import AgentFactory


async def main() -> None:
    factory = AgentFactory()  # safe_mode=True (default) — env vars NOT exposed to YAML
    agent = factory.create_agent_from_yaml_path("agent.yaml")

    async with agent:
        result = await agent.run("What is the capital of France?")
        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
```

### Why this works

- The YAML has **no `=Env.X`** references. Provider credentials are resolved by `FoundryChatClient.__init__` reading `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL` from `os.environ` directly ([`clients.md`](../api-reference/1.8.0/clients.md)).
- `factory.create_agent_from_yaml_path` matches `provider: Foundry` against the built-in [provider mapping](../api-reference/1.8.0/declarative.md#built-in-provider-type-mappings) and instantiates `FoundryChatClient` for you.
- `safe_mode=True` means even if the YAML *did* contain `=Env.SECRET`, PowerFx would not see it — defense in depth against an untrusted YAML source.
- `async with agent` is the canonical resource-management pattern — see [`missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md).

---

## Variant — when you must use `=Env.*` in YAML

If you're consuming an upstream YAML sample that uses `=Env.AZURE_FOUNDRY_PROJECT_ENDPOINT` (like Microsoft's [`declarative-agents/agent-samples/foundry/FoundryAgent.yaml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/declarative-agents/agent-samples/foundry/FoundryAgent.yaml)), you must explicitly disable safe mode:

```python
factory = AgentFactory(
    safe_mode=False,           # ⚠️ YAML can now read every env var in the process
    env_file_path=".env",      # load .env before evaluating =Env.* expressions
)
agent = factory.create_agent_from_yaml_path("foundry_sample.yaml")
```

> [!WARNING]
> Only set `safe_mode=False` when you fully trust the YAML source. Treat it like `eval()` — the YAML can read any environment variable, including secrets you didn't intend to expose. Prefer rewriting the YAML to drop `=Env.*` references and rely on standard env var names instead.

---

## Variant — function tools

To attach a Python tool, declare it in YAML with **`kind: function`** (lowercase — case-sensitive at [`_models.py:L578`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_models.py#L578)) and an explicit **`bindings:`** block whose `name:` matches a key in `AgentFactory(bindings={...})` (see [`_loader.py:L741-L753`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L741-L753)):

```yaml
kind: Prompt
name: WeatherAgent
instructions: You answer weather questions for the given city.
model:
  id: gpt-5-4
  provider: Foundry
tools:
  - kind: function
    name: get_weather
    description: Get current weather for a city.
    parameters:
      properties:
        city:
          type: string
          required: true
          description: The city name.
    bindings:
      - name: get_weather             # must match a key in AgentFactory(bindings=...)
```

```python
from typing import Annotated
from pydantic import Field
from agent_framework.declarative import AgentFactory


def get_weather(
    city: Annotated[str, Field(description="The city name.")],
) -> str:
    return f"It's sunny in {city}."


factory = AgentFactory(
    bindings={"get_weather": get_weather},  # binding name == YAML bindings[].name
)
agent = factory.create_agent_from_yaml_path("agent.yaml")
```

> [!IMPORTANT]
> `kind` is case-sensitive. `kind: Function` (PascalCase) silently falls through to the base `Tool` class — the callable is **not** wired and the agent may surface "tool definition without implementation" failures at run time. Verify with the executor source: [`_models.py:L576-L580`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_models.py#L576-L580).

> [!NOTE]
> Without the `bindings:` block in YAML, `_parse_tool` ([`_loader.py:L739-L753`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/declarative/agent_framework_declarative/_loader.py#L739-L753)) constructs an `AFFunctionTool` with `func=None`. The schema/description still reach the model, but tool invocation fails. Declare every YAML function tool's `bindings:` and pass the matching callable in `AgentFactory(bindings={...})`.

> [!NOTE]
> Hosted tools (Bing Web Search, Code Interpreter, File Search) are declared with their respective `kind:` values in the `tools:` block; the factory wires them up via the corresponding chat-client `get_*_tool(...)` factory ([`tools-hosted.md`](../api-reference/1.8.0/tools-hosted.md)). Check the upstream `agent-samples/foundry/` folder for ready-made YAML.

---

## Variant — async factory method

When the chat-client construction is async (some Foundry agent flavors), use the `_async` method:

```python
async def main() -> None:
    factory = AgentFactory()
    agent = await factory.create_agent_from_yaml_path_async("agent.yaml")
    async with agent:
        ...
```

---

## Verification

```bash
python3 agent_demo.py
# Expected: prints the model's answer, or a Foundry auth error if env vars missing.
```

For YAML schema validation without running the agent:

```python
from agent_framework.declarative import AgentFactory, DeclarativeLoaderError

try:
    AgentFactory().create_agent_from_yaml_path("agent.yaml")
except DeclarativeLoaderError as e:
    print(f"YAML invalid: {e}")
```

---

## Common mistakes

| Mistake | Fix |
|---|---|
| `=Env.X` returns empty string | Either set `safe_mode=False` *(only if trusted YAML)* or rewrite YAML to use standard env var names read by the chat client |
| `ProviderLookupError: AzureOpenAIChat` | Provider name is `AzureOpenAI.Chat` (dot-separated) — see [provider mapping table](../api-reference/1.8.0/declarative.md#built-in-provider-type-mappings) |
| `DeclarativeLoaderError: ... model.id required` | Every `kind: Prompt` YAML needs `model.id` (the deployment / model name) |
| Tool YAML present but function never called | Register the callable via `AgentFactory(bindings={...})`; YAML alone doesn't make a Python function discoverable |
| No `async with agent:` | Causes unclosed-connector warnings — see [`missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md) |

See [`declarative-pitfalls.md`](../anti-patterns/declarative-pitfalls.md) for the full anti-pattern catalog.

---

## See also

- [API ref — `declarative.md`](../api-reference/1.8.0/declarative.md) — `AgentFactory` full surface
- [Pattern — `declarative-workflow.md`](declarative-workflow.md) — workflow companion
- [Anti-pattern — `declarative-pitfalls.md`](../anti-patterns/declarative-pitfalls.md)
- [Pattern — `canonical-agent-creation.md`](canonical-agent-creation.md) — imperative equivalent
- Upstream samples: [agent-samples/foundry](https://github.com/microsoft/agent-framework/tree/python-1.8.0/declarative-agents/agent-samples/foundry), [agent-samples/openai](https://github.com/microsoft/agent-framework/tree/python-1.8.0/declarative-agents/agent-samples/openai)
