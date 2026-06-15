# Tools — Foundry Hosted Tools & Function Tools (Python)

> 主軸 skill: [../SKILL.md](../SKILL.md)
> 公式サンプル: [microsoft-foundry/foundry-samples — hosted-agents/agent-framework/responses](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/responses)

`FoundryChatClient` で使えるツールは大きく 3 種類です。

| 種類 | 例 | 動作場所 | 認証 |
|---|---|---|---|
| Hosted ツール | Code Interpreter, File Search, Web Search, Bing Grounding, Image Generation, Azure AI Search, Hosted MCP | Foundry サービス内部 | プロジェクトの managed identity / 接続済みリソース |
| 関数ツール | `@tool` を付けた Python 関数 | あなたのプロセス内 | アプリ側で実装 |
| ローカル MCP | `MCPStreamableHTTPTool`, `MCPStdioTool` | あなたのプロセスから MCP サーバーへ HTTP/stdio | MCP サーバー側 |

---

## ユーザー指示からツールを推論する

ユーザーが要件レベルの短い指示しか書かない場合（例: 「Web で調べて答えるエージェントを作って」「画像も生成できるようにして」）でも、以下の表に従って `tools=[...]` に適切なツールを自動追加してください。

| 指示文の手がかり | 既定で追加するツール |
|---|---|
| 「Web 検索」「Bing で」「最新の情報を調べて」 | `FoundryChatClient.get_web_search_tool()` (Azure OpenAI モデル限定) |
| 「コード実行」「Python で計算」「グラフ描画」「データ分析」 | `FoundryChatClient.get_code_interpreter_tool()` |
| 「ファイルを検索」「アップロードした文書から」「vector store」 | `FoundryChatClient.get_file_search_tool()` |
| 「画像生成」「画像を作って」「絵を描いて」 | `FoundryChatClient.get_image_generation_tool(model="gpt-image-1")` |
| 「Bing で grounding」「Bing リソースを使って」 | `FoundryChatClient.get_bing_grounding_tool(connection_id=...)` |
| 「Azure AI Search の `<index>` を引いて」「自社ナレッジから」 | `FoundryChatClient.get_azure_ai_search_tool(index_connection_id=..., index_name=...)` |
| **MCP の URL が文中にある** (`https://.../mcp` 等) | Local MCP (`MCPStreamableHTTPTool`)。詳細は [mcp.md](mcp.md) |
| 「Hosted MCP として」「Foundry 側で MCP を呼ぶ」 | `FoundryChatClient.get_mcp_tool(name=, url=, approval_mode="never_require")` |
| 関数呼び出し系（自前のビジネスロジック・ローカル API） | `@tool(approval_mode="never_require")` を付けた Python 関数 |

> どれを選ぶか迷ったら、**「副作用がない / 読み取り中心」なら `approval_mode="never_require"`**、**「書き込み / 課金 / 破壊的」なら `"always_require"`** を既定にしてください。

---

## Hosted ツール一覧

### Code Interpreter

サンドボックス内で Python を実行できるホスト型ツール。ファイル入出力、グラフ生成、計算などに使えます。

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

agent = Agent(
    client=FoundryChatClient(credential=AzureCliCredential()),
    instructions="あなたはデータ分析アシスタントです。Python で計算するときは必ずコード実行ツールを使ってください。",
    tools=[FoundryChatClient.get_code_interpreter_tool()],
)

response = await agent.run("1 から 100 までの素数を全部リストアップして個数を教えて")
print(response.text)
```

### File Search

Foundry の vector store に登録した文書を検索できます。

```python
tools = [
    FoundryChatClient.get_file_search_tool(
        # vector_store_ids=["vs_xxx"],  # 既存 vector store を指定
        max_num_results=5,
    ),
]
```

### Web Search

Bing-backed のグラウンディング。**Azure OpenAI モデルでのみ動作**します (他社モデルではエラー)。

```python
tools = [FoundryChatClient.get_web_search_tool()]
```

### Bing Grounding (自前の Bing リソース)

```python
tools = [
    FoundryChatClient.get_bing_grounding_tool(
        connection_id="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<acct>/projects/<project>/connections/<bing-conn>",
    ),
]
```

### Image Generation

```python
tools = [
    FoundryChatClient.get_image_generation_tool(
        model="gpt-image-1",
        size="1024x1024",
    ),
]
```

### Azure AI Search

```python
tools = [
    FoundryChatClient.get_azure_ai_search_tool(
        index_connection_id="<ai-search-connection-id>",
        index_name="my-index",
    ),
]
```

### Hosted MCP

サービス側で MCP リクエストが発行されます。詳細は [mcp.md](mcp.md) を参照。

```python
tools = [
    FoundryChatClient.get_mcp_tool(
        name="Learn",
        url="https://learn.microsoft.com/api/mcp",
        approval_mode="never_require",
    ),
]
```

---

## 関数ツール — `@tool` デコレータ

### 基本

```python
from typing import Annotated
from pydantic import Field
from agent_framework import tool


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="天気を取得したい場所 (例: 東京)")],
    unit: Annotated[str, Field(description="温度単位 ('C' or 'F')")] = "C",
) -> str:
    """指定された場所の現在の天気を返します。"""
    return f"{location}: 晴れ 22{unit}"
```

引数の型・`Field(description=...)`・docstring がそのまま JSON Schema になります。

### approval_mode

| 値 | 動作 | いつ使う |
|---|---|---|
| `"never_require"` | 承認なしで自動実行 | 副作用がない読み取り系、または学習・検証 |
| `"always_require"` | 毎回承認が必要 | DB 書き込み、課金、外部 API への破壊的呼び出し |
| `"requires_approval"` (非推奨/旧名) | 同上 | — |

承認が必要な場合、`agent.run()` のレスポンスに承認待ちステップが返るので、それに対して `approve()` を呼んでから `agent.run()` を再開します (詳細は公式 sample `01-basic/03_human_in_the_loop.py` 参照)。

### 非同期関数

```python
@tool(approval_mode="never_require")
async def fetch_user(user_id: Annotated[str, Field(description="ユーザー ID")]) -> dict:
    """ユーザー情報を取得します。"""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.example.com/users/{user_id}")
        return r.json()
```

### ツールの追加方法

```python
# Agent 作成時に渡す
agent = Agent(client=client, tools=[get_weather, fetch_user])

# あるいは run() ごとに渡す (この呼び出しでのみ有効)
response = await agent.run("...", tools=[get_weather])
```

---

## 複数ツール混在の例

```python
import asyncio
from typing import Annotated
from pydantic import Field
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


@tool(approval_mode="never_require")
def get_employee_email(
    name: Annotated[str, Field(description="社員氏名")],
) -> str:
    """社員のメールアドレスを返します (社内ディレクトリのモック)。"""
    return f"{name.lower().replace(' ', '.')}@contoso.com"


async def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
            model="gpt-4.1-mini",
            credential=AzureCliCredential(),
        ),
        instructions=(
            "あなたは社内アシスタントです。"
            "計算には Python を、Web 検索が必要な質問には Web Search を、"
            "社員情報の問い合わせには get_employee_email を使ってください。"
        ),
        tools=[
            get_employee_email,
            FoundryChatClient.get_code_interpreter_tool(),
            FoundryChatClient.get_web_search_tool(),
        ],
    )

    print((await agent.run("田中太郎さんのメールアドレスは？")).text)
    print((await agent.run("123 の階乗を計算して")).text)


asyncio.run(main())
```

---

## 落とし穴

1. **ツールが呼ばれない** → instructions に「○○ のときは必ず ○○ ツールを使ってください」と明示する
2. **Web Search が `400` を返す** → Azure OpenAI 以外のモデル (例: Mistral, Llama) では使えない
3. **関数ツールが承認待ちで止まる** → 検証時は `approval_mode="never_require"` を指定
4. **ツール出力が長すぎてコンテキスト溢れ** → 関数側で要約して返す
