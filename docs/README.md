# GitHub Copilot × Microsoft Agent Framework × Microsoft Foundry ハンズオン ワークショップ

GitHub Copilot の **Agent Skills** を活用しながら、**Microsoft Agent Framework (MAF) Python SDK** で「**Microsoft / Azure 最新情報エージェント**」を作り、**Microsoft Foundry の Hosted Agent** にデプロイ、**トレース／評価**、最後に **GitHub Actions CI/CD で自動デプロイ＋自動評価** までを一通り体験するワークショップです。

## 学習ゴール

| # | 達成項目 |
|---|---------|
| 1 | Agent Skills の概念と作り方を理解し、Copilot に呼び出させられる |
| 2 | MAF Python SDK で MCP サーバー連携エージェントを Copilot 補助のもとで作れる |
| 3 | Foundry に Hosted Agent としてデプロイし、Playground でテストできる |
| 4 | OpenTelemetry トレースを Application Insights に流し、Cloud Evaluation で品質を測れる |
| 5 | GitHub Actions で「機能追加 PR → 自動評価 → main マージで自動デプロイ」を体験できる |

## 対象者

- Python の基本（`async/await`、関数定義、Pydantic）が分かる
- Azure CLI で `az login` できる
- GitHub と VS Code を日常的に使う
- 生成 AI／エージェントに**初めて or 触ったことがある**程度（中級者にも対応）
- **このリポジトリを自分の GitHub に fork できる**（Lab 5 で GitHub Actions を走らせるため）

## シナリオ：Microsoft / Azure 最新情報エージェント

[Microsoft Release Communications MCP Server](https://learn.microsoft.com/ja-jp/microsoft-365/admin/manage/mrc-mcp?view=o365-worldwide)（公開・無料・**認証不要**）と連携し、以下のような質問に答える社内向けエージェントを作ります：

- 「今四半期に GA になった Azure AI サービスの更新は？」
- 「今後 3 か月以内に廃止される Azure 機能を教えて」
- 「最新の Microsoft 365 Copilot ロードマップ項目を 5 件まとめて」

MCP エンドポイント：`https://www.microsoft.com/releasecommunications/mcp`

公開ツール（主要 4 つ）：
- `search_microsoft_release_messages` — Microsoft 365 メッセージ センター
- `search_microsoft_roadmap` — Microsoft 365 ロードマップ
- `search_azure_updates` — Azure Updates
- `search_microsoft_documentation` — Microsoft Learn

## Lab 一覧

| Lab | 内容 | 想定時間 |
|-----|-----|---|
| Lab 0 | [環境セットアップ（リポジトリ fork + Foundry プロジェクト + gpt-4.1-mini デプロイ）](00-setup.md) | 30 分 |
| Lab 1 | [Agent Skills の作成と Copilot での利用](01-agent-skills.md) | 20 分 |
| Lab 2 | [MAF で Microsoft 最新情報エージェント作成](02-maf-agent.md)（Copilot に作らせる） | 40 分 |
| Lab 3 | [Hosted Agent を Foundry へデプロイ](03-foundry-deploy.md) | 40 分 |
| Lab 4 | [トレース確認と Cloud Evaluation](04-trace-evaluation.md) | 30 分 |
| Lab 5 | [GitHub Actions で CI/CD 化（完成版 YAML をコピペ + Microsoft Learn MCP 追加 PR）](05-cicd.md) | 30 分 |

> 各 Lab の冒頭に **「この Lab で作るもの」** を明記しています。
> 時間や進捗の都合で短縮したい場合は **★Stretch** マークの章をスキップしてください。

## 前提ツール

| 必須 / 任意 | ツール | 確認コマンド | 補足 |
|---|---|---|---|
| 必須 | **Python 3.13+** | `python --version` | Hosted Agent のランタイムが Python 3.13 |
| 必須 | Azure CLI 2.60+ | `az --version` | |
| 必須 | Git | `git --version` | |
| 必須 | **GitHub CLI** 2.40+ | `gh --version` | Lab 0 の fork と Lab 5 の PR 作成で使用 |
| 必須 | VS Code | （GUI） | |
| 必須 | GitHub Copilot 拡張 | `code --list-extensions` | `GitHub.copilot` / `GitHub.copilot-chat` |
| 必須 | Azure サブスクリプション | | Foundry プロジェクト作成権限 + **Foundry Project Manager** |
| 必須 | **GitHub アカウント** | | Lab 5 でこのリポジトリを fork して Actions を動かす |
| Lab 3+ | Azure Developer CLI (azd) 1.25.3+ | `azd version` | |
| Lab 3+ | `microsoft.foundry` 拡張 | `azd ext list` | |
| Lab 4 | Docker（任意：Aspire Dashboard でローカルトレース確認） | `docker --version` | ★Stretch |

> セットアップ手順は [Lab 0](00-setup.md) で詳細に案内します。

## このリポジトリの構成

```
ghcp-maf-foundry-workshop/
├─ docs/                          ← ワークショップ手順書（このフォルダー）
│  ├─ README.md                  ← 本ファイル
│  ├─ 00-setup.md                ← Lab 0
│  ├─ 01-agent-skills.md         ← Lab 1
│  ├─ 02-maf-agent.md            ← Lab 2
│  ├─ 03-foundry-deploy.md       ← Lab 3
│  ├─ 04-trace-evaluation.md     ← Lab 4
│  └─ 05-cicd.md                 ← Lab 5
├─ kb-1.8.0/                      ← MAF Copilot 用詳細 KB (chatmodes が参照)
│  ├─ SKILL.md
│  └─ references/
├── .github/
│  ├─ instructions/              ← Copilot が自動読込する instruction
│  └─ workflows/                 ← Lab 5 で作成
├── data/
│  └─ eval_inputs.json           ← Lab 4 / Lab 5 が読む評価用クエリ集（最初から配置済み）
├── solutions/                     ← 各 Lab の完成版ファイル（困ったとき / 急いで通したいとき用）
│  ├─ README.md
│  ├─ lab0/  lab2/  lab3/  lab4/  lab5/
├── src/                          ← Lab 2 以降のエージェントコード（参加者が作成）
├── .env.sample                    ← Lab 0 でコピーして .env を作るテンプレート（最初から配置済み）
└── .gitignore                     ← .env / .venv / .azure / 評価結果などを除外（最初から配置済み）
```

> **`solutions/` フォルダー** には各 Lab で書くべきコードの完成版が入っています。詰まったときや時間が押したときは [`solutions/README.md`](../solutions/README.md) を参照してください。


## 参考ドキュメント

- [Microsoft Agent Framework 公式](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)
- [Microsoft Foundry Hosted Agents Quickstart (azd)](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Hosted Agent permissions reference](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions)
- [Microsoft Foundry RBAC](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)
- [Microsoft Release Communications MCP Server](https://learn.microsoft.com/ja-jp/microsoft-365/admin/manage/mrc-mcp?view=o365-worldwide)
- [Agent Framework Observability (Python)](https://learn.microsoft.com/agent-framework/agents/observability)
- [Foundry Cloud Evaluation (`azure-ai-projects` `evals`)](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/ai/azure-ai-projects/samples/evaluations)
- [hosted-agents/agent-framework Python samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/responses)
- [GitHub Copilot Customization](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)

---

準備ができたら [Lab 0: 環境セットアップ](00-setup.md) から始めてください。
