# Hosted Agent Deployment Pattern (1.8.0)

Microsoft Foundry hosted agents are containerized agents deployed into a
Foundry-managed runtime via the **official `azd ai agent` extension**.

> [!IMPORTANT]
> Hosted agents are currently limited to the **`northcentralus`** Azure region.
> See: [`hosted-agent-region-availability.md`](./hosted-agent-region-availability.md)

## Required toolchain

| Tool | Version | Install |
|---|---|---|
| `azd` | 1.21.3+ | `curl -fsSL https://aka.ms/install-azd.sh \| bash` |
| `azure.ai.agents` extension | preview | `azd extension install azure.ai.agents` (auto on init) |

## Canonical workflow

```bash
# 1. Initialize azd project from official starter
azd init -t Azure-Samples/azd-ai-starter-basic --location northcentralus

# 2. Add agent definition (manifest URL -> azure.yaml services: block)
azd ai agent init -m <agent-manifest-url>

# 3. Provision infrastructure + build container + publish agent
azd up

# 4. Invoke deployed agent
azd ai agent invoke <agent-name> "<message>"

# 5. Cleanup
azd down --purge --force
```

## File layout

```text
project-root/
├── azure.yaml                       # services.<agent>.{host: azure.ai.agent, language: docker}
├── infra/
│   ├── main.bicep                  # Provisions Foundry project + ACR + AppInsights
│   ├── main.parameters.json        # AI_PROJECT_DEPLOYMENTS, ENABLE_HOSTED_AGENTS, etc.
│   └── core/                       # Modular bicep sub-templates
└── src/<agent>/
    ├── agent.yaml                  # kind: hosted, protocols: [responses]
    ├── main.py                     # Wraps Agent in ResponsesHostServer
    ├── Dockerfile                  # python:3.12-slim base, CMD ["python", "main.py"]
    ├── requirements.txt            # agent-framework + agent-framework-foundry-hosting
    └── .dockerignore
```

## `azure.yaml` shape (post `azd ai agent init`)

```yaml
requiredVersions:
  extensions:
    azure.ai.agents: ">=0.1.0-preview"
services:
  <agent-name>:
    project: src/<agent-name>
    host: azure.ai.agent          # ← critical: triggers hosted-agent flow
    language: docker
    docker:
      remoteBuild: true            # ACR remote build, no local Docker needed
    config:
      container:
        resources: { cpu: "0.5", memory: 1Gi }
      deployments:
        - model: { format: OpenAI, name: gpt-4.1-mini, version: "2025-04-14" }
          name: gpt-4.1-mini
          sku: { capacity: 10, name: GlobalStandard }
      startupCommand: python main.py
infra:
  provider: bicep
  path: ./infra
```

## Container side (`src/<agent>/main.py`)

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    credential=DefaultAzureCredential(),
)
agent = Agent(client=client, instructions="...", default_options={"store": False})
ResponsesHostServer(agent).run()  # listens on port 8088
```

> [!NOTE]
> History is managed by the Foundry hosting infrastructure (`store: False` on the agent).
> The container exposes the OpenAI Responses protocol on port 8088.

## Working example

See [`templates/hosted-agent-deployment/`](../../../templates/hosted-agent-deployment/)
for a fully-tested template using this pattern.

## Anti-patterns

- ❌ Missing `services:` block → see [`azure-yaml-missing-services-block.md`](../../anti-patterns/azure-yaml-missing-services-block.md)
- ❌ Confusing `AgentFactory` (local SDK) with hosted deploy → see [`agentfactory-confused-with-hosted-deploy.md`](../../anti-patterns/agentfactory-confused-with-hosted-deploy.md)
- ❌ Using `kind: Prompt` for hosted agents → see [`agent-manifest-yaml.md`](./agent-manifest-yaml.md)
