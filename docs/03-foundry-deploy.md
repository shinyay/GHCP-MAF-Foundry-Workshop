# Lab 3: Hosted Agent を Foundry へデプロイ

## この Lab で行うこと

- Lab 2 で作った MAF エージェントを **Foundry Hosted Agent** としてデプロイ
- `azd ai agent init` で対話的にプロジェクトをスキャフォールド
- ローカル (`azd ai agent run`) → クラウド (`azd deploy`) で動作確認
- Foundry ポータルの **Playground** から動作確認
- ログとトレースを確認

> この Lab は **[Lab 0](00-setup.md) で Foundry プロジェクトと gpt-5.4-mini モデルが作成済み、かつ自分に Foundry Project Manager ロールが付与済み** であることを前提にしています。未完了なら Lab 0 に戻ってください。

## アーキテクチャ

```
あなたのコード                                 Foundry
─────────────                                 ──────────
main.py                                       ┌─────────────┐
  ResponsesHostServer(agent).run()  ── Docker ─▶ Hosted     │
                                              │  Agent      │
agent.manifest.yaml                           │  (container)│
azure.yaml                                    └─────────────┘
requirements.txt                                    │
                                                    ▼
                                            ┌────────────────┐
                                            │ Responses API  │
                                            │ + Playground   │
                                            │ + Tracing      │
                                            └────────────────┘
```

`azd ai agent init` が `main.py` / `agent.manifest.yaml` / `azure.yaml` / `requirements.txt` をテンプレートから生成します。あなたは **`main.py` の中身を Lab 2 のロジックに差し替える** だけです。

---

## 3-1. 事前確認

### Lab 0 の前提が揃っているか

```bash
azd version                     # 1.25.0 以上
azd ext list                    # azure.ai.agents 0.1.34-preview 以上
az account show
```

### `.env` の中身確認

**PowerShell**

```pwsh
Get-Content .env | Select-String "FOUNDRY_PROJECT_ENDPOINT|AZURE_AI_MODEL_DEPLOYMENT_NAME"
```

**Bash**

```bash
grep -E "FOUNDRY_PROJECT_ENDPOINT|AZURE_AI_MODEL_DEPLOYMENT_NAME" .env
```

### ロール確認（重要）

Hosted Agent のデプロイには **Foundry Project Manager** が必須です。Lab 0 の 0-3 で割り当てたはずですが、念のため：

**PowerShell**

```pwsh
$myObjId = az ad signed-in-user show --query id -o tsv
$projectId = "<\u3042\u306a\u305f\u306e Foundry \u30d7\u30ed\u30b8\u30a7\u30af\u30c8\u306e\u30ea\u30bd\u30fc\u30b9 ID>"
az role assignment list --assignee $myObjId --scope $projectId `
    --query "[?roleDefinitionId.contains(@,'eadc314b-1a2d-4efa-be10-5d325db5065e')]" -o tsv
```

**Bash**

```bash
MY_OBJ_ID=$(az ad signed-in-user show --query id -o tsv)
PROJECT_ID="<あなたの Foundry プロジェクトのリソース ID>"
az role assignment list --assignee "$MY_OBJ_ID" --scope "$PROJECT_ID" \
    --query "[?contains(roleDefinitionId,'eadc314b-1a2d-4efa-be10-5d325db5065e')]" -o tsv
```

空文字なら未割り当て。Lab 0 の 0-3 のロール割り当てコマンドを再実行してください。

---

## 3-2. `azd ai agent init` でスキャフォールド

リポジトリルートに **`agent/`** サブディレクトリを作って、その中でテンプレートを展開します（Lab 2 の `src/` と分離するため）。

```bash
mkdir agent
cd agent
azd ai agent init
```

インタラクティブな質問に答えます（**回答例は公式 quickstart 準拠**）：

| # | 質問 | 回答 |
|---|---|---|
| 1 | Language | **Python** |
| 2 | Starter template | **Basic agent (Responses, Agent Framework, Python)** |
| 3 | Agent name | **`ms-updates-agent`**（任意） |
| 4 | Deployment type | **Container deploy** |
| 5 | Runtime | **Python 3.13** |
| 6 | Entry point | **`main.py`**（デフォルト） |
| 7 | Dependency resolution | **Remote build (dependencies installed on server during deployment)** |
| 8 | Foundry Project | **Use existing Foundry project**（Lab 0 で作った project を選ぶ）|
| 9 | Azure Tenant | あなたのテナント |
| 10 | Azure subscription | あなたのサブスクリプション |
| 11 | Location | **East US 2**（Lab 0 でこのリージョンに統一している） |
| 12 | Model deployment | **`gpt-5.4-mini`**（Lab 0 でデプロイした同名の deployment）|
| 13 | Model version | Lab 0 でデプロイしたバージョン |
| 14 | Model SKU | **GlobalStandard** |
| 15 | Deployment capacity | デフォルトの **10** で OK |
| 16 | Deployment name | Lab 0 で作った deployment 名（`gpt-5.4-mini`） |
| 17 | Container resources | デフォルト **0.5 cores, 1Gi memory** |

完了時に「**AI agent definition added to your azd project successfully!**」が表示されます。

### 生成されたファイル

```
agent/
├─ azure.yaml                  ← azd プロジェクト定義
├─ agent.manifest.yaml         ← Hosted Agent 定義（モデル、リソース、tools 等）
├─ main.py                     ← エントリポイント (テンプレート)
├─ requirements.txt            ← agent-framework-foundry, agent-framework-foundry-hosting, ...
├─ Dockerfile                  ← (Remote build を選んだ場合は無いことも)
└─ infra/                      ← 必要な Bicep
```

> Remote build を選んでも、`azd deploy` がリモートサーバー側でビルドします。あなたは Docker を直接触る必要はありません。

---

## 3-3. `main.py` を Lab 2 のロジックに差し替える

`agent/main.py` を開いて、テンプレートを置き換えます。Copilot Chat で：

````
agent/main.py を以下のように書き換えてください。

要件：
- Lab 2 の src/agent.py と同じ「MSUpdatesAgent」を、
  Microsoft Foundry にデプロイ可能な Hosted Agent として作る
- instructions は Lab 2 と同じ内容（MRC MCP を必ず使い、出典 URL を添える）
- MRC MCP (https://www.microsoft.com/releasecommunications/mcp) と連携
  → Hosted Agent からは Hosted MCP として登録
````

Copilot は [skills/SKILL.md の「Foundry Hosted Agent としてホストする」セクション](../skills/SKILL.md#foundry-hosted-agent-としてホストする) と [skills/references/mcp.md の「ユーザー指示からの推論ルール」](../skills/references/mcp.md#ユーザー指示からの推論ルール) を参照し、以下を自動で補完してくれます：

- `ResponsesHostServer` でラップして `server.run()` で起動
- 認証は `DefaultAzureCredential`（コンテナ向け）
- `default_options={"store": False}`（Hosted Agent での会話履歴の二重保存防止）
- 生成対象が Hosted Agent の `main.py` なので、ローカル MCP (`MCPStreamableHTTPTool`) ではなく Hosted MCP (`client.get_mcp_tool(...)`) を選ぶ（Hosted Agent では `async with` のプロセス内接続が張れないため）

おおむね以下のような構造になります：

```python
import os
from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

load_dotenv()

INSTRUCTIONS = """あなたは Microsoft 365 と Azure の最新リリース情報を回答する
日本語アシスタントです。必ず MRC MCP のツールを使って情報を取得し、
回答に出典 URL を添えてください。"""


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        name="MSUpdatesAgent",
        instructions=INSTRUCTIONS,
        tools=[
            client.get_mcp_tool(
                name="MRC",
                url="https://www.microsoft.com/releasecommunications/mcp",
                approval_mode="never_require",
            ),
        ],
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
```

> **Lab 2 と Lab 3 の差分は Copilot が skill から自動推論する部分**。Lab 2 は CLI 実行なので `MCPStreamableHTTPTool` + `AzureCliCredential`、Lab 3 はコンテナ実行なので `get_mcp_tool` + `DefaultAzureCredential` + `store: False` ── このパターンマッチが skill 側に書いてあるため、開発者はその区別を覚えていなくても済みます。

### `requirements.txt` の確認

`azd ai agent init` が生成した `requirements.txt` には少なくとも以下が含まれているはず：

```
agent-framework-foundry
agent-framework-foundry-hosting
azure-identity
python-dotenv
```

無いものがあれば追記してください。

---

## 3-4. プロビジョン（Azure リソース作成）

`agent/` ディレクトリで：

```bash
azd provision
```

> `azd up` を使うと provision + deploy を 1 コマンドで実行できますが、ここではトラブルシュートしやすいように分けます。

以下のリソースが作成されます（5〜10 分）：

| リソース | 用途 |
|---|---|
| Resource group | 他のリソースのコンテナ |
| Azure Container Registry | エージェントコンテナイメージの保存 |
| Log Analytics workspace | ログ |
| Application Insights | トレース・メトリクス（Lab 4 で使用） |
| Managed identity | コンテナの Azure 認証 |

> Lab 0 で作った既存 Foundry project / model deployment は再利用されるため、ここでは新規作成されません。

---

## 3-5. ローカルで動作確認

```bash
azd ai agent run
```

このコマンドは：
1. 一時的な仮想環境を作る（Python 3.13 必須）
2. `requirements.txt` をインストール
3. `agent.manifest.yaml` の `startupCommand` で `main.py` を起動
4. `http://localhost:8088/responses` で API を公開

> Preview 期間中は依存関係の version conflict 警告が出ることがありますが、起動できれば無視して OK です。

別のターミナルで（`agent/` ディレクトリで）：

```bash
azd ai agent invoke --local "今四半期に GA になった Azure AI 関連の更新を 3 件教えて"
```

応答が返ってくればローカル動作 OK です。`Ctrl+C` でローカルサーバーを停止。

### Windows ARM64 の注意

Windows ARM64 環境では `aiohttp` / `grpcio` / `cryptography` / `httptools` のプリビルド wheel が無く、ソースビルドに Microsoft C++ Build Tools が必要です。この場合 **3-5 をスキップして 3-6 のクラウドデプロイで動作確認** してください。

---

## 3-6. Foundry にデプロイ

```bash
azd deploy
```

このコマンドは：
1. `main.py` + `requirements.txt` をコンテナイメージへビルド（リモートビルド）
2. ACR へ push
3. Foundry に Hosted Agent version を作成
4. 完了すると Playground URL と Agent endpoint が表示される

```
Deploying services (azd deploy)
  Done: Deploying service ms-updates-agent
  - Agent playground (portal): https://ai.azure.com/.../build/agents/ms-updates-agent/build?version=1
  - Agent endpoint: https://<account>.services.ai.azure.com/api/projects/<project>/agents/ms-updates-agent/versions/1
```

完了まで 3〜8 分。

---

## 3-7. デプロイされたエージェントを呼ぶ

### CLI から

```bash
azd ai agent invoke "今四半期に GA になった Azure AI 関連の更新を 3 件教えて"
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

1. 表示された Playground URL をブラウザで開く（または Foundry ポータル > **Build** > **Agents** > `ms-updates-agent` > **Open in playground**）
2. プロンプト例：
   ```
   Microsoft 365 Copilot のロードマップで Outlook 関連を新しい順に 5 件まとめて
   ```
   ```
   今後 90 日以内に Retiring になる Azure 機能を教えて
   ```
3. 下部の **Tool calls** タブで MCP ツール (`search_microsoft_release_messages` 等) が呼ばれていることを確認

---

## 3-8. ★Stretch: コード変更を反映してみる

`agent/main.py` の `INSTRUCTIONS` を編集して、もう一度 `azd deploy` を叩くだけで新バージョンがデプロイされます。

```bash
azd deploy
azd ai agent show     # version が増えている
azd ai agent invoke "テスト質問"
```

新しい version が active になり、過去 version は履歴として残ります。

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `azd ai agent init` が古いオプションを聞く | `azd ext upgrade azure.ai.agents` で 0.1.34-preview 以上にする |
| `SubscriptionNotRegistered` | `az provider register --namespace Microsoft.CognitiveServices` |
| `AuthorizationFailed` during provisioning | **Foundry Project Manager** + **Contributor** が必要。Lab 0 を再確認 |
| `AuthenticationError` / `DefaultAzureCredential` failure | `azd auth logout && azd auth login` |
| `ResourceNotFound` / `DeploymentNotFound` | `FOUNDRY_PROJECT_ENDPOINT` と `AZURE_AI_MODEL_DEPLOYMENT_NAME` を Foundry ポータルで再確認 |
| `AcrPullUnauthorized` | プロジェクト managed identity に **Container Registry Repository Reader** を ACR スコープで付与 |
| `Connection refused` on local run | ポート 8088 が他のプロセスに使われている |
| **Hosted MCP が呼ばれない** | `instructions` でツールを明示 / `approval_mode="never_require"` を確認 |

> `azd ai agent provision` / `azd ai agent up` / `azd ai agent deploy` は **存在しません**。必ず `azd provision` / `azd up` / `azd deploy` を使ってください。

---

## チェックリスト

- [ ] Lab 0 の Foundry project + gpt-5.4-mini デプロイ + Foundry Project Manager 割り当て済み
- [ ] `agent/` ディレクトリで `azd ai agent init` 成功
- [ ] `agent/main.py` を MRC MCP + FoundryChatClient のロジックに書き換え済み
- [ ] `azd provision` 成功
- [ ] `azd ai agent run` でローカル起動成功（Windows ARM64 はスキップ可）
- [ ] `azd ai agent invoke --local "..."` で応答取得（同上スキップ可）
- [ ] `azd deploy` 成功
- [ ] `azd ai agent show` で `Active`
- [ ] `azd ai agent invoke "..."` で応答取得
- [ ] Playground で対話成功・Tool calls タブで MCP 呼び出しを確認

---

次へ → [Lab 4: トレース確認と Cloud Evaluation](04-trace-evaluation.md)
