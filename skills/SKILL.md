---
name: agent-framework-azure-ai-py
description: Microsoft Foundry のエージェントを Microsoft Agent Framework Python SDK (agent-framework-foundry 1.0+) で作るための skill。FoundryChatClient によるアプリ主導エージェント作成、ホスト型ツール (Code Interpreter / File Search / Web Search / Bing Grounding / Image Generation / Azure AI Search / Hosted MCP) や関数ツールの追加、ローカル MCP サーバー連携、AgentSession による会話継続 (アプリ側 / Hosted Agent サービス側両対応)、ストリーミング応答、構造化出力 (Pydantic / JSON Schema)、Foundry Hosted Agent としてのデプロイ (azd ai agent init `--deploy-mode code` / `container`)、OpenTelemetry observability、Cloud Evaluation を扱う。
license: MIT
metadata:
  author: Microsoft
  version: "3.0.0"
  package: agent-framework-foundry
  agent_framework_version: "1.0+"
---

# Agent Framework × Microsoft Foundry (Python)

Microsoft Agent Framework Python SDK と Microsoft Foundry を組み合わせてエージェントを構築するための skill です。

> **このリビジョンの前提**
> - `agent-framework-foundry` **1.0 GA 以降**を前提にしています。プレリリース用の `--pre` は不要です。
> - 環境変数の正規名は **`FOUNDRY_MODEL`** です (旧 `AZURE_AI_MODEL_DEPLOYMENT_NAME` は Hosted Agent コンテナへ自動注入される変数名としては残りますが、アプリ コードからは `FOUNDRY_MODEL` を参照してください)。
> - `azd` 拡張は **`microsoft.foundry`** に統一されました (旧 `azure.ai.agents` は非推奨)。
> - Hosted Agent (preview) のサポート リージョンは **North Central US** のみです (2026年初頭時点)。
> - 1.0 で削除された API: `Message(text=...)` (現在は `Message(contents=[TextContent(text=...)])`)、`agent.run_stream(...)` (現在は `agent.run(..., stream=True)`)、`response.try_parse_value()` (現在は `response.value` を `try/except ValidationError` で受ける)、`AzureAIClient` / `AzureAIAgentClient` / `AzureAIProjectAgentProvider` / `AzureAIAgentsProvider` (Foundry SDK に統合)。

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
              │   - モデルデプロイ (gpt-4.1-mini 等)│
              │   - Hosted ツール / Foundry Toolbox │
              │   - 会話履歴 (conversation)         │
              └──────────────────────────────────┘
```

---

## Installation

```bash
# アプリ側 (ローカル実行 / CI 評価など) - Agent Framework 1.0 GA 以降は --pre 不要
pip install agent-framework-foundry aiohttp azure-identity python-dotenv

# Hosted Agent としてホストする場合 (main.py 側)
pip install agent-framework-foundry agent-framework-foundry-hosting aiohttp python-dotenv

# Observability や Evaluation を使う場合
pip install azure-monitor-opentelemetry "azure-ai-projects>=2.2.0"
```

> `aiohttp` は 1.0 GA で明示的な依存になりました (バージョン解決の安定化のため個別指定推奨)。`azure-ai-projects>=2.2.0` は Cloud Evaluation と source-code deploy 双方で必要です。

## Environment Variables

```bash
# Foundry プロジェクトの "Project endpoint" (Overview ページに表示)
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"

# Foundry プロジェクトにデプロイしたモデルの "Deployment name"
# (Agent Framework 1.0 公式 Quickstart の正規名)
FOUNDRY_MODEL="gpt-4.1-mini"

# (任意) Observability / Foundry App Insights 連携
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;..."
ENABLE_INSTRUMENTATION=true
ENABLE_SENSITIVE_DATA=false   # 本番で true にしない (プロンプト/応答が漏れる)
```

> **`.env` は自動ロードされません**。スクリプト先頭で `from dotenv import load_dotenv; load_dotenv()` を必ず呼んでください。
>
> Hosted Agent としてデプロイした後は、Foundry が `FOUNDRY_MODEL` を含む環境変数を**コンテナへ自動注入**します (ただしランタイムによっては `AZURE_AI_MODEL_DEPLOYMENT_NAME` も併せて注入されます。コード側は `FOUNDRY_MODEL` を読めば十分です)。

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
            model="gpt-4.1-mini",
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

> **ショートカット: `.as_agent()`**
> `FoundryChatClient` (と 1.0 以降の他の ChatClient) には `.as_agent(instructions=..., tools=..., name=...)` ショートカットがあり、`Agent(client=...)` の代わりに使えます。何を使っても同じ `Agent` オブジェクトが返ります。
>
> ```python
> agent = FoundryChatClient(
>     project_endpoint="...",
>     model="gpt-4.1-mini",
>     credential=AzureCliCredential(),
> ).as_agent(
>     name="HelloAgent",
>     instructions="あなたは...",
> )
> ```

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
        model="gpt-4.1-mini",
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
                model="gpt-4.1-mini",
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
        model=os.environ["FOUNDRY_MODEL"],
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

デプロイには 2 パターンあります。**どちらも `azd ai agent` 拡張 (`azd ext install microsoft.foundry`)、v1.25.3+ の azd、Foundry Project Manager ロール、そして North Central US リージョン (Hosted Agent preview 制約) が必要**です。

### パターン A (推奨): ソースコード方式 `--deploy-mode code`

コンテナは Foundry がサーバーサイドでビルドします。フラットな zip (`main.py` + `requirements.txt`) をアップロードするだけで OK。Docker / ACR / Bicep は不要です。

```bash
# 1. スキャフォールド (対話式、もしくはフラグで一括指定)
azd ai agent init --deploy-mode code --runtime python_3_13 --entry-point main.py
# 2. Provision + deploy を一括実行
azd up
# 3. ローカル動作確認 (任意、Inspector UI を無効化)
azd ai agent run --no-inspector
azd ai agent invoke --local "Hello"
# 4. クラウド側を呼ぶ
azd ai agent invoke "Hello"
azd ai agent monitor --follow   # ログをストリーミング
```

生成されるファイル (コード方式):

- `main.py` — エントリポイント
- `requirements.txt` — `agent-framework-foundry`, `agent-framework-foundry-hosting`, `aiohttp`, `python-dotenv`, ...
- `agent.manifest.json` — Hosted Agent 定義 (モデル, リソース, env mapping など)
- `azure.yaml` — azd プロジェクト定義
- `infra/` — 最小限の Bicep

### パターン B (Stretch): コンテナ方式 `--deploy-mode container`

```bash
azd ai agent init --deploy-mode container
azd provision      # ACR + App Insights + Managed Identity を作成
azd deploy         # コンテナをビルド → ACR push → Foundry へデプロイ
```

Dockerfile + Bicep 一式が生成され、コンテナイメージのカスタマイズやプライベート ACR 使用が可能。柔軟だが設定項目が多いため、通常はパターン A を推奨します。

> **「存在しないサブコマンド」に注意**: `azd ai agent provision` / `azd ai agent up` / `azd ai agent deploy` は**存在しません**。Provision/deploy は azd 本体の `azd up` / `azd provision` / `azd deploy` を使います。`azd ai agent` 拡張のサブコマンドは `init`, `run`, `invoke`, `show`, `monitor` などだけです。

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
