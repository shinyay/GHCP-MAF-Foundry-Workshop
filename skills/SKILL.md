---
name: agent-framework-azure-ai-py
description: Microsoft Foundry のエージェントを Microsoft Agent Framework Python SDK (agent-framework-foundry) で作るための skill。FoundryChatClient によるアプリ主導エージェント作成、ホスト型ツール (Code Interpreter / File Search / Web Search) や関数ツールの追加、MCP サーバー連携、AgentSession による会話継続、ストリーミング応答、構造化出力 (Pydantic / JSON Schema)、Foundry Hosted Agent としてのデプロイを扱う。
license: MIT
metadata:
  author: Microsoft
  version: "2.0.0"
  package: agent-framework-foundry
---

# Agent Framework × Microsoft Foundry (Python)

Microsoft Agent Framework Python SDK と Microsoft Foundry を組み合わせてエージェントを構築するための skill です。

---

## 2 つの利用パターン

| シナリオ | Python での表現 | 使うのはこんなとき |
|---|---|---|
| Foundry の Responses エンドポイントを使った推論 (アプリが instructions/tools を所有) | `Agent(client=FoundryChatClient(...))` | ローカル開発、CI 評価、自分のコードがエージェント本体になるケース |
| Foundry にデプロイ済みエージェントへの接続 (Prompt Agent / Hosted Agent) | `FoundryAgent(...)` | Foundry ポータルや Hosted Agent としてデプロイしたエージェントを Python から呼び出すケース |

> Hosted Agent は **エージェント本体が Foundry 上のコンテナで動作**し、`FoundryChatClient` を内部で使った `main.py` を `agent-framework-foundry-hosting` の `ResponsesHostServer` でラップしてホストします。

---

## Architecture

```
┌──────────────────────── あなたのコード ────────────────────────┐
│                                                               │
│  Agent(client=FoundryChatClient(project_endpoint, model, ...))│
│           │                                                   │
│           ├─ tools=[ 関数, FoundryChatClient.get_*_tool(),    │
│           │          MCPStreamableHTTPTool, ... ]              │
│           │                                                   │
│           ▼                                                   │
│   agent.run(...) / agent.run(..., stream=True) / session=...  │
│                                                               │
└──────────────────────────────┬────────────────────────────────┘
                               │ Responses API
                               ▼
              ┌──────────────────────────────────┐
              │  Microsoft Foundry プロジェクト     │
              │   - モデルデプロイ (gpt-5.4-mini 等)│
              │   - Hosted ツール / Foundry Toolbox │
              │   - 会話履歴 (conversation)         │
              └──────────────────────────────────┘
```

---

## Installation

```bash
# アプリ側 (ローカル実行 / CI 評価など)
pip install agent-framework-foundry azure-identity python-dotenv

# Hosted Agent としてホストする場合 (main.py 側)
pip install agent-framework-foundry agent-framework-foundry-hosting python-dotenv

# Observability や Evaluation を使う場合
pip install azure-monitor-opentelemetry "azure-ai-projects>=2.1.0"
```

> `agent-framework-foundry` は preview パッケージのため `--pre` を付けてインストールします。必要なパッケージを個別に指定すると依存解決が安定します。

## Environment Variables

```bash
# Foundry プロジェクトの "Project endpoint" (Overview ページに表示)
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"

# Foundry プロジェクトにデプロイしたモデルの "Deployment name"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"

# (任意) Observability / Foundry App Insights 連携
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;..."
ENABLE_INSTRUMENTATION=true
ENABLE_SENSITIVE_DATA=false   # 本番で true にしない (プロンプト/応答が漏れる)
```

> Hosted Agent としてデプロイした後は、これらの環境変数は Foundry が **コンテナへ自動注入**します。ローカル開発時のみ `.env` などで設定してください。

## 認証 — DefaultAzureCredential を基本に

> ローカルでも本番でも同じコードが動くように、原則 `DefaultAzureCredential` を使います。
> - **ローカル開発**: `azd auth login` または `az login` を済ませた状態で `DefaultAzureCredential()` がそのまま動作。
> - **CI/CD・本番**: 環境変数 `AZURE_TOKEN_CREDENTIALS=prod` を設定すると Managed Identity / Workload Identity 系のみが使われます。鍵や接続文字列は使わない方針です。

```python
from azure.identity import DefaultAzureCredential, AzureCliCredential
# あるいは非同期コンテキストでクリーンアップしたい場合は:
# from azure.identity.aio import DefaultAzureCredential, AzureCliCredential
```

公式サンプルは多くの場合 `AzureCliCredential()` で開発しています。ローカル開発時はそれに従ってかまいません。

---

## 基本ワークフロー

### 1) 最小エージェント

```python
import asyncio
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


async def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
            model="gpt-5.4-mini",
            credential=AzureCliCredential(),
        ),
        name="HelloAgent",
        instructions="あなたは親切な日本語アシスタントです。簡潔に答えてください。",
    )

    response = await agent.run("自己紹介して")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
```

### 2) 関数ツールを持たせる

`@tool` デコレータを付けると、引数の型ヒント / `Field(description=...)` / docstring が自動で JSON Schema に変換されます。
`approval_mode="never_require"` を指定すると承認なしで自動実行されます (検証や Lab 用)。

```python
from random import randint
from typing import Annotated
from pydantic import Field
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="天気を取得したい場所 (例: 東京)")],
) -> str:
    """指定された場所の天気を返します。"""
    conditions = ["晴れ", "曇り", "雨", "雪"]
    return f"{location} の天気は {conditions[randint(0, 3)]}、最高気温 {randint(5, 30)}℃ です。"


agent = Agent(
    client=FoundryChatClient(
        project_endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
        model="gpt-5.4-mini",
        credential=AzureCliCredential(),
    ),
    instructions="日本語で簡潔に答えてください。",
    tools=[get_weather],
)
```

### 3) Foundry のホスト型ツール

`FoundryChatClient` のクラスメソッドからホスト型ツールを生成します。インスタンス化不要です。

```python
agent = Agent(
    client=FoundryChatClient(credential=AzureCliCredential()),
    instructions="Web 検索とコード実行が使えます。",
    tools=[
        FoundryChatClient.get_web_search_tool(),        # Bing-backed (Azure OpenAI モデル限定)
        FoundryChatClient.get_code_interpreter_tool(),  # サンドボックスでコード実行
    ],
)
```

主要なホスト型ツール:

| ツール | ファクトリ | 補足 |
|---|---|---|
| Code Interpreter | `get_code_interpreter_tool()` | サンドボックスで Python 実行 |
| File Search | `get_file_search_tool()` | Foundry vector store を検索 |
| Web Search | `get_web_search_tool()` | Bing-backed grounding (Azure OpenAI 限定) |
| Image Generation | `get_image_generation_tool(model="gpt-image-1", ...)` | 画像生成 |
| Hosted MCP | `get_mcp_tool(name=, url=, headers=, approval_mode=)` | Foundry が MCP を呼び出す |
| Bing Grounding | `get_bing_grounding_tool(connection_id=)` | 自前の Bing リソース |
| Azure AI Search | `get_azure_ai_search_tool(index_connection_id=, index_name=)` | RAG |

### 4) ストリーミング応答

`agent.run(...)` に `stream=True` を渡すと **`ResponseStream`** が返り、`async for` で逐次チャンクを受け取れます。Agent Framework Python 1.0.0 で API がここに統一されました (旧 `agent.run_stream(...)` は削除)。

```python
print("Agent: ", end="", flush=True)
stream = agent.run("短い物語を書いて", stream=True)
async for chunk in stream:
    if chunk.text:
        print(chunk.text, end="", flush=True)
print()
```

### 5) 会話を続ける — `AgentSession`

```python
session = agent.create_session()

r1 = await agent.run("私の名前は花子です。", session=session)
print(r1.text)

r2 = await agent.run("私の名前を覚えていますか？", session=session)
print(r2.text)  # → 「花子」を覚えている
```

### 6) 構造化出力 (Pydantic)

`options={"response_format": MyModel}` を `agent.run()` に渡します。返り値の `response.value` で Pydantic インスタンスを取り出します。
スキーマに合わなかった場合は `pydantic.ValidationError` が投げられるので、`try/except` で受けます (1.0.0 で `response.try_parse_value` は削除されました)。

```python
from pydantic import BaseModel, ValidationError


class WeatherReport(BaseModel):
    location: str
    temperature_c: float
    conditions: str


response = await agent.run(
    "東京の今の天気を JSON で。",
    options={"response_format": WeatherReport},
    tools=[get_weather],
)

try:
    report = response.value
    print(f"{report.location}: {report.temperature_c}°C ({report.conditions})")
except ValidationError as err:
    print("構造化応答ではありませんでした:", response.text)
    print(err)
```

`response_format` には Pydantic モデルの代わりに **JSON Schema (dict)** も渡せます。その場合 `response.value` は `dict` / `list` になります。

---

## MCP サーバーを使う

### Local MCP (アプリ側から MCP サーバーへ HTTP/Stdio 接続)

```python
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


async def main() -> None:
    async with MCPStreamableHTTPTool(
        name="Learn",
        url="https://learn.microsoft.com/api/mcp",  # 認証不要
    ) as learn_mcp:
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
                model="gpt-5.4-mini",
                credential=AzureCliCredential(),
            ),
            instructions=(
                "あなたは Microsoft Learn 公式ドキュメントを根拠に回答するアシスタントです。"
                "質問が出たら必ず Microsoft Learn MCP のツールで情報を取得し、出典 URL を添えてください。"
            ),
            tools=[learn_mcp],
        )

        result = await agent.run("Azure AI Foundry の Hosted Agent の概要を 3 行で教えて")
        print(result.text)
```

### Hosted MCP (Foundry サービスが MCP を呼び出す)

Hosted MCP は Foundry のサービス内部で MCP リクエストが発行されるため、アプリ側から `with` で接続を張る必要はありません。代わりに `FoundryChatClient.get_mcp_tool()` で構成オブジェクトを作って `tools=` に渡します。

```python
agent = Agent(
    client=FoundryChatClient(credential=AzureCliCredential()),
    instructions="Microsoft Learn を必ず参照して回答します。",
    tools=[
        FoundryChatClient.get_mcp_tool(
            name="Learn",
            url="https://learn.microsoft.com/api/mcp",
            approval_mode="never_require",
        ),
    ],
)
```

> **トレース伝播の差**: 自分のプロセス内で開く `MCPStreamableHTTPTool` には Agent Framework が自動で `traceparent` を伝搬します。Hosted MCP (`get_mcp_tool`) はサービス側で呼ばれるため伝搬しません。end-to-end の distributed tracing が必要な場合は local MCP を選びます。

---

## Observability — OpenTelemetry

```python
from agent_framework.observability import enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
import os

# Foundry App Insights へ送信 (事前に pip install azure-monitor-opentelemetry)
configure_azure_monitor(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
)
# Agent Framework の計装（これを呼ばないと agent.run のスパンが出ない）
enable_instrumentation()

tracer = get_tracer()
with tracer.start_as_current_span("my_business_logic"):
    response = await agent.run("...")
```

> Hosted Agent (`azd ai agent init` で生成し `azd deploy` したもの) では、Foundry が App Insights 接続文字列と計装を自動付与するので、上記コードは不要です。ローカル実行時だけ追加してください。
>
> 環境変数だけでやりたい場合は `configure_otel_providers()` (下記表参照) も使えますが、Foundry App Insights と併用すると exporter が二重登録になるため **どちらか一方に統一**してください。

主要な環境変数:

| 環境変数 | 用途 |
|---|---|
| `ENABLE_INSTRUMENTATION=true` | Agent Framework の OTEL インストルメンテーションを有効化 |
| `ENABLE_SENSITIVE_DATA=true` | プロンプト / 応答 / 関数引数を span にも記録 (**本番では false**) |
| `ENABLE_CONSOLE_EXPORTERS=true` | コンソールへ trace 出力 (デバッグ用) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector / Aspire Dashboard のエンドポイント |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Foundry App Insights 連携 |

Hosted Agent としてデプロイした場合は `APPLICATIONINSIGHTS_CONNECTION_STRING` がコンテナへ自動注入され、protocol library が OTEL トレースを自動送信します。

---

## Foundry Hosted Agent としてホストする

ローカルで動かしている Agent を `main.py` の中で `ResponsesHostServer` でラップすると、Foundry にデプロイ可能な Hosted Agent になります。

```python
# main.py
import os
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions="あなたは親切なアシスタントです。",
        tools=[
            client.get_code_interpreter_tool(),
        ],
        # Hosted Agent では会話履歴は Foundry 側で管理されるため store=False を推奨
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()  # localhost:8088 で /responses エンドポイントを公開


if __name__ == "__main__":
    main()
```

必須ファイル:

- `main.py` — エントリポイント (`ResponsesHostServer(agent).run()` を呼ぶ)
- `agent.manifest.yaml` — `azd ai agent init` が生成する Hosted Agent 定義
- `requirements.txt` — `agent-framework-foundry`, `agent-framework-foundry-hosting`, `python-dotenv`, ...
- `azure.yaml` — `azd ai agent init` が生成する azd プロジェクト定義

デプロイ:

```bash
azd ai agent init      # 対話: Basic agent (Responses, Agent Framework, Python) を選ぶ
azd provision          # Foundry プロジェクト + ACR + App Insights + Model を作成
azd ai agent run       # ローカルで http://localhost:8088 起動
azd ai agent invoke --local "Hello"
azd deploy             # コンテナをビルド → ACR push → Foundry へデプロイ
azd ai agent invoke "Hello"
azd ai agent monitor --follow   # ログをストリーミング
```

> `azd ai agent provision` / `azd ai agent up` / `azd ai agent deploy` は **存在しません**。プロビジョン/デプロイは `azd provision` / `azd deploy` を使います (azd ai agent ext 配下のサブコマンドは `init`, `run`, `invoke`, `show`, `monitor` のみ)。

---

## デプロイ済み Hosted Agent への接続 — `FoundryAgent`

Foundry にデプロイ済みのエージェントを Python から呼びたい場合は `FoundryAgent` を使います。

```python
from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential


agent = FoundryAgent(
    agent_name="agent-framework-agent-basic-responses",
    credential=AzureCliCredential(),
    allow_preview=True,  # Hosted Agent (preview) を使う場合
)

response = await agent.run("Hello!")
print(response.text)
```

> `FoundryAgent` ではエージェントの instructions / tools は **Foundry 側に定義**されているものが使われます。Python コードから上書きはできません (これは設計上の制約)。

---

## クイックリファレンス

### import

```python
from agent_framework import Agent, tool, MCPStreamableHTTPTool, AgentSession
from agent_framework.foundry import FoundryChatClient, FoundryAgent, FoundryEmbeddingClient
from agent_framework.observability import enable_instrumentation, get_tracer
from agent_framework_foundry_hosting import ResponsesHostServer, InvocationsHostServer
from azure.identity import AzureCliCredential, DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor   # Foundry App Insights連携
# Async credential (推奨される async コンテキストマネージャ用法):
# from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
```

### 主要メソッド

| メソッド | 用途 |
|---|---|
| `Agent(client=..., instructions=, tools=, default_options=)` | エージェント定義 |
| `agent.run(prompt, session=, options=, tools=)` | 1 回呼ぶ (非同期) |
| `agent.run(prompt, stream=True, session=, options=)` | ストリーミング (`ResponseStream`、`async for`) |
| `agent.create_session()` | 会話継続用の `AgentSession` を作成 |
| `FoundryChatClient.get_web_search_tool(...)` | Web 検索ツール (Bing) |
| `FoundryChatClient.get_code_interpreter_tool()` | コード実行ツール |
| `FoundryChatClient.get_mcp_tool(name=, url=, headers=, approval_mode=)` | Hosted MCP |
| `configure_azure_monitor(connection_string=...)` | App Insights 送信設定 (azure.monitor.opentelemetry) |
| `enable_instrumentation()` | Agent Framework の OTEL 計装を有効化 |

### 命名規約

- `async def` を基本に、ローカル MCP / async credential には `async with` を使う
- 関数ツールには `@tool(approval_mode="never_require")` (検証用) を付ける。本番では `approval_mode="always_require"` か middleware で制御
- 関数の引数は `Annotated[type, Field(description="...")]` で説明を付ける (Foundry が JSON Schema 化する)
- `default_options={"store": False}` は Hosted Agent では必須 (重複会話履歴を避けるため)

---

## Reference Files

- [references/tools.md](references/tools.md) — ホスト型ツール / 関数ツールの詳細パターン、**ユーザーの指示文からツールを選ぶ推論ルール**
- [references/mcp.md](references/mcp.md) — MCP 統合 (local / hosted) の詳細、**MCP URL が指示文に含まれているときの推論**
- [references/threads.md](references/threads.md) — `AgentSession` と Foundry conversation の管理、**対話ループ + streaming の実装パターン**
- [references/advanced.md](references/advanced.md) — 構造化出力 (ファイル保存パターン含む) / Cloud Evaluation (data_mapping ルール、ポーリング、結果 URL) / observability / middleware
