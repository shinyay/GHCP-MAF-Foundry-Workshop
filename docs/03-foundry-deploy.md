# Lab 3: Hosted Agent を Foundry へデプロイ

## この Lab で行うこと

- Lab 2 で作った MAF エージェントを **Foundry Hosted Agent** としてデプロイ
- `azd ai agent init --deploy-mode code` でソースコードデプロイ用プロジェクトをスキャフォールドし (コンテナ不要)
- `azd up` で provision + deploy を 1 コマンドで実行
- デプロイ後の動作確認 (`azd ai agent run` / `azd ai agent invoke` / Foundry ポータルの Playground)
- ログとトレースを確認

> この Lab は **[Lab 0](00-setup.md) で Foundry プロジェクト (North Central US) と gpt-4.1-mini モデルが作成済み、かつ自分に Foundry Project Manager ロールが付与済み** であることを前提にしています。未完了なら Lab 0 に戻ってください。

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
azd ext list                      # microsoft.foundry が表示されること
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

## 3-2. `azd ai agent init` でスキャフォールド (ソースコードデプロイ)

リポジトリルートに **`agent/`** サブディレクトリを作って、その中でテンプレートを展開します (Lab 2 の `src/` と分離するため)。

```bash
mkdir agent
cd agent
azd ai agent init --deploy-mode code --runtime python_3_13 --entry-point main.py
```

> **`--deploy-mode code` が重要です** 。これにより Docker 不要のソースコードデプロイ (`main.py` + `requirements.txt` をそのまま zip して Foundry サービス側でホスト) モードになります。コンテナイメージビルドと ACR は不要になり、デプロイ時間も大幅に短縮されます (概ね 1ツ 2 分)。

インタラクティブな質問に答えます (回答例は公式 Quickstart 準拠)：

| # | 質問 | 回答 |
|---|---|---|
| 1 | Language | **Python** |
| 2 | Starter template | **Basic agent (Responses, Agent Framework, Python)** |
| 3 | Agent name | **`ms-updates-agent`** (任意) |
| 4 | Deployment type | **Code deploy** (上記 `--deploy-mode code` で指定済み) |
| 5 | Runtime | **Python 3.13** (上記 `--runtime python_3_13` で指定済み) |
| 6 | Entry point | **`main.py`** (上記 `--entry-point main.py` で指定済み) |
| 7 | Foundry Project | **Use existing Foundry project** (Lab 0 で作った project を選ぶ) |
| 8 | Azure Tenant | あなたのテナント |
| 9 | Azure subscription | あなたのサブスクリプション |
| 10 | Location | **North Central US** (Hosted Agent (preview) が利用可能な唯一のリージョン — Lab 0 でこのリージョンを選択済み) |
| 11 | Model deployment | **`gpt-4.1-mini`** (Lab 0 でデプロイした同名の deployment) |
| 12 | Model version | Lab 0 でデプロイしたバージョン |
| 13 | Model SKU | **GlobalStandard** |
| 14 | Deployment capacity | デフォルトの **10** で OK |
| 15 | Deployment name | Lab 0 で作った deployment 名 (`gpt-4.1-mini`) |

完了時に 「**AI agent definition added to your azd project successfully!**」が表示されます。

### 生成されたファイル

```
agent/
├─ azure.yaml                  ← azd プロジェクト定義 (services.host: foundryagent)
├─ agent.manifest.yaml         ← Hosted Agent 定義 (モデル、runtime: python_3_13、entry-point等)
├─ main.py                     ← エントリポイント (テンプレート)
├─ requirements.txt            ← agent-framework-foundry, agent-framework-foundry-hosting, ...
└─ infra/                      ← 必要な Bicep (Log Analytics / App Insights のみ。ACR 不要)
```

> **Dockerfile は生成されません** 。ソースコードデプロイモードでは Foundry 側が指定された runtime (python_3_13) で `requirements.txt` をインストールし、`main.py` を起動します。もしコンテナ方式を試したい場合は **付録 A** を参照してください。

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

Copilot は [kb-1.8.0/README.md の「Foundry Hosted Agent としてホストする」セクション](../kb-1.8.0/README.md#foundry-hosted-agent-としてホストする) と [kb-1.8.0/api-reference/1.8.0/tools-mcp.md の「ユーザー指示からの推論ルール」](../kb-1.8.0/api-reference/1.8.0/tools-mcp.md#ユーザー指示からの推論ルール) を参照し、以下を自動で補完してくれます：

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
        model=os.environ["FOUNDRY_MODEL"],
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
aiohttp
azure-identity
python-dotenv
```

`aiohttp` は `FoundryChatClient` の HTTP クライアントが使うため、明示的に含めておくとデプロイ時の依存解決エラーを避けられます。無いものがあれば追記してください。

---

## 3-4. `azd up` で provision + deploy を一括実行

`agent/` ディレクトリで：

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

> `azd ai agent provision` / `azd ai agent up` / `azd ai agent deploy` は **存在しません** 。必ず `azd up` / `azd provision` / `azd deploy` (拡張不要) を使ってください。もし provision と deploy を分けてデバッグしたい場合は `azd provision` → `azd deploy` の順で召べます。

---

## 3-5. ローカルで動作確認 (任意)

すでに `azd up` でデプロイ済みのため 3-5 はスキップしても OK ですが、`azd up` 前にコードだけをローカル検証したい場合は以下を使います:

```bash
azd ai agent run --no-inspector
```

このコマンドは:
1. 一時的な仮想環境を作る (Python 3.13 必須)
2. `requirements.txt` をインストール
3. `agent.manifest.yaml` に定義された entry-point (`main.py`) を起動
4. `http://localhost:8088/responses` で API を公開

> `--no-inspector` を付けると Inspector UI を起動せず、ツール起動が高速化されます。Inspector を使いたい場合はフラグを外してください。

別のターミナルで (`agent/` ディレクトリで):

```bash
azd ai agent invoke --local "今四半期に GA になった Azure AI 関連の更新を 3 件教えて"
```

応答が返ってくればローカル動作 OK です。`Ctrl+C` でローカルサーバーを停止。

### Windows ARM64 の注意

Windows ARM64 環境では `aiohttp` / `grpcio` / `cryptography` / `httptools` のプリビルド wheel が無く、ソースビルドに Microsoft C++ Build Tools が必要です。この場合 **3-5 をスキップして `azd up` のクラウドデプロイで動作確認** してください。

---

## 3-6. デプロイされたエージェントを呼ぶ

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

## 3-7. ★Stretch: コード変更を反映してみる

`agent/main.py` の `INSTRUCTIONS` を編集して、もう一度 `azd deploy` を叩くだけで新バージョンがデプロイされます (二回目以降は provision 不要なので `azd up` より `azd deploy` のほうが高速)。

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
| `azd ai agent init` が `--deploy-mode` オプションを認識しない | `azd ext upgrade microsoft.foundry` を実行して拡張を最新化 |
| `SubscriptionNotRegistered` | `az provider register --namespace Microsoft.CognitiveServices` |
| `AuthorizationFailed` during provisioning | **Foundry Project Manager** + **Contributor** が必要。Lab 0 を再確認 |
| `AuthenticationError` / `DefaultAzureCredential` failure | `azd auth logout && azd auth login` |
| `ResourceNotFound` / `DeploymentNotFound` | `FOUNDRY_PROJECT_ENDPOINT` と `FOUNDRY_MODEL` を Foundry ポータルで再確認 |
| `Connection refused` on local run | ポート 8088 が他のプロセスに使われている |
| **Hosted MCP が呼ばれない** | `instructions` でツールを明示 / `approval_mode="never_require"` を確認 |
| `LocationNotAvailableForResourceType` | Hosted Agent (preview) は **North Central US のみ** で提供。Lab 0 でリージョンを間違えた場合はリソースグループを作り直そう |

> `azd ai agent provision` / `azd ai agent up` / `azd ai agent deploy` は **存在しません** 。必ず `azd up` / `azd provision` / `azd deploy` (拡張不要の上位コマンド) を使ってください。

---

## チェックリスト

- [ ] Lab 0 の Foundry project (North Central US) + gpt-4.1-mini デプロイ + Foundry Project Manager 割り当て済み
- [ ] `agent/` ディレクトリで `azd ai agent init --deploy-mode code --runtime python_3_13 --entry-point main.py` 成功
- [ ] `agent/main.py` を MRC MCP + FoundryChatClient のロジックに書き換え済み
- [ ] `azd up` 成功 (provision + deploy 一括)
- [ ] (任意) `azd ai agent run --no-inspector` でローカル起動成功 (Windows ARM64 はスキップ可)
- [ ] (任意) `azd ai agent invoke --local "..."` で応答取得 (同上スキップ可)
- [ ] `azd ai agent show` で `Active`
- [ ] `azd ai agent invoke "..."` で応答取得
- [ ] Playground で対話成功・Tool calls タブで MCP 呼び出しを確認

---

次へ → [Lab 4: トレース確認と Cloud Evaluation](04-trace-evaluation.md)
