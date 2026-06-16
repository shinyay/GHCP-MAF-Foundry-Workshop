# Lab 3: Hosted Agent を Foundry へデプロイ

## この Lab で行うこと

- Lab 2 で作った MAF エージェントを **Foundry Hosted Agent** としてデプロイ
- `azd ai agent init --deploy-mode code` でソースコードデプロイ用プロジェクトをスキャフォールドし (コンテナ不要)
- `azd up` で provision + deploy を 1 コマンドで実行
- デプロイ後の動作確認 (`azd ai agent run` / `azd ai agent invoke` / Foundry ポータルの Playground)
- ログとトレースを確認

> この Lab は **[Lab 0](00-setup.md) で Foundry プロジェクトと gpt-4.1-mini モデルが作成済み、かつ自分に Foundry Project Manager ロールが付与済み** であることを前提にしています。未完了なら Lab 0 に戻ってください。

## アーキテクチャ

```
あなたのコード                                 Foundry
─────────────                                 ──────────
main.py                                       ┌─────────────┐
  ResponsesHostServer(agent).run()  ── zip ──▶ Hosted     │
                                              │  Agent      │
agent.manifest.yaml                           │  (managed)  │
azure.yaml                                    └─────────────┘
requirements.txt                                    │
                                                    ▼
                                            ┌────────────────┐
                                            │ Responses API  │
                                            │ + Playground   │
                                            │ + Tracing      │
                                            └────────────────┘
```

`azd ai agent init --deploy-mode code` が `main.py` / `agent.manifest.yaml` / `azure.yaml` / `requirements.txt` をテンプレートから生成します。あなたは **`main.py` の中身を Lab 2 のロジックに差し替える** だけで、ソースコードがそのまま Foundry にデプロイされます (Docker は不要)。

---

## 3-1. 事前確認

### Lab 0 の前提が揃っているか

```bash
azd version                       # 1.25.3 以上 (source-code deploy に必要)
azd ext list                      # azure.ai.agents が表示されること
az account show
```

### `.env` の中身確認

**PowerShell**

```pwsh
Get-Content .env | Select-String "FOUNDRY_PROJECT_ENDPOINT|FOUNDRY_MODEL"
```

**Bash**

```bash
grep -E "FOUNDRY_PROJECT_ENDPOINT|FOUNDRY_MODEL" .env
```

---

## 3-2. `azd ai agent init` でスキャフォールド (ソースコードデプロイ)

リポジトリルートに **`agent/`** サブディレクトリを作って、その中でテンプレートを展開します (Lab 2 の `src/` と分離するため)。

```bash
mkdir agent
cd agent
azd ai agent init --deploy-mode code --runtime python_3_13 --entry-point main.py
```

> **`--deploy-mode code` が重要です** 。これにより Docker 不要のソースコードデプロイ (`main.py` + `requirements.txt` をそのまま zip して Foundry サービス側でホスト) モードになります。コンテナイメージビルドと ACR は不要になり、デプロイ時間も大幅に短縮されます (概ね 1〜2 分)。もし--deploy-modeが不正というエラーになった場合、azure.ai.agentsのバージョンが古い可能性がありますので、`azd extension upgrade azure.ai.agents`を実行してアップデートを実施してください。

インタラクティブな質問に答えます (回答例は公式 Quickstart 準拠)：

| # | 質問 | 回答 |
|---|---|---|
| 1 | Language | **Python** |
| 2 | Starter template | **Basic agent (Responses, Agent Framework, Python)** |
| 3 | Agent name | **`ms-updates-agent`** |
| 4 | Deployment type | **Code deploy** (上記 `--deploy-mode code` で指定済み) |
| 5 | Runtime | **Python 3.13** (上記 `--runtime python_3_13` で指定済み) |
| 6 | Entry point | **`main.py`** (上記 `--entry-point main.py` で指定済み) |
| 7 | Foundry Project | **Use existing Foundry project** (Lab 0 で作った project を選ぶ) |
| 8 | Azure Tenant | あなたのテナント |
| 9 | Azure subscription | あなたのサブスクリプション |
| 10 | Location | Lab 0 で作成した Foundry プロジェクトと**同じリージョン**を選ぶ |
| 11 | Model deployment | **`gpt-4.1-mini`** (Lab 0 でデプロイした同名の deployment) |
| 12 | Model version | Lab 0 でデプロイしたバージョン |
| 13 | Model SKU | **GlobalStandard** |
| 14 | Deployment capacity | デフォルトの **10** で OK |
| 15 | Deployment name | Lab 0 で作った deployment 名 (`gpt-4.1-mini`) |

完了時に 「**AI agent definition added to your azd project successfully!**」が表示されます。

### 生成されたファイル

```
agent/<your agent name>/
├─ azure.yaml                  ← azd プロジェクト定義 (services.host: foundryagent)
├─ infra/                      ← 必要な Bicep (Log Analytics / App Insights のみ。ACR 不要)
└─ src/<your agent name>/
    ├─ agent.yaml              ← Hosted Agent 定義 (モデル、runtime: python_3_13、entry-point等)
    ├─ main.py                 ← エントリポイント (テンプレート)
    ├─ requirements.txt        ← agent-framework-foundry, agent-framework-foundry-hosting, ...
    └─ infra/                  ← 必要な Bicep (Log Analytics / App Insights のみ。ACR 不要)
```

> **Dockerfile は生成されません** 。ソースコードデプロイモードでは Foundry 側が指定された runtime (python_3_13) で `requirements.txt` をインストールし、`main.py` を起動します。もしコンテナ方式を試したい場合は **付録 A** を参照してください。

---

## 3-3. `main.py` を Lab 2 のロジックに差し替える

`agent/<your agent name>/src/<your agent name>/main.py` を開いて、テンプレートを置き換えます。Copilot Chat で：

````
agentフォルダ内の main.py を以下のように書き換えてください。

要件：
- Lab 2 の src/agent.py と同じ「MSUpdatesAgent」を、
  Microsoft Foundry にデプロイ可能な Hosted Agent として作る
- instructions は Lab 2 と同じ内容（MRC MCP を必ず使い、出典 URL を添える）
- MRC MCP (https://www.microsoft.com/releasecommunications/mcp) と連携
  → Hosted Agent からは Hosted MCP として登録
````

Copilot は [Microsoft Agent Framework の Foundry Hosted Agent サンプル (`ResponsesHostServer` + Hosted MCP)](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting/foundry-hosted-agents) と [kb-1.8.0/api-reference/1.8.0/tools-mcp.md の「ユーザー指示からの推論ルール」](../kb-1.8.0/api-reference/1.8.0/tools-mcp.md#ユーザー指示からの推論ルール) を参照し、以下を自動で補完してくれます：

- `ResponsesHostServer` でラップして `server.run()` で起動
- 認証は `DefaultAzureCredential`（コンテナ向け）
- `default_options={"store": False}`（Hosted Agent での会話履歴の二重保存防止）
- 生成対象が Hosted Agent の `main.py` なので、ローカル MCP (`MCPStreamableHTTPTool`) ではなく Hosted MCP (`client.get_mcp_tool(...)`) を選ぶ（Hosted Agent では `async with` のプロセス内接続が張れないため）

おおむね以下のような構造になります：

```python
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

AGENT_NAME = "MSUpdatesAgent"
MRC_MCP_URL = "https://www.microsoft.com/releasecommunications/mcp"

INSTRUCTIONS = """あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語エージェントです。

必ず Microsoft Release Communications MCP のツールを使って一次情報を取得してから回答してください。
MRC MCP のツールを使わずに、一般知識や推測だけで回答してはいけません。

回答ルール:
- 回答は必ず日本語にしてください。
- Microsoft 365 または Azure のリリース情報に絞って、要点を簡潔にまとめてください。
- 日付、対象製品、影響範囲、利用者が取るべき対応が分かる場合は含めてください。
- 回答の末尾に「出典:」として、MRC MCP から得た出典 URL を必ず添えてください。
- MRC MCP で該当情報が見つからない場合も、その旨を日本語で説明し、参照した URL を示してください。
"""


def require_env(name: str) -> str:
    """Return a required environment variable or fail with an actionable message."""
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} が未設定または空です。Foundry の環境変数設定を確認してください。")
    return value


def resolve_model() -> str:
    """Resolve the local or hosted model deployment name."""
    model = (os.getenv("FOUNDRY_MODEL") or "").strip()
    if model:
        return model
    return require_env("AZURE_AI_MODEL_DEPLOYMENT_NAME")


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=require_env("FOUNDRY_PROJECT_ENDPOINT"),
        model=resolve_model(),
        credential=DefaultAzureCredential(),
    )

    mrc_mcp_tool = client.get_mcp_tool(
        name="mrc_release_communications",
        url=MRC_MCP_URL,
        approval_mode="never_require",
    )

    agent = Agent(
        client=client,
        name=AGENT_NAME,
        instructions=INSTRUCTIONS,
        tools=[mrc_mcp_tool],
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
```

> [!IMPORTANT]
> モデル名は `os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]` と **フォールバック付きで読む**。ローカル実行では `.env` の `FOUNDRY_MODEL` が、`azd up` でデプロイした Hosted Agent コンテナでは Foundry が注入する `AZURE_AI_MODEL_DEPLOYMENT_NAME` が使われます。`os.environ["FOUNDRY_MODEL"]` だけだと **コンテナ起動時に `KeyError` で落ちます**（コンテナに `FOUNDRY_MODEL` は注入されない）。

### `requirements.txt` の確認

`azd ai agent init` が生成した `requirements.txt` には少なくとも以下が含まれているはず：

```
agent-framework-foundry
agent-framework-foundry-hosting
aiohttp
azure-identity
python-dotenv
mcp
```

`aiohttp` は `FoundryChatClient` の HTTP クライアントが使うため、明示的に含めておくとデプロイ時の依存解決エラーを避けられます。無いものがあれば追記してください。

---

## 3-4. `azd up` で provision + deploy を一括実行

`agent/<your agent name>/` ディレクトリ配下で：

```bash
azd up
```

`azd up` は **provision (Azure リソース作成) + deploy (コード zip + Foundry へ push)** を 1 コマンドで実行します。ソースコードデプロイモードなので ACR やコンテナビルドは不要。作成されるリソースは以下だけ：

| リソース | 用途 |
|---|---|
| Resource group | 他のリソースのコンテナ |
| Log Analytics workspace | ログ |
| Application Insights | トレース・メトリクス (Lab 4 で使用) |
| Managed identity | Hosted Agent の Azure 認証 |

> Lab 0 で作った既存 Foundry project / model deployment は再利用されるため、ここでは新規作成されません。

デプロイ完了時に Playground URL と Agent endpoint が表示されます：

```
Deploying services (azd deploy)
  Done: Deploying service ms-updates-agent
  - Agent playground (portal): https://ai.azure.com/.../build/agents/ms-updates-agent/build?version=1
  - Agent endpoint: https://<account>.services.ai.azure.com/api/projects/<project>/agents/ms-updates-agent/versions/1
```

完了まで 3〜5 分 (コンテナ方式より 2〜3 分高速)。

---

## 3-5. デプロイされたエージェントを呼ぶ

### CLI から

```bash
azd ai agent invoke "最近 GA になった Azure 機能を 3 件教えて"
```

### ステータス確認

```bash
azd ai agent show
```

`status: Active` ならデプロイ成功です。

### ログをライブで見る

```bash
azd ai agent monitor --follow
```

別のターミナルで `azd ai agent invoke "..."` を叩くと、リクエストがリアルタイムでログに流れます。`Ctrl+C` で停止。

### Foundry ポータルの Playground で動作確認

1. `azd up` 完了時に表示された Playground URL をブラウザで開く (または Foundry ポータル > **Build** > **Agents** > `ms-updates-agent` > **Open in playground**)
2. プロンプト例：
   ```
   Microsoft 365 Copilot のロードマップで Outlook 関連を新しい順に 5 件まとめて
   ```
   ```
   今後 90 日以内に Retiring になる Azure 機能を教えて
   ```
3. 下部の **Tool calls** タブで MCP ツール (`search_microsoft_release_messages` 等) が呼ばれていることを確認

---

## 3-6. ★Stretch: コード変更を反映してみる

`main.py` の `INSTRUCTIONS` を編集して、もう一度 `azd deploy` を叩くだけで新バージョンがデプロイされます (二回目以降は provision 不要なので `azd up` より `azd deploy` のほうが高速)。

```bash
azd deploy
azd ai agent show     # version が増えている
azd ai agent invoke "テスト質問"
```

新しい version が active になり、過去 version は履歴として残ります。

---

## 付録 A: コンテナ方式でデプロイしたい場合 (★Stretch)

チームポリシーで Docker イメージと ACR が必要な場合は、スキャフォールド時に以下を選びます:

```bash
azd ai agent init --deploy-mode container --runtime python_3_13
```

この場合、追加で以下が質問されます:

| 質問 | 推奨回答 |
|---|---|
| Dependency resolution | **Remote build (dependencies installed on server during deployment)** |
| Container resources | デフォルト **0.5 cores, 1Gi memory** |

コンテナ方式では Azure Container Registry が作成され、`azd deploy` がコンテナイメージをビルド → ACR へ push します (ソースコードデプロイより 5〜10 分長い)。Bring-your-own-Docker やカスタム base image が必要な企業シナリオで主に使います。

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `azd ai agent init` が `--deploy-mode` オプションを認識しない | `azd extension upgrade azure.ai.agents` を実行して拡張を最新化 |
| `SubscriptionNotRegistered` | `az provider register --namespace Microsoft.CognitiveServices` |
| `AuthorizationFailed` during provisioning | **Foundry Project Manager** + **Contributor** が必要。Lab 0 を再確認 |

もし`Microsoft Release Communications MCP Server`のツール呼び出しでエラーとなる場合は、代わりに`Microsoft Learn MCP Server`の利用を検討してください。エンドポイントは`https://learn.microsoft.com/api/mcp`です。

---

次へ → [Lab 4: トレース確認と Cloud Evaluation](04-trace-evaluation.md)
