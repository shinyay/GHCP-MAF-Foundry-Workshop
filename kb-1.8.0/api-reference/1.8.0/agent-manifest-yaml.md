# `agent.yaml` schema for Foundry hosted agents (1.8.0)

Foundry hosted agents use the `microsoft/AgentSchema` v1.0 `ContainerAgent.yaml` schema:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/microsoft/AgentSchema/refs/heads/main/schemas/v1.0/ContainerAgent.yaml

kind: hosted                       # ← REQUIRED: 'hosted' for Foundry runtime
name: <agent-name>                 # alphanumeric + hyphens
description: |
    Free-form description.
metadata:
    tags:
        - Agent Framework
        - Responses Protocol
protocols:                         # ← REQUIRED: at least one protocol
    - protocol: responses
      version: 1.0.0
resources:
    cpu: "0.5"                     # vCPU (string)
    memory: 1Gi                    # memory size
environment_variables:
    - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
      value: gpt-4.1-mini
```

## Field reference

| Field | Required | Notes |
|---|---|---|
| `kind` | ✅ | Must be `hosted` (NOT `Prompt`; that is for local `AgentFactory`). |
| `name` | ✅ | Becomes the agent identifier in Foundry. Must match `azure.yaml` services key. |
| `protocols[]` | ✅ | At least one. Common: `responses` (conversational), `invocations` (request-response). |
| `resources.{cpu,memory}` | ❌ | Defaults: 0.5 vCPU, 1 GiB. |
| `environment_variables[]` | ❌ | Inject env vars into the container at runtime. |

## Protocols comparison

| Protocol | Use for | Why |
|---|---|---|
| `responses` (v1.0.0) | Chatbots, multi-turn Q&A, streaming | Platform manages conversation history; OpenAI-compatible |
| `invocations` (v1.0.0) | One-shot synchronous request/response | Lower-overhead RPC style |

## ❌ Anti-pattern: `kind: Prompt`

```yaml
# This is for LOCAL AgentFactory only — CANNOT be deployed via azd ai agent
kind: Prompt
name: hello-foundry
model:
  id: gpt-5-4
  provider: Foundry
```

Use this format only when loading agents locally via the `agent-framework-declarative`
package. For Foundry deploy, use `kind: hosted` as shown above.

See also: [`hosted-agent-deploy.md`](./hosted-agent-deploy.md), [`../../anti-patterns/agentfactory-confused-with-hosted-deploy.md`](../../anti-patterns/agentfactory-confused-with-hosted-deploy.md)
