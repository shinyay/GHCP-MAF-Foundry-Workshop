---
name: deploy-hosted-agent
description: ローカルで動作確認済みの Microsoft Agent Framework 1.8.1 エージェントを、Foundry の Hosted Agent としてデプロイする (azd ai agent init --deploy-mode code + azd up)。ワークショップ Lab 3 (docs/03-foundry-deploy.md) のショートカット版。
tools: ["read", "search", "edit"]
---

# /deploy-hosted-agent

ローカルで動いている Agent Framework のエージェントを **Foundry Hosted Agent** としてデプロイするためのプロンプトです。Lab 3 ([`docs/03-foundry-deploy.md`](../../docs/03-foundry-deploy.md)) の作業をエージェントに代行させます。

## When to invoke

以下に該当するとき:

- Lab 2 で `solutions/lab2/src/agent.py` (またはユーザーの `src/agent.py`) が **ローカル実行で動作確認済み**。
- これを Foundry の Hosted Agent として `azd up` でデプロイしたい。
- `--deploy-mode code` (ソース デプロイ) を使う前提。`--deploy-mode container` (Docker) は **付録扱い** なのでこのプロンプトでは扱わない。

新規エージェントを 0 から作るところからは扱わない。既存のローカル動作エージェントがある前提。

## Prerequisites

実装前に確認:

- ローカル エージェントが動作していること。`asyncio.run(main())` で実行できる状態。
- `az login` および `azd auth login` が完了していること。
- Foundry プロジェクトが既に存在していること (Lab 0 完了)。
- `azd` 拡張 **`microsoft.foundry`** がインストール済み (`azd ext list` で確認)。なければ `azd ext install microsoft.foundry`。
- リージョンは **North Central US** (Hosted Agent preview 制約)。
- 詳細は [`solutions/lab3/`](../../solutions/lab3/) と [`docs/03-foundry-deploy.md`](../../docs/03-foundry-deploy.md) を参照。

## Inputs

ユーザーに 1 ターンで確認:

| 入力 | 必須 | デフォルト / 例 |
|---|---:|---|
| **元のローカル コード パス** | はい | `solutions/lab2/src/agent.py` または `src/agent.py` |
| **Hosted Agent 名** | 推測可 | 既定 `ms-updates-agent` |
| **デプロイ ディレクトリ** | 推測可 | リポジトリ ルート直下に `agent/` を新規作成 |
| **Foundry リージョン** | 既定 | **`northcentralus`** (固定。変更は拒否) |
| **モデル** | 既定 | **`gpt-4.1-mini`** (`FOUNDRY_MODEL` の値) |

## Expected output

以下を最小差分で実施:

1. リポジトリ ルート (またはユーザー指定の場所) に **`agent/`** ディレクトリを新規作成。
2. `agent/main.py` を生成: ローカル コードを **Hosted Agent パターン** (`ResponsesHostServer`) に書き換える。
3. `agent/requirements.txt` を生成: `agent-framework-foundry`, `agent-framework-foundry-hosting`, `azure-identity`, `python-dotenv` 等を含める。
4. リポジトリ ルートで `azd ai agent init --deploy-mode code` を **実行案内** (実行はしない)。
5. `agent.yaml` の `name` / `version` がユーザー指定と一致するか確認の案内。
6. 最後に `azd up` の案内。

## Steps

1. **元コードを読む**: `read_file` でローカル エージェント ファイル全文を取得。
2. **Hosted Agent パターンとの差分を確認**: [`solutions/lab3/agent/main.py`](../../solutions/lab3/agent/main.py) を雛形として参照。主な変更点:
   - `Agent(client=...)` の構造は維持。
   - **`credential` は `DefaultAzureCredential()`** に変更 (`AzureCliCredential` ではなく、Managed Identity を透過利用するため)。
   - import 追加: `from agent_framework_foundry_hosting import ResponsesHostServer`。
   - `asyncio.run(main())` を **削除**。代わりに同期 `main()` の末尾で `ResponsesHostServer(agent).run()` を呼ぶ。
   - `default_options={"store": False}` を `Agent(...)` に追加 (Hosted Agent では Foundry が会話履歴を管理するため)。
   - 関数ツールに `@tool(approval_mode="never_require")` 等が付いていることを確認 (Hosted Agent は対話的承認をしない)。
3. **`agent/main.py` 生成**: 上記の変換を加えた `main.py` を `agent/` 直下に書き出す。
4. **`agent/requirements.txt` 生成**:

   ```text
   agent-framework-foundry>=1.8.1
   agent-framework-foundry-hosting>=1.8.1
   azure-identity
   python-dotenv
   aiohttp
   ```

   元コードに追加依存 (例: 関数ツール内で使うライブラリ) があれば追記する。
5. **`.env` 確認**: `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, `HOSTED_AGENT_NAME` が設定されているかチェック。`HOSTED_AGENT_NAME` がなければユーザー指定値を `.env` に追記提案。
6. **`azd ai agent init` の案内** (実行はしない、コマンドを提示):

   ```bash
   # リポジトリ ルートで実行
   azd ai agent init --deploy-mode code --source ./agent
   ```

   - 対話プロンプトで Foundry プロジェクト、サブスクリプション、リージョン (**`northcentralus`** を選択) を聞かれる。
   - `agent.yaml` と `infra/` が生成される。
7. **`agent.yaml` のチェック ポイント**:
   - `name`: ユーザー指定 (例: `ms-updates-agent`) と一致。
   - `version`: 通常 `1`。
   - `model.deployment`: `gpt-4.1-mini`。
   - `entry_point`: `main.py`。
8. **`azd up` の案内** (実行はしない):

   ```bash
   azd up
   ```

   - provision + deploy が一括実行される。初回は 5〜10 分。
   - 完了後、Foundry ポータルの **Agents** タブにデプロイされたエージェントが表示される。

## Verification

ユーザーに案内 (実行はしない):

```bash
# 1. デプロイ完了確認 (Foundry ポータルでも見える)
azd env get-values | grep AGENT

# 2. Hosted Agent への疎通テスト
az rest --method POST \
  --uri "$FOUNDRY_PROJECT_ENDPOINT/agents/$HOSTED_AGENT_NAME/versions/$HOSTED_AGENT_VERSION/responses?api-version=2025-09-01-preview" \
  --body '{"input":"Microsoft 365 の最新リリースを 3 つ"}' \
  --headers "Content-Type=application/json"
```

期待される挙動:

- `azd up` の最終出力に `Deployment succeeded` と URL が出る。
- Foundry ポータル → Agents タブに新しいエージェントが現れる。
- 疎通テストで Hosted Agent が応答する (MCP を使うエージェントなら出典 URL 付き)。

トラブル時:

- `LocationNotAvailableForResourceType` → リージョンを **`northcentralus`** に再選択。`azd env set AZURE_LOCATION northcentralus` で上書き可能。
- `azd ai agent init` に `--deploy-mode` がない → `azd ext upgrade microsoft.foundry`。
- `403 Forbidden` (`azd up` 中) → 自分の Entra ID に **`Foundry Project Manager`** ロール (`eadc314b-6967-41eb-b9ec-2c8f0d3cd3a5`) を Foundry プロジェクトに割当 ([Lab 0](../../docs/00-setup.md) で実施)。
- デプロイ後にエージェントが応答しない → Foundry ポータルの **Logs** タブでコンテナ ログを確認。多くは環境変数未注入 (`FOUNDRY_MODEL` 未設定) か、`DefaultAzureCredential` 失敗。
- MCP ツールが呼ばれない → `default_options={"store": False}` の設定漏れ、`approval_mode` が `"always_require"` で待機中。

## やってはいけないこと

- ❌ `--deploy-mode container` を使う (このプロンプトは `code` 専用)。
- ❌ `eastus` 等 North Central US 以外のリージョンを選ぶ (preview 制約)。
- ❌ `credential=AzureCliCredential()` のままデプロイ (コンテナ内に Azure CLI はない)。
- ❌ `asyncio.run(main())` を `main.py` に残す (`ResponsesHostServer` が代替)。
- ❌ `agent.yaml` を手動で全面書き換え (`azd` 生成内容を尊重し、最小修正にとどめる)。

## 参考

- [`solutions/lab3/agent/main.py`](../../solutions/lab3/agent/main.py) — 完成版 Hosted Agent
- [`solutions/lab3/agent/requirements.txt`](../../solutions/lab3/agent/requirements.txt)
- [`solutions/lab3/README.md`](../../solutions/lab3/README.md)
- [`docs/03-foundry-deploy.md`](../../docs/03-foundry-deploy.md) — Lab 3 手順書
- [`kb-1.8.0/README.md`](../../kb-1.8.0/README.md) — Agent Framework 全般
