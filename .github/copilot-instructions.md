# GHCP × Microsoft Agent Framework × Foundry ワークショップ

このリポジトリは **GitHub Copilot を活用して Microsoft Agent Framework + Microsoft Foundry のエージェントを構築する 5 つの Lab を体験するハンズオン ワークショップ** です。Copilot Chat / Agent モードに対するリポジトリ ルートの規約をここに集約します。**Lab 文脈・既定値・命名規約・推奨手順** はすべてここで一致させてください。

> [!IMPORTANT]
> 詳細な API 知識は [`skills/SKILL.md`](../skills/SKILL.md) と [`skills/references/`](../skills/references/) に集約されています。コード生成・修正の際は必ずそちらを参照し、ここでは「ワークショップ全体の前提・既定値」のみを定義します。

---

## このリポジトリは何か

- **ハンズオン ワークショップ** (テンプレートでもライブラリでもない)。
- 想定読者: Azure / Python の基礎知識がある開発者で、Agent Framework と Foundry を初めて触る人。
- 進行は [`docs/`](../docs/) 直下を **Lab 0 → 1 → 2 → 3 → 4 → 5** の順に。
- 参加者は自分の手で `src/` 配下にコードを書き、Lab 3 で `azd up` し、Lab 4 で評価し、Lab 5 で CI/CD を組みます。
- 模範解答は [`solutions/lab0/`](../solutions/lab0/) 〜 [`solutions/lab5/`](../solutions/lab5/) に置いてあり、**詰まったときの参考**として参照されます。

## バージョン / パッケージ (固定値)

| 項目 | 既定値 |
|---|---|
| Microsoft Agent Framework | **1.8.1 以降** (`agent-framework-foundry`) |
| インストール | `pip install agent-framework-foundry aiohttp azure-identity python-dotenv` (`--pre` 不要) |
| Hosted Agent ホスト側 | `pip install agent-framework-foundry-hosting` を追加 |
| Observability / Evaluation | `pip install azure-monitor-opentelemetry "azure-ai-projects>=2.2.0"` |
| Python | 3.11+ |
| OS | Linux (Dev Container / Codespaces / WSL 推奨) |

> [!NOTE]
> 1.8 系では `Message(text=...)` / `agent.run_stream(...)` / `response.try_parse_value()` / `AzureAIClient` 系は使えません。代わりに `Message(contents=[TextContent(text=...)])` / `agent.run(..., stream=True)` / `response.value` + `ValidationError` ハンドリング / `FoundryChatClient` を使います。

## Foundry 既定環境

| 項目 | 既定値 | 備考 |
|---|---|---|
| リージョン | **`northcentralus`** | Hosted Agent (preview) はこのリージョンのみ (2026 年初頭時点) |
| モデル | **`gpt-4.1-mini`** (deployment name も同じ) | Lab 0-4 でデプロイ |
| SKU | `GlobalStandard` | 既定で十分 |
| azd 拡張 | **`microsoft.foundry`** | 旧 `azure.ai.agents` は非推奨 |
| RBAC ロール | **`Foundry Project Manager`** (`eadc314b-6967-41eb-b9ec-2c8f0d3cd3a5`) | 自分の Entra ID に Lab 0 で割当 |

> [!WARNING]
> 既定リージョン・モデル・ロールを **勝手に書き換えない**。`eastus` や `gpt-4o` 等を提案すると Lab 3 でデプロイが落ちます。

## 環境変数の正規名

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=gpt-4.1-mini
HOSTED_AGENT_NAME=ms-updates-agent
HOSTED_AGENT_VERSION=1

# 任意 (Lab 4)
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;...
ENABLE_INSTRUMENTATION=true
ENABLE_SENSITIVE_DATA=false
```

> [!IMPORTANT]
> - 旧 `AZURE_AI_MODEL_DEPLOYMENT_NAME` は Hosted Agent コンテナへの注入名としては残るが、**アプリ コードからは `FOUNDRY_MODEL` を読む**。両方混在させない。
> - `.env` は **自動ロードされない**。Python スクリプト先頭で必ず `from dotenv import load_dotenv; load_dotenv()` を呼ぶ。
> - `ENABLE_SENSITIVE_DATA=true` は本番禁止 (プロンプト / 応答が App Insights に記録される)。

## 認証 (Lab ごとの推奨)

| Lab | 推奨 | 理由 |
|---|---|---|
| Lab 0 (CLI 操作) | `az login` → `azd auth login` | 双方必要 |
| Lab 2 (ローカル実行) | `AzureCliCredential()` | 軽量で確実 |
| Lab 3 (Hosted Agent) | `DefaultAzureCredential()` | Managed Identity を本番で透過利用 |
| Lab 4 (Evaluation) | `AzureCliCredential()` または `DefaultAzureCredential()` | どちらでも可 |
| Lab 5 (CI/CD) | OIDC + Workload Identity | 鍵を持たない方針 |

```python
from azure.identity import AzureCliCredential  # ローカル
# または
from azure.identity import DefaultAzureCredential  # 本番 / CI
```

## デプロイの主導線 (Lab 3)

- **`azd ai agent init --deploy-mode code`** + **`azd up`** が主導線。
- ソース コード (Python ファイル) をそのまま Foundry へアップロードし、Foundry 側でホスト。
- `--deploy-mode container` (Docker) は **付録扱い**。標準ハンズオンでは扱わない。
- `azd ai agent init` で `agent.yaml` と `infra/` が生成される。**生成された Bicep は基本いじらない**。

> [!TIP]
> `azd ai agent init` が `--deploy-mode` を受け付けない場合は `azd ext upgrade microsoft.foundry` で拡張を更新する。

## エージェント実装のショートカット

- **シングル エージェント**: `FoundryChatClient(...).as_agent(instructions=..., tools=..., name=...)` を優先する (公式 Quickstart スタイル)。
- 関数ツールは `@tool(approval_mode="never_require")` (Lab / 検証用) または `"always_require"` (本番)。
- ホスト型ツールは **`FoundryChatClient.get_*_tool()` クラスメソッド** から取得 (例: `get_web_search_tool()`, `get_code_interpreter_tool()`)。インスタンス化しない。
- 会話継続は `agent.create_session()` (アプリ側) / Foundry Hosted Agent の `conversation_id` (サービス側)。

## Markdown / コードの規約 (要約)

- 詳細は [`.github/instructions/python.instructions.md`](./instructions/python.instructions.md) と [`.github/instructions/docs.instructions.md`](./instructions/docs.instructions.md) を参照。
- すべての Python コードに型ヒント、`async with` で `FoundryChatClient` / credential / MCP をクリーンアップ。
- Markdown のコードブロックには言語タグ必須 (` ```python ` / ` ```bash ` / ` ```text `)。リスト記号は `-`、リンクは repo-relative。

## やってはいけないこと

- ❌ 既存 [`docs/`](../docs/) の Lab 手順を勝手に書き換える (参加者が混乱する)。
- ❌ [`skills/SKILL.md`](../skills/SKILL.md) の API パターンに反するコード (例: `agent.run_stream()`、`AzureAIClient`、`Message(text=...)`) を提案する。
- ❌ `FOUNDRY_MODEL` 以外のモデル指定変数名 (`AZURE_OPENAI_MODEL` 等) を新規導入する。
- ❌ `azd ai agent init --deploy-mode container` を既定として案内する (付録のみ)。
- ❌ Hosted Agent を `eastus` 等 North Central US 以外で動かそうとする (preview 制限)。
- ❌ `.env` を `python-dotenv` なしで読めると仮定する。

## 関連ドキュメント

- [`skills/SKILL.md`](../skills/SKILL.md) — Agent Framework 1.8.1 の使い方 (主要 API)
- [`skills/references/tools.md`](../skills/references/tools.md) — 関数ツール / ホスト型ツール
- [`skills/references/mcp.md`](../skills/references/mcp.md) — ローカル / Hosted MCP 連携
- [`skills/references/threads.md`](../skills/references/threads.md) — 会話継続 (Session / Conversation)
- [`skills/references/advanced.md`](../skills/references/advanced.md) — ストリーミング / 構造化出力 / Observability / Evaluation
- [`.github/prompts/README.md`](./prompts/README.md) — スラッシュ プロンプトの使い方 (`/add-mcp-tool` 等)
