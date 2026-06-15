# Foundry hosted agent regional availability (2026-06-13)

> [!WARNING]
> Microsoft Foundry hosted agents are currently limited to the **`northcentralus`** Azure region.
> Source: [Hosted agents concepts](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/hosted-agents) (2025-12-11 docs)

## Why this matters

`azd up` with `host: azure.ai.agent` succeeds only when `AZURE_LOCATION=northcentralus`.
Other regions will fail at the agent-publish step OR succeed at infra provisioning while the
hosted-agent capability remains unavailable (silent gap).

## How to set the region

```bash
# At azd init time
azd init -e <env> --location northcentralus

# Or after init
azd env set AZURE_LOCATION northcentralus
```

## Workshop-default region (`eastus`) coexistence

The workshop-wide default Foundry region is `eastus` + `gpt-5.4`
(see [`docs/foundry-provisioning.md § Default environment`](../../../docs/foundry-provisioning.md#default-environment)).

The `hosted-agent-deployment` template overrides this default to `northcentralus` in its
`.env.example` because hosted agents are not yet available in `eastus`. **This is an intentional
template-level carve-out**, not a change to the workshop default.

## Future state

When Microsoft expands hosted-agent availability beyond `northcentralus`, this KB and the
template's `.env.example` should be updated. Track:
- [Microsoft Foundry release notes](https://learn.microsoft.com/azure/ai-foundry/whats-new)
- [Hosted agents concept docs](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/hosted-agents)
