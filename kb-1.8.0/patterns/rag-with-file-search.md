# Pattern: RAG with Hosted File Search

> Status: **Stable**
> Pinned: `agent-framework-foundry==1.8.0`
> Verified against: parent demo `src/demo8_rag.py`
> See also: [API ref — `tools-hosted.md`](../api-reference/1.8.0/tools-hosted.md#file-search-rag-with-hosted-vector-store)

## Goal

Give an agent the ability to **search a private corpus** (PDFs, docs, transcripts) using Foundry's hosted vector store + file search tool. This is the canonical RAG pattern in Agent Framework 1.8.0.

## When to use

- ✅ Your data is private (internal docs, customer-specific knowledge).
- ✅ You want Foundry to manage the embeddings, indexing, and retrieval.
- ✅ Citations from your own corpus (file name + snippet).
- ❌ Public web data → use [`hosted-bing-search.md`](hosted-bing-search.md).
- ❌ You need a fully custom retrieval pipeline (re-rankers, hybrid search) → use Azure AI Search directly + a function tool.

## Prerequisite — Vector store in Foundry

1. Foundry portal → your project → **Vector stores** → **Create**.
2. Upload your PDFs / docs / transcripts.
3. Wait for indexing to complete (status = Ready).
4. Copy the **vector store ID** (`vs_xxxxxxxx`).
5. Add to `.env`:
   ```
   FOUNDRY_VECTOR_STORE_ID=vs_xxxxxxxx
   ```

## Code

```python
import asyncio
import os
from pathlib import Path

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


for k, v in dotenv_values(Path(__file__).resolve().parents[1] / ".env").items():
    if v is not None and not (os.getenv(k) or "").strip():
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")
    vector_store_id = _require_env("FOUNDRY_VECTOR_STORE_ID")

    async with AzureCliCredential() as cred:
        client = FoundryChatClient(
            project_endpoint=project_endpoint, model=model, credential=cred
        )

        file_search = client.get_file_search_tool(
            vector_store_ids=[vector_store_id],
            max_num_results=5,
        )

        async with client.as_agent(
            name="kb_assistant",
            instructions=(
                "You answer questions about the corporate handbook. "
                "Use the file_search tool to find relevant passages. "
                "Cite the source filename for each fact you state."
            ),
            tools=[file_search],
        ) as agent:
            result = await agent.run("How many vacation days do new hires get?")
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
```

## Why each piece

| Piece | Why |
|-------|-----|
| `client.get_file_search_tool(...)` | The 1.8.0 factory method. Returns a hosted tool definition Foundry can invoke. |
| `vector_store_ids=[vs_id]` | A list (you can pass multiple stores for cross-corpus search). |
| `max_num_results=5` | Cap on retrieved chunks per call. Higher = more context + more tokens. 5 is a good default. |
| Instruction: "Cite the source filename" | The hosted tool returns filename + snippet, but the model may omit citations. Explicit instruction increases citation rate. |
| **No** `HostedFileSearchTool(...)` import | The standalone class was removed in 1.0 GA. Always use the `client.get_*_tool(...)` factory. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `HostedFileSearchTool(vector_store_id=...)` | Removed in 1.0 GA. Use `client.get_file_search_tool(vector_store_ids=[...])`. |
| `vector_store_ids=vs_id` (string, not list) | Always a list of one or more IDs. |
| Pointing at a vector store that's still indexing | Tool calls will return empty results. Wait for status = Ready. |
| Pointing at a vector store in a **different project** | Foundry's RBAC blocks cross-project access. Vector stores must live in the same project as the agent. |
| Omitting the citation instruction | Model says "vacation = 15 days" with no source → not auditable. Always instruct to cite. |
| Setting `max_num_results` too high (e.g., 50) | Token explosion + slow retrieval. Start with 5 and tune up only if recall is poor. |

## Variations

### Combine RAG + Bing (private knowledge + web fallback)

```python
file_search = client.get_file_search_tool(vector_store_ids=[vs_id], max_num_results=5)
bing_tool = build_bing_tool()   # see hosted-bing-search.md

async with client.as_agent(
    name="hybrid_assistant",
    instructions=(
        "Use file_search first. If the answer isn't in our docs, fall back to bing."
    ),
    tools=[file_search, bing_tool],
) as agent:
    ...
```

The model decides which tool to call. With clear instructions it'll prefer the private corpus.

### Multiple corpora

```python
file_search = client.get_file_search_tool(
    vector_store_ids=[vs_handbook, vs_engineering_wiki],
    max_num_results=8,
)
```

## Verification

```bash
# 1. Make sure your vector store status is Ready in the Foundry portal.
# 2. Set .env with FOUNDRY_VECTOR_STORE_ID + project + model.
# 3. Run:
python path/to/this/script.py
```

Expected: an answer that quotes from your indexed docs, with a citation like `(source: employee_handbook.pdf)`.

## See also

- [`tools-hosted.md`](../api-reference/1.8.0/tools-hosted.md) — full hosted tool reference
- [`hosted-bing-search.md`](hosted-bing-search.md) — web variant
- [Microsoft Learn: Foundry File Search](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/tools/file-search)
