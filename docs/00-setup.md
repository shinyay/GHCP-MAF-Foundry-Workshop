# Lab 0: 環境セットアップ

## この Lab で行うこと

- 必要なツールのインストール確認（Python 3.13+, Azure CLI, GitHub CLI, azd, azd `azure.ai.agents` 拡張）
- Azure サブスクリプションへのサインインと**ロール確認（Foundry Project Manager 必須）**
- **Microsoft Foundry プロジェクトを新規作成**
- **gpt-4.1-mini モデルをデプロイ**
- Python 仮想環境準備
- 環境変数（実値入り）`.env` を作成
- ★Optional: ワークショップリポジトリを自分の GitHub アカウントに fork (Lab 5 で GitHub Actions を実行する場合)

> Lab 2 以降は **Foundry プロジェクト + デプロイ済みモデル** が前提です。Foundry プロビジョニングには 5〜10 分かかるので、その待ち時間に Python 環境を並行で整えると効率的です。

---

## 0-1. ツール確認

### 必須ツール

シェル（PowerShell / bash / fish のいずれか）を開いて以下を実行し、すべてバージョンが表示されればOKです。

```bash
python --version          # 3.13 以上
az --version              # 2.60 以上（一行目の azure-cli を確認）
git --version
gh --version              # GitHub CLI 2.40+ (Lab 5 で fork と PR 作成に使用)
code --version            # VS Code が PATH 上にあること
```

未インストールのものがあれば下記からインストール：

| ツール | リンク |
|---|---|
| Python **3.13** | <https://www.python.org/downloads/> |
| Azure CLI | <https://learn.microsoft.com/cli/azure/install-azure-cli> |
| Git | <https://git-scm.com/downloads> |
| **GitHub CLI** | <https://cli.github.com/> |
| VS Code | <https://code.visualstudio.com/> |

> Python 3.13 が必須なのは Hosted Agent (Lab 3) のランタイムが Python 3.13 だからです。3.10 〜 3.12 でも Lab 2 までは動きますが、Lab 3 で `azd ai agent run` がローカル仮想環境を作るときに 3.13 を要求します。

### VS Code 拡張機能

VS Code を開いて、以下の拡張機能がインストール済みか確認：

- **GitHub Copilot**
- **GitHub Copilot Chat**
- **Python**
- **Azure CLI Tools**（任意・便利）
- **Microsoft Foundry Toolkit**（Lab 3 のローカル trace 確認に推奨）<https://aka.ms/foundrytk>

確認コマンド（インストール済み拡張を一覧表示）：

```bash
code --list-extensions
```

必須 ID：`GitHub.copilot` / `GitHub.copilot-chat` / `ms-python.python` が出力に含まれていればOK。

### Lab 3 以降で使うツール（このタイミングで一緒に入れておくのが楽）

**PowerShell（Windows）**

```pwsh
winget install Microsoft.Azd
```

**Bash（macOS / Linux）**

```bash
# macOS
brew tap azure/azd && brew install azd
# Linux
curl -fsSL https://aka.ms/install-azd.sh | bash
```

共通：`azd` バージョン確認 → `azure.ai.agents` 拡張を入れる。

```bash
azd version                                # 1.25.3 以上 (Hosted Agent source-code deploy に必要)
azd extension install azure.ai.agents      # Hosted Agent デプロイ用拡張 (0.1.39 以上必須)
azd extension list                         # azure.ai.agents が表示されればOK
```

> 既にインストール済みの場合は `azd extension upgrade azure.ai.agents` でアップグレードしてください。バージョンが **0.1.39 未満** の場合、`azd ai agent init` で `--deploy-mode` オプションが使えない等の問題が発生します。

---

## 0-2. Azure サインインと権限確認

```bash
az login
azd auth login
az account show --query "{Subscription:name, Tenant:tenantId, User:user.name}"
```

### 必要なロール

ワークショップでは Foundry プロジェクトを新規作成し、その後エージェントをデプロイ・実行します。**Hosted Agent（Lab 3）のデプロイには `Foundry Project Manager` が必須**です。

| 用途 | ロール | スコープ | 必要度 |
|---|---|---|---|
| Foundry リソース / プロジェクト作成 | **Owner** または **Contributor + User Access Administrator** | サブスクリプション or リソースグループ | 既存リソースを使う場合は不要 |
| **Hosted Agent デプロイ (Lab 3+)** | **Foundry Project Manager** | Foundry プロジェクト | **必須** |
| エージェント呼び出し / 評価 | **Foundry User** 以上 | Foundry プロジェクト | 必須 |

ロール名指定で不安定になることを避けるため、本ワークショップではロール定義 ID（GUID）を使います。

| ロール名 | ロール定義 ID (GUID) |
|---|---|
| Foundry User | `53ca6127-db72-4b80-b1b0-d745d6d5456d` |
| Foundry Owner | `c883944f-8b7b-4483-af10-35834be79c4a` |
| Foundry Account Owner | `e47c6f54-e4a2-4754-9501-8e0985b135e1` |
| **Foundry Project Manager** | **`eadc314b-1a2d-4efa-be10-5d325db5065e`** |

権限確認：

**PowerShell**

```pwsh
$subId = az account show --query id -o tsv
$myId  = az ad signed-in-user show --query id -o tsv
az role assignment list --assignee $myId `
    --scope "/subscriptions/$subId" --query "[].roleDefinitionName" -o tsv
```

**Bash**

```bash
SUB_ID=$(az account show --query id -o tsv)
MY_ID=$(az ad signed-in-user show --query id -o tsv)
az role assignment list --assignee "$MY_ID" \
    --scope "/subscriptions/$SUB_ID" --query "[].roleDefinitionName" -o tsv
```

`Owner` または `Contributor + User Access Administrator` があれば、0-3 でプロジェクトを新規作成し、その際に自分自身に **Foundry Project Manager** を割り当てます。

---

## 0-3. Microsoft Foundry プロジェクト作成

ここでプロジェクトの作成だけ**先にトリガー**しておきます。プロビジョニング中（5〜10 分）に 0-5 以降を並行で進めて OK です。

### 方法 A. ポータルから作成（推奨・初回ユーザー向け）

1. ブラウザで [Microsoft Foundry ポータル](https://ai.azure.com) を開く（右上の **New Foundry** トグルが ON になっていることを確認）
2. **+ 新しいプロジェクト** をクリック
3. 以下を入力：
   | 項目 | 値 |
   |---|---|
   | プロジェクト名 | `workshop-foundry-<your-alias>` （例 `workshop-foundry-taro`） |
   | Foundry リソース | **新規作成** を選択 |
   | リソースグループ | **新規作成** — 参加者ごとにユニークな名前 (例: `rg-taro1111`) |
   | リージョン | 任意（`eastus`、`westus2` 等。Lab 3 の Hosted Agent も現在は複数リージョンで利用可能） |
4. **作成** をクリック → 5〜10 分待つ
5. 完了後、プロジェクトの **Overview** ページで **Project endpoint** をコピー（例：`https://<account>.services.ai.azure.com/api/projects/<project>`）

> このエンドポイントは 0-7 で `.env` に貼り付けます。メモ帳等に控えておいてください。

### 自分自身に Foundry Project Manager を割り当て

プロジェクト作成者には通常 Foundry Project Manager が付与されますが、念のため確認・付与します。

**PowerShell**

```pwsh
$rg = "<自分のリソースグループ名>"   # 例: rg-taro1111
$accountName = "<上で作った Foundry リソース名>"
$projectName = "workshop-foundry-<your-alias>"
$myId = az ad signed-in-user show --query id -o tsv

$projectId = az cognitiveservices account project show `
    -g $rg -n $accountName --project-name $projectName --query id -o tsv

az role assignment create `
    --role "eadc314b-1a2d-4efa-be10-5d325db5065e" `
    --assignee-object-id $myId --assignee-principal-type User `
    --scope $projectId
```

**Bash**

```bash
RG="<自分のリソースグループ名>"   # 例: rg-taro1111
ACCOUNT_NAME="<上で作った Foundry リソース名>"
PROJECT_NAME="workshop-foundry-<your-alias>"
MY_ID=$(az ad signed-in-user show --query id -o tsv)

PROJECT_ID=$(az cognitiveservices account project show \
    -g "$RG" -n "$ACCOUNT_NAME" --project-name "$PROJECT_NAME" --query id -o tsv)

az role assignment create \
    --role "eadc314b-1a2d-4efa-be10-5d325db5065e" \
    --assignee-object-id "$MY_ID" --assignee-principal-type User \
    --scope "$PROJECT_ID"
```

> すでに割り当て済みの場合は `RoleAssignmentExists` というエラーが出ますが無視して OK です。

### 方法 B. CLI から全部作成（自動化派・★Stretch）

**PowerShell**

```pwsh
$rg = "rg-<your-alias>"          # 参加者ごとにユニーク (例: rg-taro1111)
$loc = "<リージョン>"              # 例: eastus, westus2 等
$alias = "<your-alias>"           # 英小文字・数字のみ
$accountName = "foundry-$alias"
$projectName = "workshop-foundry-$alias"

az group create -n $rg -l $loc
az cognitiveservices account create `
    -g $rg -n $accountName -l $loc `
    --kind AIServices --sku S0 `
    --custom-domain $accountName --yes

# allowProjectManagement を有効化（project create の前に必須）
$accountId = az cognitiveservices account show -g $rg -n $accountName --query id -o tsv
az resource update --ids $accountId --set properties.allowProjectManagement=true

az cognitiveservices account project create `
    -g $rg -n $accountName `
    --project-name $projectName `
    -l $loc
```

**Bash**

```bash
RG="rg-<your-alias>"              # 参加者ごとにユニーク (例: rg-taro1111)
LOC="<リージョン>"                  # 例: eastus, westus2 等
ALIAS="<your-alias>"              # 英小文字・数字のみ
ACCOUNT_NAME="foundry-$ALIAS"
PROJECT_NAME="workshop-foundry-$ALIAS"

az group create -n "$RG" -l "$LOC"
az cognitiveservices account create \
    -g "$RG" -n "$ACCOUNT_NAME" -l "$LOC" \
    --kind AIServices --sku S0 \
    --custom-domain "$ACCOUNT_NAME" --yes

# allowProjectManagement を有効化（project create の前に必須）
az resource update \
    --ids $(az cognitiveservices account show -g "$RG" -n "$ACCOUNT_NAME" --query id -o tsv) \
    --set properties.allowProjectManagement=true

az cognitiveservices account project create \
    -g "$RG" -n "$ACCOUNT_NAME" \
    --project-name "$PROJECT_NAME" \
    -l "$LOC"
```

エンドポイント取得：

**PowerShell**

```pwsh
az cognitiveservices account project show `
    -g $rg -n $accountName `
    --project-name $projectName `
    --query "properties.endpoints.\"AI Foundry API\"" -o tsv
```

**Bash**

```bash
az cognitiveservices account project show \
    -g "$RG" -n "$ACCOUNT_NAME" \
    --project-name "$PROJECT_NAME" \
    --query 'properties.endpoints."AI Foundry API"' -o tsv
```

---

## 0-4. gpt-4.1-mini モデルをデプロイ

0-3 のプロジェクトが **プロビジョニング完了** してから実行します（Overview ページで状態が `Succeeded` になっていること）。

### 方法 A. ポータルから（推奨）

1. Foundry ポータル > 作成したプロジェクトを開く
2. 左メニュー **Models + endpoints** > **+ Deploy model** > **Deploy base model**
3. 検索ボックスに `gpt-4.1-mini` を入力 → 選択 → **Confirm**
4. デプロイ設定：
   | 項目 | 値 |
   |---|---|
   | Deployment name | **`gpt-4.1-mini`** ← この値を `.env` の `FOUNDRY_MODEL` に使うので**そのまま**にする |
   | Deployment type | **Global Standard** |
5. **Deploy** をクリック → 1〜2 分で完了

### 方法 B. CLI から（★Stretch）

**PowerShell**

```pwsh
az cognitiveservices account deployment create `
    -g $rg --name $accountName `
    --deployment-name "gpt-4.1-mini" `
    --model-name "gpt-4.1-mini" `
    --model-version "2025-04-14" `
    --model-format "OpenAI" `
    --sku-name "GlobalStandard" `
    --sku-capacity 1
```

**Bash**

```bash
az cognitiveservices account deployment create \
    -g "$RG" --name "$ACCOUNT_NAME" \
    --deployment-name "gpt-4.1-mini" \
    --model-name "gpt-4.1-mini" \
    --model-version "2025-04-14" \
    --model-format "OpenAI" \
    --sku-name "GlobalStandard" \
    --sku-capacity 1
```

> `--model-version` と `--sku-capacity` は CLI 2.87.0 以降で必須です。利用可能なバージョンは以下で確認できます：
> ```bash
> az cognitiveservices account list-models -g "$RG" -n "$ACCOUNT_NAME" \
>     --query "[?name=='gpt-4.1-mini'].version" -o tsv
> ```

### 動作確認

Foundry ポータル > **Models + endpoints** に `gpt-4.1-mini` が **Status: Succeeded** で表示されればOK。

---

## 0-5. ★Optional: リポジトリを自分の GitHub に fork して clone

> [!NOTE]
> **Lab 5 (CI/CD) を実施する場合のみ必要です。** Lab 2〜4 だけ実施する場合はこのセクションをスキップして 0-6 へ進んでください。

Lab 5 で **この fork したリポジトリに対して GitHub Actions を走らせる**ため、まず自分の GitHub アカウントに fork します。

### 方法 A. GitHub CLI で fork + clone（推奨）

```bash
gh auth login        # 初回のみ。Web ブラウザで認証
gh repo fork <upstream-owner>/ghcp-maf-foundry-workshop --clone --remote
cd ghcp-maf-foundry-workshop
code .
```

`--clone --remote` を付けると fork と同時に clone され、`origin` が自分の fork、`upstream` が元リポジトリに設定されます。

### 方法 B. ブラウザから fork

1. ブラウザで元リポジトリ `https://github.com/<upstream-owner>/ghcp-maf-foundry-workshop` を開く
2. 右上の **Fork** > **Create fork** をクリック
3. 自分の fork の URL をコピーして clone：

```bash
git clone https://github.com/<your-github-username>/ghcp-maf-foundry-workshop.git
cd ghcp-maf-foundry-workshop
git remote add upstream https://github.com/<upstream-owner>/ghcp-maf-foundry-workshop.git
code .
```

### 確認

```bash
git remote -v
# origin    https://github.com/<your-github-username>/ghcp-maf-foundry-workshop.git (fetch/push)
# upstream  https://github.com/<upstream-owner>/ghcp-maf-foundry-workshop.git       (fetch/push)
```

ディレクトリ構造を確認：

```bash
ls -la                 # Bash
Get-ChildItem -Force   # PowerShell
```

`docs/`、`kb-1.8.0/`、`.github/` があればOK。

---

## 0-6. Python 仮想環境とパッケージ

### 仮想環境の作成と有効化

**PowerShell（Windows）**

```pwsh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Bash（macOS / Linux / WSL / Git Bash）**

```bash
python -m venv .venv
source .venv/bin/activate    # Windows の Git Bash なら source .venv/Scripts/activate
```

**Fish（macOS / Linux で fish shell を使う場合）**

```fish
python -m venv .venv
source .venv/bin/activate.fish    # Fish は activate.fish を明示的に指定する必要あり
```

> Fish で `source .venv/bin/activate` を実行すると `Unsupported use of '='` エラーが出ます。必ず `activate.fish` を指定してください。

### パッケージインストール（両シェル共通）

```bash
pip install --upgrade pip

# Lab 2 (ローカル MAF) 用 —— Agent Framework Python 1.0.0 GA 以降
# `--pre` 不要。`aiohttp` は FoundryChatClient の HTTP クライアントが使用。
# `mcp` は `MCPStreamableHTTPTool` / `MCPStdioTool` 用 (Lab 2 で MRC MCP 接続に必須)。
pip install agent-framework-foundry aiohttp mcp
pip install azure-identity python-dotenv pydantic

# Lab 4 (Cloud Evaluation) 用 —— evals API は 2.2.0 以降で安定化
pip install "azure-ai-projects>=2.2.0"
```

> `mcp` は `agent-framework-core` の **optional extra** (`agent-framework-core[all]` に含まれる) なので、`agent-framework-foundry` だけインストールしても入りません。Lab 2 で `MCPStreamableHTTPTool` を使うので**明示的にインストール**してください。インストールしないと runtime に `ModuleNotFoundError: 'MCPStreamableHTTPTool' requires 'mcp'` で fail します (class import 自体は成功するため compileall では検出されません)。

> Agent Framework Python 1.0.0 は 2026 年初頭に GA したため `--pre` は不要になりました。ただし `agent-framework[all]` umbrella は依存解決に時間がかかるので、上記のように `agent-framework-foundry` + 個別依存を明示するのが安定します。

> Lab 3 (Hosted Agent デプロイ) では `agent-framework-foundry-hosting` も必要になりますが、Lab 3 で `azd ai agent init` を実行すると `requirements.txt` が生成されてそこに記載されるので、ここで明示インストール不要です。

> 仮想環境を VS Code が認識しない場合は `Ctrl+Shift+P` → **Python: Select Interpreter** で `.venv` 配下の Python を選択。

インストール確認：

```bash
python -c "import agent_framework; print(agent_framework.__version__)"
python -c "from agent_framework.foundry import FoundryChatClient; print('FoundryChatClient OK')"
python -c "from azure.ai.projects import AIProjectClient; print('AIProjectClient OK')"
python -c "from mcp.client.streamable_http import streamable_http_client; print('mcp streamable_http OK')"
```

4 行とも例外なく実行できればOKです。最後の `mcp` import test は Lab 2 で `MCPStreamableHTTPTool` が runtime に必要とする lazy import を事前検証します。

---

## 0-7. 環境変数（`.env`）作成

リポジトリ ルートには **`.env.sample` と `.gitignore` が最初から配置済み** です。テンプレートをコピーして実値を書き込むだけで完了します。

### `.env.sample` をコピーして `.env` を作成

両シェル共通（`cp` は PowerShell では `Copy-Item` のエイリアス）：

```bash
cp .env.sample .env
code .env    # FOUNDRY_PROJECT_ENDPOINT に 0-3 のエンドポイントを貼り付ける
```

書き換えるのは原則 `FOUNDRY_PROJECT_ENDPOINT` の URL だけ。`FOUNDRY_MODEL=gpt-4.1-mini` は 0-4 で同名でデプロイしたのでそのままで OK。`HOSTED_AGENT_NAME` / `HOSTED_AGENT_VERSION` は Lab 3 完了後に必要に応じて更新します。

> `.gitignore` には最初から `.env` の除外が含まれているため、誤コミットの心配はありません。

---

準備ができたら → [Lab 1: Agent Skills の作成と Copilot での利用](01-agent-skills.md)
