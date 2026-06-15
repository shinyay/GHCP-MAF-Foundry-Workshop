# Anti-pattern: `azure.yaml` missing `services:` block

> **Severity**: BLOCKER (silent-PASS — `azd deploy` returns SUCCESS without deploying anything)

## Symptom

```bash
$ azd deploy
SUCCESS: Your services have been deployed in 0 seconds.
```

…but no service was actually deployed. The Azure portal shows no new resources/changes.

## Cause

`azure.yaml` lacks a `services:` block:

```yaml
# ❌ BAD — azd deploy is a no-op
name: my-agent
infra:
  provider: bicep
  path: ./infra
# (no `services:` key)
```

`azd deploy` iterates over the services map. Empty map = zero work = SUCCESS exit code.

## Fix

Declare at least one service:

```yaml
# ✅ GOOD
name: my-agent
requiredVersions:
  extensions:
    azure.ai.agents: ">=0.1.0-preview"
services:
  hello-foundry:
    project: src/hello-foundry
    host: azure.ai.agent
    language: docker
    docker:
      remoteBuild: true
    config:
      # ... full config from `azd ai agent init`
infra:
  provider: bicep
  path: ./infra
```

For hosted Foundry agents, use **`azd ai agent init -m <manifest-url>`** which generates the
correct `services:` block automatically. See [`../api-reference/1.8.0/hosted-agent-deploy.md`](../api-reference/1.8.0/hosted-agent-deploy.md).

## Origin

Discovered during Cycle 5b dryrun of `templates/hosted-agent-deployment/` (2026-06-13).
The pre-rewrite starter shipped with infra-only `azure.yaml`, causing `azd deploy` to silent-PASS
while no agent was ever published. Permanently guarded by
[`tests/test_template_hosted_agent_deployment.py::test_azure_yaml_has_services_block`](../../tests/test_template_hosted_agent_deployment.py).

## Related

- [`agentfactory-confused-with-hosted-deploy.md`](./agentfactory-confused-with-hosted-deploy.md)
- [`../api-reference/1.8.0/hosted-agent-deploy.md`](../api-reference/1.8.0/hosted-agent-deploy.md)
