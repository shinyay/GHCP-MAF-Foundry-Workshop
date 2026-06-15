# Pattern: RAG with Azure AI Search (semantic mode)

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0` + `agent-framework-azure-ai-search`
> Verified against: [`microsoft/agent-framework@python-1.8.0`](https://github.com/microsoft/agent-framework/tree/python-1.8.0) — [`agent-framework-azure-ai-search/_context_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-ai-search/agent_framework_azure_ai_search/_context_provider.py)

## Goal

Ground an agent's answers in an existing **Azure AI Search** index using semantic ranker — without writing your own retrieval glue. The provider runs `before_run`, injects the top-K matching chunks as context messages, and lets the LLM answer with explicit grounding.

## When to use

- You already have content indexed in Azure AI Search (e.g., from Azure AI Search's Knowledge Base wizard, Form Recognizer pipelines, or custom indexers).
- Your index has a semantic configuration enabled.
- You want **single-step retrieval** (one search per turn) — for multi-step planning, use `mode="agentic"` instead (see [`../api-reference/1.8.0/context-providers-rag.md`](../api-reference/1.8.0/context-providers-rag.md#azureaisearchcontextprovider)).
- You want **managed identity** auth (recommended) or `AzureKeyCredential` for early dev.

## Prerequisites

| Resource | What |
|----------|------|
| Azure AI Search service | Standard tier or higher (semantic ranker requires it) |
| Search index | With a semantic configuration named (e.g., `"default"`) |
| Identity / key | Managed identity with `Search Index Data Reader` role, **or** an `api_key` |

```bash
pip install "agent-framework-foundry==1.8.0" "agent-framework-azure-ai-search"
```

## Env vars (recommended)

```bash
AZURE_SEARCH_ENDPOINT="https://my-search.search.windows.net"
AZURE_SEARCH_INDEX_NAME="company-docs"
# Either:
AZURE_SEARCH_API_KEY="..."           # key-based dev
# Or rely on managed identity via DefaultAzureCredential (no env var)

FOUNDRY_PROJECT_ENDPOINT="https://<project>.services.ai.azure.com/api/projects/<proj>"
FOUNDRY_MODEL="gpt-5-4"
```

## Code — semantic RAG with managed identity

```python
import asyncio
import os
from agent_framework import AgentSession
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_ai_search import AzureAISearchContextProvider
from azure.identity.aio import DefaultAzureCredential


async def main() -> None:
    async with (
        DefaultAzureCredential() as foundry_cred,
        DefaultAzureCredential() as search_cred,
        FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=foundry_cred,
        ) as client,
    ):
        rag = AzureAISearchContextProvider(
            endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
            index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
            credential=search_cred,
            mode="semantic",
            top_k=5,
            semantic_configuration_name="default",
        )

        agent = client.as_agent(
            name="company-policy-assistant",
            instructions=(
                "Answer using the context provided. "
                "If the context does not contain the answer, say so explicitly. "
                "Cite the source title when available."
            ),
            context_providers=[rag],
        )

        session = AgentSession()
        response = await agent.run(
            "What is the parental leave policy?",
            session=session,
        )
        print(response.messages[-1].text)


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

- **`async with` everywhere** — both credentials and the chat client are async resources. See [`../anti-patterns/missing-async-with-cleanup.md`](../anti-patterns/missing-async-with-cleanup.md).
- **Separate credentials for Foundry and Search** — they typically resolve to the same managed identity, but the providers manage their own client lifecycles, so don't share one credential object.
- **`mode="semantic"`** — single-step search with the semantic ranker. Lowest latency.
- **`top_k=5`** — five chunks injected into context per turn. Tune based on chunk size and model context window.
- **`semantic_configuration_name="default"`** — must match an existing config in your index. Confirm in the Azure portal under your index → Semantic configurations.
- **`context_providers=[rag]`** — the provider is attached at agent construction time. The framework wires `before_run` / `after_run` automatically.

## Verification

```bash
python rag_with_aisearch.py
```

Expected:
- The first call shows the retrieval context being assembled (visible in OTel spans if you wire `configure_otel_providers(...)`).
- The response cites content from your indexed docs.
- If you ask an off-topic question (not covered by the index), the agent says so rather than hallucinating — confirming the instruction took effect.

## Common mistakes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `HttpResponseError: ... (403) Forbidden` from AI Search | Missing `Search Index Data Reader` role on your identity | Grant the role on the **search service** scope |
| Empty results consistently | Wrong `semantic_configuration_name` | Check the configured name in the Azure portal |
| `RuntimeError: settings missing field` | Neither kwargs nor env vars set | Provide `endpoint`/`index_name`/credential at construction OR set `AZURE_SEARCH_*` env vars |
| Hallucinated answers despite context | Instructions don't tell the model to *use* the context | Strengthen instructions: "answer **only** from the context" |
| Slow first call | Index cold-start on AI Search | Normal; warm up with a single query at startup if latency matters |
| `ValueError: ... knowledge_base_name ...` | Used wrong `@overload` (passed both `index_name` and `knowledge_base_name`) | Pass exactly one — `index_name` for semantic/agentic-from-index, `knowledge_base_name` for agentic-from-existing-KB |

## Variant — quick key-auth for early dev

```python
rag = AzureAISearchContextProvider(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    api_key=os.environ["AZURE_SEARCH_API_KEY"],
    mode="semantic",
    top_k=5,
    semantic_configuration_name="default",
)
```

> [!WARNING]
> Do **not** ship API keys to production. Managed identity / `DefaultAzureCredential` is the only acceptable production auth for AI Search.

## Variant — agentic mode (multi-step planning)

Use `mode="agentic"` when a single search is not enough — e.g., the user's question requires combining several sub-queries. Agentic mode creates an AI Search Knowledge Base from your index and uses an Azure OpenAI reasoning model to plan retrievals.

```python
rag = AzureAISearchContextProvider(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name="company-docs",
    credential=search_cred,
    mode="agentic",
    azure_openai_resource_url="https://my-aoai.openai.azure.com",
    model="gpt-5-4",                         # reasoning model (workshop default — gpt-5 family is reasoning-capable)
    retrieval_reasoning_effort="medium",
    knowledge_base_output_mode="extractive_data",
    top_k=5,
)
```

Pros: better for complex queries. Cons: higher latency, costs an extra LLM call per turn for planning.

## See also

- [`../api-reference/1.8.0/context-providers-rag.md`](../api-reference/1.8.0/context-providers-rag.md#azureaisearchcontextprovider) — all 3 overloads and option-by-option reference
- [`../api-reference/1.8.0/sessions.md`](../api-reference/1.8.0/sessions.md#contextprovider) — `ContextProvider` lifecycle
- [`rag-with-file-search.md`](rag-with-file-search.md) — alternative RAG using Foundry's hosted File Search tool (different mechanism — tool vs provider)
- [`../anti-patterns/using-the-wrong-memory-primitive.md`](../anti-patterns/using-the-wrong-memory-primitive.md) — when to use a `ContextProvider` vs `HistoryProvider`
- [Azure AI Search semantic ranker docs](https://learn.microsoft.com/azure/search/semantic-search-overview)

Upstream source: [`agent-framework-azure-ai-search/_context_provider.py:L157-L285`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/azure-ai-search/agent_framework_azure_ai_search/_context_provider.py#L157-L285).
