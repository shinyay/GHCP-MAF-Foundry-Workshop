# Pattern: Foundry Prompt Agent — Convert a Local Agent to a Publishable Definition

> Status: ⚠️ **Experimental** — `@experimental(feature_id=ExperimentalFeature.TO_PROMPT_AGENT)`
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent_framework_foundry/_to_prompt_agent.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_to_prompt_agent.py) (~320 LOC) and [test suite `test_to_prompt_agent.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/tests/foundry/test_to_prompt_agent.py) (664 LOC)
> See also: [API ref — `clients.md`](../api-reference/1.8.0/clients.md), [`canonical-agent-creation.md`](canonical-agent-creation.md), [`hosted-bing-search.md`](hosted-bing-search.md)

> [!WARNING]
> `to_prompt_agent` is decorated with `@experimental(feature_id=ExperimentalFeature.TO_PROMPT_AGENT)`. The signature, the tool-translation rules, and the set of generation parameters carried across **can and will change** between minor versions. Pin `agent-framework-foundry==1.8.0` exactly and re-validate on every Agent Framework upgrade. See [`feature-stages.md`](../api-reference/1.8.0/feature-stages.md) for the warning model.

> [!IMPORTANT]
> The PR description for [#5959](https://github.com/microsoft/agent-framework/pull/5959) mentions a `deploy_as_prompt_agent` convenience wrapper, but **that function does NOT exist** in `agent-framework-foundry==1.8.0`. Only `to_prompt_agent` shipped (verified: `agent_framework_foundry/__init__.py:L19,L43`). The publish step — `AIProjectClient.agents.create_version(definition)` — is **your code's responsibility**.

## Goal

Take an `Agent` you've already built, instructions-tuned, and tool-tested against `FoundryChatClient` **locally**, and convert it into a `PromptAgentDefinition` that you can publish to your Azure AI Foundry project as a **hosted prompt agent** (no code changes to the local agent; the same `Agent` definition powers both local execution and the hosted deployment).

## When to use this pattern

- ✅ You finished iterating on an agent's instructions, tools, and generation params locally and now want a **server-managed** version of it in Foundry.
- ✅ You want **other Foundry users / SDKs / Logic Apps** to call your agent without your Python runtime being in the path.
- ✅ Your agent uses **hosted Foundry tools** (Bing, code interpreter, file search, hosted MCP) — `to_prompt_agent` round-trips them.
- ❌ Your agent has **local Python function tools** that must execute server-side — see Gotcha #1 below; you'll only get the *declaration*, not the implementation.
- ❌ Your agent uses **local MCP** (`MCPStreamableHTTPTool` etc.) — see Gotcha #2; `to_prompt_agent` raises `ValueError`.
- ❌ You don't have an `AIProjectClient` with `agents.create_version(...)` permissions on the target project.
- ❌ You wanted an auto-deploy convenience — see the warning above; there's no `deploy_as_prompt_agent`.

## Code

Two-step flow: `to_prompt_agent(agent) → PromptAgentDefinition → AIProjectClient.agents.create_version(definition)`.

```python
import asyncio
import os
from pathlib import Path
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.foundry import FoundryChatClient, to_prompt_agent
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
for _k, _v in dotenv_values(_DOTENV_PATH).items():
    if _v is None:
        continue
    if not (os.getenv(_k) or "").strip():
        os.environ[_k] = _v


def get_weather(
    city: Annotated[str, "City name, e.g. 'Seattle'."],
) -> str:
    """Look up the current weather for a city."""
    return f"The weather in {city} is sunny and 22°C."


async def main() -> None:
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        )

        # 1) Build and locally validate your agent.
        agent = client.as_agent(
            name="weather-assistant",
            instructions="You are a friendly weather assistant. Always cite the city.",
            tools=[get_weather],
            default_options={"temperature": 0.3},
        )

        # (Run a local probe here if you want — agent.run("...") — before publishing.)

        # 2) Convert local Agent → Foundry PromptAgentDefinition.
        definition = to_prompt_agent(agent)
        #    The definition carries: model, instructions, tools (as declarations
        #    for function tools, pass-through for hosted SDK tools), and any
        #    translated generation params from agent.default_options.

        # 3) Publish — caller's responsibility, NOT auto-deployed by to_prompt_agent.
        async with AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project:
            version = await project.agents.create_version(definition)
            print(f"Published prompt agent. version_id={version.id}")


if __name__ == "__main__":
    asyncio.run(main())
```

> [!NOTE]
> The example above is **verified against upstream source and the 664-LOC test suite** but **was not executed against a live Foundry endpoint** as part of this KB authoring (X-stage policy: compile + AST only). The shape — `to_prompt_agent(agent) → PromptAgentDefinition`, then `project.agents.create_version(definition)` — matches the source docstring at [`_to_prompt_agent.py:L80-L82`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_to_prompt_agent.py#L80-L82). Confirm the `AIProjectClient.agents.create_version(...)` call signature against your installed `azure-ai-projects` version before relying on it in production.

## How it works

### Signature

```python
@experimental(feature_id=ExperimentalFeature.TO_PROMPT_AGENT)
def to_prompt_agent(
    agent: Agent,
    *,
    structured_inputs: Mapping[str, StructuredInputDefinition] | None = None,
    rai_config: RaiConfig | None = None,
) -> PromptAgentDefinition: ...
```

Both `structured_inputs` and `rai_config` are **Foundry-only** fields (no equivalent in `ChatOptions`); they're accepted as kwargs to be forwarded into the `PromptAgentDefinition`. Everything else comes from the bound `Agent`.

### What gets lifted from the local `Agent`

| Source | Destination in `PromptAgentDefinition` | Notes |
|---|---|---|
| `agent.default_options['model']` ([resolution order](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_to_prompt_agent.py#L90-L98)) — falls back to `agent.client.model` | `model` | If neither is set → `ValueError("Agent has no model. Set 'model' on the FoundryChatClient ...")` |
| `agent.default_options['instructions']` | `instructions` | Omitted if `None` |
| `agent.default_options['tools']` + `agent.mcp_tools` | `tools` (via `_convert_tools`) | See tool-translation matrix below |
| `agent.default_options['temperature']` | `temperature` | Translated by `_prepare_prompt_agent_options` |
| `agent.default_options['top_p']` | `top_p` | Same |
| `agent.default_options['tool_choice']` | `tool_choice` | **Omitted when no tools are present** |
| `agent.default_options['reasoning']` | `reasoning` | Same |
| `agent.default_options['response_format']` / `text` / `verbosity` | `text` (as `PromptAgentDefinitionTextOptions`) | Same |

**Generation params come from `Agent.default_options`, not from `to_prompt_agent` kwargs.** Configure them on the `Agent` (or pass `default_options={...}` to its constructor) — `to_prompt_agent` is intentionally a thin conversion, not a configuration override point.

### Tool translation matrix (verified at [`_to_prompt_agent.py:L237-L323`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_to_prompt_agent.py#L237-L323))

| Source tool type | What happens |
|---|---|
| `FoundryChatClient.get_web_search_tool()` / `get_code_interpreter_tool()` / `get_mcp_tool()` / etc. (hosted SDK `Tool` instances, returned by `client.get_*_tool()` factories — added in 1.6.0 per PR [#5958](https://github.com/microsoft/agent-framework/pull/5958)) | **Pass-through unchanged.** These already match the Foundry tool schema. |
| `FunctionTool` derived from a local Python callable | **Declaration only** — translated into a Foundry `FunctionTool(name, description, parameters, strict=True)` carrying only the JSON schema. Server-side execution must be wired separately by the caller (the hosted agent will *call* the tool but Foundry won't run your local Python). See Gotcha #1. |
| `Mapping`/`dict` with a `"type"` discriminator | **Validated and rehydrated** via `Tool._deserialize(dict, [])` — used when you have a raw Foundry tool JSON spec on hand. Raises `ValueError("Dict-shaped tools must include a 'type' field ...")` if `"type"` is missing. |
| Any **local** MCP tool (e.g., from `MCPStreamableHTTPTool`, surfaced in `agent.mcp_tools`) | **Hard reject** — raises `ValueError(f"Local MCP tool {name!r} cannot be published as a prompt-agent tool. Use FoundryChatClient.get_mcp_tool(...) to register a hosted MCP server instead.")` |
| Anything else | Raises `ValueError(f"Unsupported tool type for PromptAgentDefinition: {type(tool_item).__name__}. ...")` |

### Hard client-type constraint

```python
if not isinstance(agent.client, RawFoundryChatClient):
    raise TypeError(
        "Creating a Foundry Prompt Agent requires an Agent whose client is a "
        f"FoundryChatClient; got {type(agent.client).__name__!r}."
    )
```

`OpenAIChatClient`, `OpenAIChatCompletionClient`, or any non-Foundry client → immediate `TypeError`. This is the first check `to_prompt_agent` does, before model resolution or tool conversion.

## Gotchas

### 1. ⚠️ Function tools are converted to declarations only — server-side execution is YOUR job

This is the single most important caveat (called out in the module-level docstring at [`_to_prompt_agent.py:L22-L25`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_to_prompt_agent.py#L22-L25) and the helper docstring at [L284-L289](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_to_prompt_agent.py#L284-L289)):

> *"Function tools derived from local Python callables are translated to Foundry `FunctionTool` declarations only. Prompt agents are server-side, so the deployed agent will receive the schema for these tools but cannot execute the underlying Python; wiring server-side execution is the caller's responsibility."*

If your `Agent` works locally because of a Python function tool, the published prompt agent will *advertise* that tool to the model, but **calls to it will fail server-side** unless you separately implement an Azure Function / Logic App / hosted endpoint that fulfills the same schema. For tools you want to "just work" post-publish, prefer the hosted Foundry SDK factories (`client.get_web_search_tool()`, `client.get_code_interpreter_tool()`, `client.get_mcp_tool()`).

### 2. Local MCP is rejected with a helpful pointer

Local Agent Framework MCP servers (e.g., `MCPStreamableHTTPTool(name=..., url="...")` — the 1.3.0 pattern documented in [`foundry-toolbox-mcp-http.md`](foundry-toolbox-mcp-http.md)) cannot publish. `to_prompt_agent` raises `ValueError` with the message: `"Local MCP tool '<name>' cannot be published as a prompt-agent tool. Use FoundryChatClient.get_mcp_tool(...) to register a hosted MCP server instead."` — port your MCP wiring to the hosted factory first.

### 3. `tool_choice` is dropped when there are no tools

A subtle behavior in `_prepare_prompt_agent_options`: if your `agent.default_options['tools']` ended up empty (or you didn't pass tools), `tool_choice` is omitted from the resulting `PromptAgentDefinition` even if `agent.default_options['tool_choice']` was set. The Foundry definition schema rejects `tool_choice` without tools.

### 4. Model resolution: `default_options['model']` wins over `client.model`

```python
model = agent.default_options.get("model") or agent.client.model
```

If you constructed `Agent(client, default_options={"model": "<override>"})`, the override is used. This matches `Agent.__init__`'s own resolution order, so the published agent matches what you tested locally.

### 5. No auto-deploy — and no rollback

Once you call `await project.agents.create_version(definition)`, the new version exists on the Foundry side. `to_prompt_agent` itself has no rollback / dry-run flag. If you need staged rollout, version-promotion, or rollback semantics, build that around `AIProjectClient.agents.*` yourself.

### 6. Live-test status

This pattern doc was authored **without live Foundry round-trip validation** (X-stage policy). The conversion logic is exercised heavily by the 664-LOC upstream test suite ([`test_to_prompt_agent.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/tests/foundry/test_to_prompt_agent.py)), so the **`to_prompt_agent` → `PromptAgentDefinition`** half is well-covered. The **`PromptAgentDefinition` → `create_version`** half depends on your `azure-ai-projects` SDK version and your project's RBAC — verify locally before production.

## See also

- API ref: [`clients.md`](../api-reference/1.8.0/clients.md) — `FoundryChatClient` lifecycle, `get_*_tool()` hosted-tool factories (1.6.0+)
- API ref: [`feature-stages.md`](../api-reference/1.8.0/feature-stages.md) — `@experimental` warning model
- Pattern: [`canonical-agent-creation.md`](canonical-agent-creation.md) — building the local `Agent` you'll convert
- Pattern: [`hosted-bing-search.md`](hosted-bing-search.md) — example of a hosted SDK tool that round-trips cleanly via `to_prompt_agent`
- Pattern: [`foundry-toolbox-mcp-http.md`](foundry-toolbox-mcp-http.md) — local MCP (which `to_prompt_agent` rejects; port to hosted MCP via `client.get_mcp_tool(...)` first)
- Upstream tests: [`test_to_prompt_agent.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/tests/foundry/test_to_prompt_agent.py) — 664-LOC behavior catalog covering tool translation, generation param translation, error paths
