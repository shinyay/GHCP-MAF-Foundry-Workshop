# MCP — Model Context Protocol (Python)

> 主軸 skill: [../SKILL.md](../SKILL.md)
> 公式 sample: [foundry-samples/.../responses/03-mcp/main.py](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/03-mcp/main.py)

MCP は LLM エージェントが外部システムと標準プロトコルで会話するための仕組みです。Agent Framework は **2 つの統合パターン**を提供します。

| パターン | 動作場所 | クラス | 用途 |
|---|---|---|---|
| Local MCP | あなたのプロセス内から MCP サーバーへ接続 | `MCPStreamableHTTPTool`, `MCPStdioTool`, `MCPWebsocketTool` | 開発・デバッグ・社内 MCP・トレース伝播が必要なケース |
| Hosted MCP | Foundry サービス内から MCP サーバーへ接続 | `FoundryChatClient.get_mcp_tool(...)` | 本番デプロイ / Hosted Agent / Foundry に近いネットワーク経路 |

---

## ユーザー指示からの推論ルール

ユーザーが要件レベルの短い指示しか書かない場合は、以下のヒューリスティクスで `Local` / `Hosted` を選んでください。

| 指示文の手がかり | 既定の選択 |
|---|---|
| **指示文に MCP の URL** (`https://.../mcp` 等) **がそのまま書いてあって、デプロイ先や `main.py` への明示的な指定がない** | Local MCP (`MCPStreamableHTTPTool(name=<URL から推測>, url=<その URL>)` を `async with` で開く) |
| 「**Hosted MCP として**」「**Foundry 側で MCP を呼ぶ**」と書いてある | Hosted MCP (`FoundryChatClient.get_mcp_tool(...)`) |
| **生成対象が Hosted Agent の `main.py`** (`ResponsesHostServer` でラップしてデプロイする) | Hosted MCP (Hosted Agent では `async with` のプロセス内接続が張れないため) |
| ローカル CLI スクリプト (`async def main()` を実行するだけ) で外部に公開された MCP を呼ぶ | Local MCP |

> **`name` は URL から推測**してかまいません (例: `https://learn.microsoft.com/api/mcp` → `name="Learn"`)。`approval_mode` は **公開・認証なしの MCP なら `"never_require"`**、内部書込み系は `"always_require"` を既定にしてください。

---

## Local MCP

### HTTP (Streamable)

```python
import asyncio
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


async def main() -> None:
    async with MCPStreamableHTTPTool(
        name="Learn",
        url="https://learn.microsoft.com/api/mcp",
        # 認証付き MCP の場合は headers を指定
        # headers={"Authorization": f"Bearer {os.environ['SOME_TOKEN']}"},
    ) as learn_mcp:
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
                model="gpt-4.1-mini",
                credential=AzureCliCredential(),
            ),
            instructions=(
                "あなたは Microsoft Learn 公式ドキュメントを根拠に回答するアシスタントです。"
                "情報源として Microsoft Learn MCP のツールを必ず使い、出典 (URL) を添えてください。"
            ),
            tools=[learn_mcp],
        )

        response = await agent.run("Azure AI Foundry の Hosted Agent の概要を出典 URL 付きで 3 行で")
        print(response.text)


asyncio.run(main())
```

> `MCPStreamableHTTPTool` は **必ず `async with`** で開いてください。クライアントが内部で WebSocket / SSE 接続を保持しているため、明示的なクローズが必要です。

### Stdio (ローカルプロセス)

```python
from agent_framework import MCPStdioTool

async with MCPStdioTool(
    name="LocalFs",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
) as fs_mcp:
    ...
```

### WebSocket

```python
from agent_framework import MCPWebsocketTool

async with MCPWebsocketTool(name="WS", url="wss://example.com/mcp") as ws_mcp:
    ...
```

---

## Hosted MCP

サービス側で MCP リクエストが発行されるため、アプリ側のセットアップは構成だけ。

```python
agent = Agent(
    client=FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=DefaultAzureCredential(),
    ),
    instructions="Microsoft Learn を必ず参照して回答します。",
    tools=[
        FoundryChatClient.get_mcp_tool(
            name="Learn",
            url="https://learn.microsoft.com/api/mcp",
            approval_mode="never_require",  # 認証不要なので非対話で OK
        ),
    ],
    default_options={"store": False},  # Hosted Agent でデプロイする場合
)
```

`get_mcp_tool` の主な引数:

| 引数 | 説明 |
|---|---|
| `name` | ツール識別子 (Foundry のログ・トレースに表示) |
| `url` | MCP サーバーの URL |
| `headers` | 認証ヘッダなど (例: `{"Authorization": f"Bearer {pat}"}`) |
| `approval_mode` | `"never_require"` / `"always_require"` |
| `allowed_tools` | ツール名のホワイトリスト (省略時は全公開ツール) |

### 例: GitHub MCP (PAT 認証)

```python
import os

tools = [
    FoundryChatClient.get_mcp_tool(
        name="GitHub",
        url="https://api.githubcopilot.com/mcp/",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_PAT']}"},
        approval_mode="never_require",
        allowed_tools=["search_issues", "get_repo"],
    ),
]
```

---

## Local vs Hosted の使い分け

| 観点 | Local MCP | Hosted MCP |
|---|---|---|
| ネットワーク | アプリ → MCP | Foundry → MCP |
| **OTEL distributed tracing** | **可** (Agent Framework が `traceparent` を自動伝搬) | 不可 (サービス境界で trace 切れる) |
| Hosted Agent でのデプロイ | 不可 (プロセス内接続が必要) | **必須** |
| 認証情報の置き場 | アプリ環境 | Foundry に渡す必要あり |
| デバッグしやすさ | ◎ (ローカルでブレーク可) | △ (Foundry のログ依存) |

ローカル開発では Local MCP、Hosted Agent デプロイには Hosted MCP を選ぶのが基本です。

---

## 落とし穴

1. **`MCPStreamableHTTPTool` を `with` なしで使う** → 接続リーク。必ず `async with`。
2. **Hosted MCP に GitHub Copilot ライセンスが必要な MCP を渡す** → サーバー側で 401。事前に `curl` で疎通確認。
3. **`approval_mode` を指定しない** → デフォルトで `"always_require"` になり、毎ターン承認待ちで止まる。
4. **MCP サーバーがツールを返さない** → instructions に「○○ MCP を使って」と明記、または `allowed_tools` を確認。
