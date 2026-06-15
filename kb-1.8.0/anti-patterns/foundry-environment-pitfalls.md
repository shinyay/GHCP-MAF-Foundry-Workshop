# Anti-Pattern: Foundry Environment Configuration Pitfalls

> Status: **Active hazard** — these are the most common runtime / deploy-time failures when bringing up a Microsoft Foundry agent.
> Affects: `agent-framework-foundry==1.8.0` against Microsoft Foundry projects provisioned via Azure portal / `az` CLI / Bicep.
> Severity ranges from **High** (silent wrong behavior — agent picks the wrong model deployment) to **Critical** (deploy fails / credentials leaked).

This page consolidates the environment-level pitfalls that are NOT code bugs but show up as runtime failures: RBAC, model deployment naming, connection IDs, DNS, regional availability, identity assignment.

For code-level anti-patterns (e.g., sync credentials in async, empty `.env` in Codespaces), see the other pages in `kb/anti-patterns/`. This page is the **Foundry environment** companion the `foundry-ops` chatmode cites when emitting triage / remediation steps.

> [!IMPORTANT]
> Every Azure CLI snippet below uses placeholders (`<sub>`, `<rg>`, `<account>`, `<project>`). **Verify the exact subcommand / argument set against the linked Microsoft Learn URL before running** — the Azure CLI surface changes frequently and may drift between CLI minor releases. Treat every snippet as a "scaffold to verify", not a copy-paste fact.

---

## P-1 — Missing RBAC at project scope

### Symptom

```
azure.core.exceptions.HttpResponseError: (Unauthorized) The request is not authorized.
Code: Unauthorized
```

Or, more subtly, the agent client reports `403 Forbidden` when calling the Foundry data plane (chat completions, model listings).

### Why it's wrong

The Foundry data plane requires **explicit role assignment at the project scope** for a developer identity:

| Role | Where it lives | Why |
|---|---|---|
| `Azure AI User` *(renamed `Foundry User` in 2025; both names map to role ID `53ca6127-db72-4b80-b1b0-d745d6d5456d`)* | Foundry project scope | Primary data-plane access — call model deployments, run inference, read project assets |
| `Azure AI Developer` | Foundry project scope (or higher) | Broader devops — create/manage agents, connections, evaluations, deployments. Required only when the developer manages the project (not pure consumers). |
| `Cognitive Services User` *(situational)* | Underlying AI Services account scope (parent of the project) | Only required when calling Cognitive Services integrations linked to the project (Content Safety, Vision, etc.). Not required for plain `FoundryChatClient` calls. |

> [!NOTE]
> The role `Foundry User` is the **2025 rename** of `Azure AI User`. Same role ID, same permissions — only the display name changed. Both names appear in `az role assignment list` output depending on the CLI / portal version. The parent template repo (`getting-started-with-agent-framework`) and older Bicep templates use the legacy name `Azure AI User` (or even `Cognitive Services User` for older inference paths). When in doubt, look up role ID `53ca6127-db72-4b80-b1b0-d745d6d5456d`.

Both Foundry roles are scoped at the **Foundry project resource** (not the parent AIServices account, not the subscription). A subscription-level `Owner` does NOT automatically inherit these roles for the data plane in all tenants — explicit assignment is required.

### How to detect (READ — safe to run)

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/ad/signed-in-user#az-ad-signed-in-user-show
# Step 1: get the principal ID of the current signed-in user
# NOTE: surfaces the developer's principal ID — warn before piping to disk or shared logs
az ad signed-in-user show --query id -o tsv \
  --subscription <sub>
```

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/role/assignment#az-role-assignment-list
# Step 2: list role assignments for that principal at the project scope
# (use the principal ID printed by step 1)
az role assignment list \
  --assignee <principal-id-from-step-1> \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>" \
  --subscription <sub> \
  -o table
```

Expected: at least one row for `Azure AI User` (or `Foundry User` — same role) at the project scope. If your code also calls Cognitive Services integrations, you need `Cognitive Services User` at the **account** (parent) scope. If missing, see remediation.

> Source to verify role catalogue: <https://learn.microsoft.com/azure/ai-foundry/concepts/rbac-azure-ai-foundry>

### How to fix (MUTATING-IDEMPOTENT — safe to re-run; if assignment exists, command reports `RoleAssignmentExists` — treat as success and verify with `az role assignment list`)

```bash
# Safety: MUTATING-IDEMPOTENT
# Source: https://learn.microsoft.com/cli/azure/role/assignment#az-role-assignment-create
# Use the principal ID from the step-1 READ above
az role assignment create \
  --assignee <principal-id-from-step-1> \
  --role "Azure AI User" \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>" \
  --subscription <sub>
```

> [!WARNING]
> **Propagation delay**: Azure RBAC can take **up to 5 minutes** to propagate after `az role assignment create` returns success. If your next agent call still 403s, wait and retry before re-running the role assignment.

> Source to verify: <https://learn.microsoft.com/azure/role-based-access-control/troubleshooting>

---

## P-2 — Model deployment name mismatch

### Symptom

```
agent_framework.exceptions.AgentInvalidResponseException:
  The API deployment for this resource does not exist.
  Deployment: gpt4omini
```

The agent constructs cleanly, the credential is valid, but the first `agent.run(...)` raises because `FOUNDRY_MODEL` is the **model family identifier** (e.g., `gpt-5.4`) and not the **deployment name** (e.g., `gpt-5-4`).

### Why it's wrong

In Foundry, the value `FoundryChatClient(..., model=...)` requires is the **deployment name** you chose when creating the deployment in **Models + endpoints**, NOT the underlying model identifier. The two are usually different by convention (deployment names often add a suffix like `-deploy` or `-prod`).

This is the same trap documented in `.env.example`:

```
# This is the NAME of the deployment you created in "Models + endpoints",
# NOT the underlying model family identifier (e.g., "gpt-5-4", not "gpt-5.4").
FOUNDRY_MODEL=
```

### How to detect (READ — safe to run)

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/cognitiveservices/account/deployment#az-cognitiveservices-account-deployment-list
# List the actual deployment names in your Foundry project
az cognitiveservices account deployment list \
  --name <account> \
  --resource-group <rg> \
  --subscription <sub> \
  -o table
```

Compare the `Name` column to `FOUNDRY_MODEL` in `.env`. If they don't match exactly, fix `.env` — do NOT rename the Azure deployment to match `.env` (renaming requires re-deploying the model).

### How to fix

Edit `.env`. **No Azure mutation required.** Re-run the agent.

---

## P-3 — DNS resolution failure for Foundry endpoint

### Symptom

```
socket.gaierror: [Errno -2] Name or service not known
```

Or `httpx.ConnectError: Cannot connect to host <account>.services.ai.azure.com:443`.

### Why it's wrong

Three common causes (in order of likelihood):

1. **Typo in `FOUNDRY_PROJECT_ENDPOINT`** — the URL should be `https://<account>.services.ai.azure.com/api/projects/<project>` exactly. A typo in the account name OR a missing `/api/projects/<project>` suffix is the most common cause.
2. **Private networking / Codespaces egress** — the Foundry account has a private endpoint and the developer is on a Codespaces container that cannot resolve the private DNS zone.
3. **Region typo / account moved** — the account exists in a different region; the public DNS name resolves but to a non-existent host.

### How to detect (READ — safe to run)

```bash
# Safety: READ
# Source: local shell — no Azure call
# 1. Verify the endpoint string is well-formed (expect: https://<account>.services.ai.azure.com/api/projects/<project>)
echo "$FOUNDRY_PROJECT_ENDPOINT"
```

```bash
# Safety: READ
# Source: local DNS resolver — no Azure call
# 2. Resolve the DNS A record (extract host from endpoint)
nslookup "$(echo "$FOUNDRY_PROJECT_ENDPOINT" | sed -E 's|https?://([^/]+).*|\1|')"
```

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/cognitiveservices/account#az-cognitiveservices-account-show
# 3. Confirm the account exists where you think it does
az cognitiveservices account show \
  --name <account> \
  --resource-group <rg> \
  --subscription <sub> \
  --query "{name:name, region:location, customSubDomainName:properties.customSubDomainName, privateEndpoints:properties.privateEndpointConnections}" \
  -o json
```

> Additional reference for private networking diagnosis: <https://learn.microsoft.com/azure/ai-services/cognitive-services-virtual-networks>

### How to fix

| Cause | Fix |
|---|---|
| Typo in endpoint | Correct `.env`. No mutation. |
| Private networking | Configure the Codespaces / dev container to resolve the private DNS zone (typically `privatelink.cognitiveservices.azure.com`), OR use a tenant-allowed public endpoint, OR run from a VM inside the private network. **Decision needs an admin** — `foundry-ops` should hand off to network admin, not invent a fix. |
| Region typo | Verify the actual region via `az cognitiveservices account show`; correct the endpoint. |

---

## P-4 — Invalid or wrong-kind connection ID

### Symptom

```
agent_framework.exceptions.AgentInvalidResponseException:
  The specified connection is not of the expected type.
```

Common cases: `BING_CONNECTION_ID` actually points to an Azure OpenAI connection, or to a connection at the wrong scope (account-level vs project-level).

### Why it's wrong

Foundry connections are scoped to a specific resource type. A "Grounding with Bing Search" connection is a different kind from an "Azure AI Search" connection — the chatmode that requests a connection ID must validate the **kind** matches the tool's expectation.

The ARM ID shape is precise:

```
/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections/<conn-name>
```

A common mistake is pointing to the **account-level** connection path (no `/projects/<project>`) — Foundry data plane requires the **project-level** path for project-scoped tools.

### How to detect (READ — safe to run)

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/cognitiveservices/account/project/connection#az-cognitiveservices-account-project-connection-list
# Preferred: project-scope CLI shape (introduced for Foundry projects)
az cognitiveservices account project connection list \
  --name <account> \
  --project-name <project> \
  --resource-group <rg> \
  --subscription <sub> \
  -o table
```

If the `az cognitiveservices account project connection list` subcommand is not yet available in your CLI version (Foundry surfaces evolve quickly), fall back to a generic ARM `GET`:

```bash
# Safety: READ
# Source: verify against Microsoft Learn before running — https://learn.microsoft.com/azure/ai-foundry/how-to/connections-add (API version may change)
az rest --method GET \
  --uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections?api-version=2024-10-01-preview" \
  --subscription <sub> \
  --query "value[].{name:name, kind:properties.category, target:properties.target}" \
  -o table
```

(API version may change — check Microsoft Learn for the current stable version.)

### How to fix

Compare the connection's `kind` / `category` against what the tool expects (`Bing.Grounding` for Bing, `AzureAISearch` for Azure AI Search, `AzureOpenAI` for Azure OpenAI). Update `.env` to point to the correct connection. **No Azure mutation required** if a correct connection already exists; if you need to create one, see Microsoft Learn.

---

## P-5 — Model not available in region / quota exhausted

### Symptom

```
azure.core.exceptions.HttpResponseError: (InvalidArgument) Model <model> not available in region <region>
```

Or, during provisioning:

```
The deployment failed because quota for this model has been exhausted in this subscription/region.
```

### Why it's wrong

Foundry model availability is **per-region** and **per-subscription quota**. A model that works in `eastus` may not be in `westeurope`; quota for `gpt-5.4` is separate from `gpt-4.1` and is per-region.

### How to detect (READ — safe to run)

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/cognitiveservices/account#az-cognitiveservices-account-list-models
# What models are available in this region for this account?
az cognitiveservices account list-models \
  --name <account> \
  --resource-group <rg> \
  --subscription <sub> \
  -o table
```

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/cognitiveservices/account#az-cognitiveservices-account-list-usage
# Check quota for this account (per-model TPM / RPM usage vs limit, per region)
az cognitiveservices account list-usage \
  --name <account> \
  --resource-group <rg> \
  --subscription <sub> \
  -o table
```

> Quota concepts (per-region, per-model, per-subscription): <https://learn.microsoft.com/azure/ai-services/openai/quotas-limits>

### How to fix

- If the model isn't in the region: pick a region that has it (the Foundry portal's region picker shows availability) and re-deploy the model.
- If quota is exhausted: request a quota increase via the Foundry portal (Models + endpoints → Quotas → Request increase) OR reduce the per-deployment TPM (tokens-per-minute) on a less-critical deployment.

Quota increases are **not** `az`-callable in most subscriptions — escalate to the Azure portal flow.

---

## P-6 — Managed identity not assigned to the deployed workload

### Symptom

A Function App, App Service, or AKS workload that runs the agent reports `Unauthorized` against the Foundry data plane even though the developer's `az login` works locally.

### Why it's wrong

`AzureCliCredential` works locally because it picks up the developer's `az login` identity. In production, the workload runs as its own identity — and the system-assigned or user-assigned **managed identity** of the App Service / Function App / Container App / AKS pod must be granted the same `Azure AI User` (= `Foundry User`) role at the Foundry project scope (plus `Cognitive Services User` at the **AI Services account** scope only when the workload calls cognitive services integrations).

### How to detect (READ — safe to run)

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/webapp/identity#az-webapp-identity-show
# Step 1: get the principal ID the workload runs as
# NOTE: surfaces the workload's principal ID — warn before piping to disk or shared logs
az webapp identity show \
  --name <webapp-name> \
  --resource-group <rg> \
  --subscription <sub> \
  --query principalId \
  -o tsv
```

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/role/assignment#az-role-assignment-list
# Step 2: check that identity's role assignments at the project scope
# (use the principal ID from step 1)
az role assignment list \
  --assignee <principal-id-from-step-1> \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>" \
  --subscription <sub> \
  -o table
```

> Managed identity concepts: <https://learn.microsoft.com/azure/app-service/overview-managed-identity>

### How to fix (MUTATING-IDEMPOTENT — safe to re-run; `RoleAssignmentExists` on re-run = success)

Same `az role assignment create` shape as P-1, but with the workload's managed identity principal ID instead of the developer's signed-in user. Use role `Azure AI User` (= `Foundry User`).

> [!WARNING]
> **Never** put account keys or connection strings into `.env` as a "fix" for missing managed identity. Managed identity is the secure path; rotation of leaked keys is much more painful than a one-time role assignment.

---

## P-7 — FoundryEvals default judge is gpt-4o (deprecated)

### Symptom

```
azure.core.exceptions.HttpResponseError: (DeploymentNotFound) The API deployment for this resource does not exist.
```

Or, when `gpt-4o` actually *is* deployed in the project:

```
azure.core.exceptions.HttpResponseError: (ServiceModelDeprecated) The model 'gpt-4o' has been deprecated.
```

Or, more subtly: evaluations succeed but score against a different judge than the rest of the stack expects — quality trends become inconsistent with production.

### Why it's wrong

`FoundryEvals(...)` in `agent-framework-foundry==1.8.0` hard-codes `gpt-4o` as the fallback judge model when the caller omits `model=`. The fallback lives in [`_foundry_evals.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/foundry/agent_framework_foundry/_foundry_evals.py).

This breaks for two reasons:

1. **Most workshop Foundry projects do not have `gpt-4o` deployed.** The workshop default in `eastus` is `gpt-5-4` (`gpt-5.4` family, version `2026-03-05`, `GlobalStandard`); see [`docs/foundry-provisioning.md` § Default environment](../../docs/foundry-provisioning.md). Calling `FoundryEvals()` without `model=` immediately fails with `DeploymentNotFound`.
2. **`gpt-4o` is deprecated.** Even when `gpt-4o` *is* deployed, Foundry now returns `ServiceModelDeprecated` and the evaluation aborts.

The fallback is **not** picked up from `FOUNDRY_MODEL` — that variable feeds the agent under test, not the judge. The judge model is a separate dimension the caller must opt into.

### How to detect (READ — safe to run)

Scan repository source (NOT `kb/`, which intentionally documents wrong examples in anti-patterns):

```bash
rg -n "FoundryEvals\(" tests templates examples --glob "*.py"
```

For each hit, inspect whether the call passes `model=` (or threads `client=FoundryChatClient(... model=...)`). Any `FoundryEvals(...)` instantiation without an explicit judge model is broken at runtime against the workshop default project.

### How to fix

Always pass `model='gpt-5-4'` (or the value of `FOUNDRY_JUDGE_MODEL`) explicitly:

```python
import os
from azure.identity.aio import AzureCliCredential
from agent_framework.foundry import FoundryChatClient, FoundryEvals

judge_model = os.environ.get("FOUNDRY_JUDGE_MODEL", "gpt-5-4")
async with AzureCliCredential() as cred:
    evals = FoundryEvals(
        client=FoundryChatClient(credential=cred, model=judge_model),  # REQUIRED — do not rely on the SDK default
    )
```

> [!IMPORTANT]
> `FOUNDRY_JUDGE_MODEL` is a **repo convention**, not an SDK-recognized variable. The Foundry SDK does not read it on its own. Every call site that constructs `FoundryEvals(...)` must read the env var and pass `model=` explicitly. Setting `FOUNDRY_JUDGE_MODEL=…` in `.env` without code that consumes it does nothing.

Each `.env.example` in this repo carries the optional `FOUNDRY_JUDGE_MODEL=gpt-5-4` comment so the convention is discoverable from a fresh checkout.

---

## Severity / safety classes used by `foundry-ops`

The `foundry-ops` chatmode tags every emitted command with a safety class. The taxonomy:

| Class | Meaning | Examples |
|---|---|---|
| `READ` | Pure read; no state change (NOTE: if the command surfaces tenant/sub/principal IDs, warn before piping to disk) | `az ... list`, `az ... show`, `az ad signed-in-user show`, `nslookup`, `curl -v` |
| `MUTATING-IDEMPOTENT` | Re-running produces the same end state | `az role assignment create` (existing assignment is reported, not duplicated) |
| `MUTATING-NON-IDEMPOTENT` | Re-running creates additional resources or causes errors | `az cognitiveservices account deployment create`, `az resource create` |
| `DESTRUCTIVE-RECOVERABLE` | Soft-delete or removable assignment; recoverable within retention window | `az role assignment delete`, `az cognitiveservices account delete` (soft-deletes for 7-14 days) |
| `DESTRUCTIVE-IRREVERSIBLE` | Hard delete / purge / unrecoverable | `az cognitiveservices account purge`, `az keyvault key delete --no-wait` after soft-delete window |
| `OBSERVABILITY-ONLY` | Trace export / span emission; no resource mutation but generates billable telemetry | OpenTelemetry exporter calls, Application Insights ingestion |

`foundry-ops` MUST prefix every emitted command block with `Safety: <class>`. DESTRUCTIVE-* classes require an explicit confirmation gate and the chatmode MUST NOT emit the unguarded command in the same block.

---

## See also

- `kb/anti-patterns/empty-env-vars-codespaces.md` — `.env` empty-string injection in Codespaces / Dev Containers
- `kb/anti-patterns/devui-production-defaults.md` — DevUI workshop defaults are unsafe in production
- `kb/anti-patterns/instrumentation-implicit-on-1.6.md` — OTel default-on in 1.6.0; how to opt out
- `kb/anti-patterns/eval-as-test-substitute.md` — broader EVALS-vs-tests confusion (P-7 companion)
- `kb/patterns/agent-evaluation-foundry.md` — Foundry-hosted LLM-as-judge pattern (P-7 companion)
- `kb/api-reference/1.8.0/evaluation.md` — canonical EVALS surface (`@experimental(feature_id=ExperimentalFeature.EVALS)`)
- `kb/api-reference/1.8.0/security.md` — IFC / prompt-injection defense (FIDES — experimental)
- `docs/foundry-provisioning.md` — repo-local Foundry provisioning pointer (PR-M companion)

### Hosted-agent-specific anti-patterns (`azd ai agent` extension path)

The 5 entries below are scoped to the Foundry **hosted-agent** container deployment path
(canonical `azd ai agent` extension pattern). They complement the P-1 through P-7 environment-wide
pitfalls above and are cited from the `foundry-ops` Triage Catalogue § F.

- `kb/api-reference/1.8.0/hosted-agent-deploy.md` — canonical `azd ai agent` extension workflow
- `kb/api-reference/1.8.0/agent-manifest-yaml.md` — `kind: hosted` vs `kind: Prompt` schema choice
- `kb/api-reference/1.8.0/hosted-agent-region-availability.md` — `northcentralus`-only constraint
- `kb/anti-patterns/azure-yaml-missing-services-block.md` — silent-PASS `azd deploy` BLOCKER
- `kb/anti-patterns/agentfactory-confused-with-hosted-deploy.md` — local SDK vs hosted deploy confusion
