# Pattern: Hosted Bing Web Search (Grounding)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: parent demo `src/demo2_web_search.py`
> See also: [API ref — `tools-hosted.md`](../api-reference/1.8.0/tools-hosted.md#bing-grounding-canonical-pattern)

## Goal

Give an agent the ability to **search the web with citations** using Bing's grounding API. Use this when your agent needs up-to-date information that isn't in the model's training data.

## When to use

- ✅ The user asks about recent events, prices, schedules, anything time-sensitive.
- ✅ You want **citations / source URLs** in the answer (Bing grounding provides them).
- ❌ You want generic web search without citations → use `client.get_web_search_tool()` instead.
- ❌ Your data is in your own knowledge base → use [`rag-with-file-search.md`](rag-with-file-search.md).

## Prerequisite — Bing connection in Foundry

1. Foundry portal → your project → **Connected resources** → **Add connection** → **Bing Search**.
2. Choose **"Grounding with Bing Search"** SKU (not "Bing Search v7" — that's a different product).
3. Copy the **project connection ID** (an ARM resource ID).
4. Add to `.env`:
   ```
   BING_CONNECTION_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<acct>/projects/<proj>/connections/<conn>
   ```

## Discovering or provisioning the Bing connection

If you inherited a Foundry project from someone else (workshop facilitator, team lead, IT), check whether a Bing connection already exists **before** clicking "Add connection" — Foundry projects can already carry a grounding connection from prior demos or templates.

> [!NOTE]
> Foundry project connections are **not surfaced by `az resource list`** — they're sub-resources of the project, not standalone ARM resources. The canonical CLI discovery paths are below.

### Discover an existing connection (read-only)

The cleanest path, when your `az` is up to date:

```bash
# Safety: READ
# Source: https://learn.microsoft.com/cli/azure/cognitiveservices/account/project/connection#az-cognitiveservices-account-project-connection-list
az cognitiveservices account project connection list \
  --resource-group <rg> \
  --account-name <account> \
  --project-name <project> \
  --query "[?properties.category=='GroundingWithBingSearch'].{name:name, id:id, target:properties.target, isDefault:properties.isDefault}" \
  --output table
```

Fallback when that subcommand isn't available in your CLI version (Foundry surfaces evolve quickly):

```bash
# Safety: READ
# Source: verify against Microsoft Learn before running — https://learn.microsoft.com/azure/ai-foundry/how-to/connections-add (API version may change)
az rest \
  --method get \
  --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections?api-version=2025-04-01-preview" \
  --query "value[?properties.category=='GroundingWithBingSearch'].{name:name, id:id}" \
  --output table
```

If a row appears, copy its `id` into `BING_CONNECTION_ID` — the `id` MUST include `/projects/<project>/connections/<name>`, not the account-level path.

### Provision a new connection

If no row appears, **create the connection via the Foundry portal** (the documented path in 1.8.0 — the 4 steps from the Prerequisite section above). There is no native `az` subcommand to create a Foundry connection today; portal-first is the supported flow. For the broader provisioning context (resource group / Foundry account / project / model deployment), see [`docs/foundry-provisioning.md` § Path A](../../docs/foundry-provisioning.md#path-a--azure-portal-slowest-most-discoverable) and [Path B](../../docs/foundry-provisioning.md#path-b--azure-cli-good-for-one-off-scripted-setup).

After creation, re-run the discovery command above to capture the new connection's `id`, then add it to `.env` as shown in the Prerequisite section.

## Code

```python
import asyncio
import os
from pathlib import Path

from agent_framework.foundry import FoundryChatClient
from agent_framework.exceptions import ChatClientInvalidResponseException
from azure.ai.projects.models import (
    BingGroundingSearchConfiguration,
    BingGroundingSearchToolParameters,
    BingGroundingTool,
)
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


# --- .env fill-only loader ---
for k, v in dotenv_values(Path(__file__).resolve().parents[1] / ".env").items():
    if v is not None and not (os.getenv(k) or "").strip():
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def build_bing_tool() -> dict:
    """Build a Bing Grounding tool config from BING_CONNECTION_ID."""
    connection_id = _require_env("BING_CONNECTION_ID")
    cfg = BingGroundingSearchConfiguration()
    cfg.project_connection_id = connection_id
    cfg.market = "en-US"
    cfg.count = 5
    return BingGroundingTool(
        bing_grounding=BingGroundingSearchToolParameters(search_configurations=[cfg])
    ).as_dict()


async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")
    bing_tool = build_bing_tool()

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=project_endpoint, model=model, credential=cred
        )
        async with client.as_agent(
            name="venue_specialist",
            instructions=(
                "You are a venue researcher. Use web search to find current venue "
                "options. Always cite source URLs you used."
            ),
            tools=[bing_tool],
        ) as agent:
            try:
                result = await agent.run(
                    "Find 3 venues for a 50-person corporate event in Seattle in Dec 2026."
                )
            except ChatClientInvalidResponseException as ex:
                if "Failed to resolve model info" in str(ex):
                    raise RuntimeError(
                        "FOUNDRY_MODEL deployment name doesn't exist in this project. "
                        "Check the Foundry portal → Models + endpoints."
                    ) from ex
                raise
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| `BingGroundingTool(...).as_dict()` | Canonical form used by the parent demos. Yes, `client.get_bing_grounding_tool(connection_id=...)` exists since 1.6.0 — but the `azure.ai.projects.models` form exposes `BingGroundingSearchConfiguration` for finer control of `market` / `count`. |
| `BingGroundingSearchConfiguration.market = "en-US"` | Localizes search results. Set to `"ja-JP"` for Japanese results, etc. |
| `BingGroundingSearchConfiguration.count = 5` | Top-K results from Bing. Higher = more cost + token use. |
| Instruction: "Always cite source URLs" | Bing returns URLs, but the model may omit them. Explicit instruction increases citation rate. |
| `try/except ChatClientInvalidResponseException` | Surfaces the two most common Foundry config errors (model name, RBAC) with actionable messages instead of opaque stack traces. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Using "Bing Search v7" connection (not "Grounding with Bing Search") | They're different products. Only the grounding SKU works with `BingGroundingTool`. Re-create the connection. |
| Forgetting `.as_dict()` on the factory return | `tools=[BingGroundingTool(...)]` ignores the dict shape. Always `.as_dict()`. |
| Missing `BING_CONNECTION_ID` env var | Fail-fast with the `_require_env()` pattern (see above). |
| Importing `HostedBingSearchTool` (removed in 1.0 GA) | Use `BingGroundingTool` or `client.get_bing_grounding_tool(...)`. |

## How to detect (in code review)

```bash
# Searches for the wrong import.
rg "HostedBingSearchTool|HostedWebSearchTool" --type py
```

## Verification

```bash
# 1. Make sure your Foundry connection exists in the project.
az login
# 2. Set .env with BING_CONNECTION_ID + FOUNDRY_PROJECT_ENDPOINT + FOUNDRY_MODEL.
# 3. Run:
python path/to/this/script.py
```

Expected: 3 venue suggestions with at least one source URL each.

## See also

- [`tools-hosted.md`](../api-reference/1.8.0/tools-hosted.md) — full Bing config reference
- [`rag-with-file-search.md`](rag-with-file-search.md) — when your data is private
- [`error-handling.md`](error-handling.md) — `ChatClientInvalidResponseException` pattern
- [`../anti-patterns/removed-apis-since-1.0.md`](../anti-patterns/removed-apis-since-1.0.md)
