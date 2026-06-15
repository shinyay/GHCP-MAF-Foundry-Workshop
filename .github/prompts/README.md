# スラッシュ プロンプト (`.github/prompts/`)

このフォルダには **VS Code のスラッシュ プロンプト** (`.prompt.md`) が入っています。Copilot Chat のテキスト ボックスで `/プロンプト名` と打つと、エージェントがプロンプト ファイルの指示に従って作業します。ワークショップでは Lab 3 / 4 / 5 のステップをショートカット化するために使います。

## 提供されているプロンプト

| スラッシュ コマンド | 目的 | 対応 Lab |
|---|---|---|
| `/deploy-hosted-agent` | ローカルで動くエージェントを Foundry の Hosted Agent としてデプロイする (`azd ai agent init --deploy-mode code` + `azd up`) | [Lab 3](../../docs/03-foundry-deploy.md) |
| `/add-cloud-evaluation` | デプロイ済み Hosted Agent を Cloud Evaluation (PromptyEvaluator) で採点するスクリプトを生成 | [Lab 4](../../docs/04-trace-evaluation.md) |
| `/add-mcp-tool` | 既存のエージェントに **MCP サーバー** (ローカル または Hosted) を 1 つ追加する | [Lab 5](../../docs/05-cicd.md) の前段 |

## 使い方 (VS Code)

1. Copilot Chat を開く (Ctrl+Alt+I)。
2. 入力欄で **`/`** を押すと利用可能なプロンプトが補完される。
3. 例: `/add-mcp-tool` を選んで Enter。
4. プロンプトが追加の入力 (MCP サーバーの URL など) を聞いてくるので、それに答える。
5. エージェントが [`kb-1.8.0/README.md`](../../kb-1.8.0/README.md) と [`kb-1.8.0/`](../../kb-1.8.0/) を参照しながら、対応する `src/` ファイルを編集する。

## いつ使うか

- ✅ Lab を一通り終えた後で **同じ作業を別のエージェントで繰り返したい** とき。
- ✅ 手順は理解しているが **タイピング量を減らしたい** とき。
- ✅ 標準パターンから逸脱しない安全な変更を **短時間で適用したい** とき。

## いつ使わないか

- ❌ Lab 1 (skill を自作する練習): プロンプトに頼らず自分で書く価値がある。
- ❌ Lab 1 の前: 何が起きているか理解する前にプロンプトを使うと、ブラック ボックス化する。
- ❌ 初見のリポジトリ: プロンプトは「このワークショップの既定値」を仮定している。他リポジトリへ流用しない。

## カスタマイズ

自分で新しいプロンプトを書きたい場合は、既存ファイルをコピーして編集してください。最小限のフロントマター:

```yaml
---
name: my-prompt
description: 何をするプロンプトかの 1 行説明 (Copilot Chat の補完に表示される)
tools: ["read", "search", "edit"]   # 使うツール (任意)
---
```

本文の構成は既存プロンプトを参考に:

1. **When to invoke** — このプロンプトをいつ呼ぶか
2. **Prerequisites** — 事前に確認すべきこと
3. **Inputs** — ユーザーから受け取る情報
4. **Expected output** — 何を生成するか
5. **Steps** — エージェントが従うべき手順
6. **Verification** — 動いたかどうかを確認するコマンド

## 関連

- [`copilot-instructions.md`](../copilot-instructions.md) — ワークショップ全体の既定値
- [`instructions/`](../instructions/) — Python / Markdown の自動適用スタイル
- [`kb-1.8.0/README.md`](../../kb-1.8.0/README.md) — Agent Framework API の知識ベース
