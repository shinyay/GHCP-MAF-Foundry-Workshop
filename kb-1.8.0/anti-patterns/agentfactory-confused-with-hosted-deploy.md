# Anti-pattern: confusing `AgentFactory` (local SDK) with hosted-agent deploy

> **Severity**: BLOCKER (silent semantics — script "works" locally but never reaches Foundry runtime)

## Symptom

```python
# This LOOKS like it deploys to Foundry but actually only loads the agent in-process
from agent_framework_declarative import AgentFactory

agent = AgentFactory.load_from_yaml(
    "agent.yaml",
    client=foundry_client,    # ⚠ silently ignored when yaml has `model:` block
)
result = await agent.run("Hi")  # runs LOCALLY against Foundry inference, no hosted agent created
```

## Cause

`agent-framework-declarative` is a **local agent factory** that translates a YAML
definition into a Python `Agent` object running in the calling process. It is NOT a deployment tool.

Specifically:
- Loading `agent.yaml` returns a Python `Agent` instance bound to the current process.
- The agent makes inference calls via the provided `client` (FoundryChatClient), but the agent
  itself never appears in the Foundry project's Agents list.
- Quirk: when `agent.yaml` has a `model:` block, the `client=` kwarg is silently ignored.
  Use `client_kwargs={"project_endpoint": ..., "credential": ...}` instead.

## Fix

To **deploy** an agent as a Foundry hosted agent, use the `azd ai agent` extension:

```bash
azd extension install azure.ai.agents
azd ai agent init -m <manifest-url>
azd up
```

See [`../api-reference/1.8.0/hosted-agent-deploy.md`](../api-reference/1.8.0/hosted-agent-deploy.md)
for the canonical pattern.

## When `AgentFactory` IS appropriate

- Local prototyping of agent prompts/tools (no deploy required)
- Testing YAML schema before committing
- Hybrid workflows where the agent runs in your service, not Foundry runtime

## Origin

Discovered during Cycle 5b dryrun (2026-06-13). The pre-rewrite starter
README's Path B ("AgentFactory yaml load") was misread as a hosted-deploy alternative;
verification showed it is purely local-loading semantics.

## Related

- [`azure-yaml-missing-services-block.md`](./azure-yaml-missing-services-block.md)
- [`../api-reference/1.8.0/agent-manifest-yaml.md`](../api-reference/1.8.0/agent-manifest-yaml.md)
