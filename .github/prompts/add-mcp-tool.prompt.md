---
name: add-mcp-tool
description: 既存の Microsoft Agent Framework 1.8.1 エージェントに MCP サーバー (ローカル または Hosted) を 1 つ追加する。ワークショップの Lab 5 前段で使う想定。kb-1.8.0/README.md と kb-1.8.0/api-reference/1.8.0/tools-mcp.md の正規パターンに従う。
tools: ["read", "search", "edit"]
---

# /add-mcp-tool

既存のエージェントに **MCP サーバー** (Model Context Protocol) を 1 つ追加するためのプロンプトです。Lab 2 / 3 で作ったエージェントに Microsoft Learn MCP を追加するなど、外部知識ソースを増やすときに使います。

## When to invoke

以下のいずれかに該当するとき:

- 既存のエージェント (`solutions/lab2/`, `solutions/lab3/agent/main.py`, または参加者の `src/`) に MCP ツールを追加したい。
- ユーザーが「Microsoft Learn MCP を使いたい」「外部 MCP サーバー `https://...` を追加したい」と依頼してきた。
- 既に動くエージェントがあり、**最小差分で MCP を 1 つだけ追加**したい。

新規エージェントを 0 から作る場合はこのプロンプトを使わず、[`kb-1.8.0/README.md`](../../kb-1.8.0/README.md) のクイックスタートから始める。

## Prerequisites

エディタの状態を確認 (推測ではなく実際に読む):

- 編集対象ファイルが `FoundryChatClient(...).as_agent(...)` または `Agent(client=FoundryChatClient(...))` のパターンで書かれていること。
- `tools=[...]` の引数がすでに存在し、追加できること。
- `agent-framework-foundry` (1.8.1+) が `requirements.txt` または `pyproject.toml` で依存に入っていること。
- `.env` が `FOUNDRY_PROJECT_ENDPOINT` と `FOUNDRY_MODEL` を含むこと。
- 詳細パターンは [`kb-1.8.0/api-reference/1.8.0/tools-mcp.md`](../../kb-1.8.0/api-reference/1.8.0/tools-mcp.md) を参照。

## Inputs

ユーザーに最小限の以下を確認 (1 ターンでまとめて聞く):

| 入力 | 必須 | 例 |
|---|---:|---|
| **編集対象ファイル** | はい | `solutions/lab2/src/agent.py` / `src/agent.py` |
| **MCP サーバー URL** | はい | `https://learn.microsoft.com/api/mcp` |
| **MCP の表示名** | 推測可 | URL から推測 (例: `learn.microsoft.com` → `"Learn"`) |
| **Local か Hosted か** | 推測可 | 下記ルールで自動判別 |
| **認証ヘッダー** | いいえ | 公開 MCP なら不要 |

### Local vs Hosted の自動判別

- 編集対象が **Lab 3 の `solutions/lab3/agent/main.py`** または `ResponsesHostServer` でラップされる Hosted Agent → **Hosted MCP** (`FoundryChatClient.get_mcp_tool(...)`)
- それ以外のローカル実行スクリプト (`asyncio.run(main())` で動かす) → **Local MCP** (`MCPStreamableHTTPTool`)

迷ったら **ユーザーに確認**。憶測で決めない。

## Expected output

最小差分の編集:

- import を 1 行追加 (Local なら `from agent_framework import MCPStreamableHTTPTool`、Hosted なら不要)。
- 既存の `tools=[...]` リストに MCP ツールを 1 つ追加。**他のツールを消さない**。
- Local の場合は `async with MCPStreamableHTTPTool(...)` で `client` の外側 (または同階層) に追加し、`tools=[..., mcp]` に渡す。
- Hosted の場合は `tools=[..., FoundryChatClient.get_mcp_tool(...)]` を追加するだけ。

不要なリファクタリングはしない (instructions の書き換え、別ツールの再配置、関数の分割など)。

## Steps

1. **編集対象を読む**: `read_file` で対象ファイルの全文を取得し、`tools=[...]` の現在の中身を把握する。
2. **既存パターンを照合**: [`kb-1.8.0/api-reference/1.8.0/tools-mcp.md`](../../kb-1.8.0/api-reference/1.8.0/tools-mcp.md) の「ユーザー指示からの推論ルール」表に従い Local / Hosted を確定。
3. **Local MCP の場合**:
   - import 追加: `from agent_framework import MCPStreamableHTTPTool`
   - `async with` ブロックで MCP を開き、その内側でエージェントを作る:

     ```python
     async with MCPStreamableHTTPTool(
         name="Learn",  # URL から推測した名前
         url="https://learn.microsoft.com/api/mcp",
     ) as learn_mcp:
         agent = FoundryChatClient(
             project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
             model=os.environ["FOUNDRY_MODEL"],
             credential=credential,
         ).as_agent(
             instructions="...",
             tools=[learn_mcp, ...],  # 既存ツールを保持
         )
     ```

4. **Hosted MCP の場合**:
   - import 追加なし (`FoundryChatClient` は既に import 済みのはず)。
   - `tools=[...]` に追加:

     ```python
     tools=[
         FoundryChatClient.get_mcp_tool(
             name="Learn",
             url="https://learn.microsoft.com/api/mcp",
             approval_mode="never_require",
         ),
         # ... 既存ツール
     ],
     ```

   - Hosted Agent の `main.py` を編集している場合は、`default_options={"store": False}` を確認する (なければ追記)。
5. **instructions に 1 文追加** (任意): MCP を使った回答方針を 1 行追加。例: 「Microsoft Learn を必ず参照し、出典 URL を添えること」。
6. **`.env.sample` 更新**: MCP に認証ヘッダーが必要なら、対応する環境変数名を追記 (値はプレースホルダー)。
7. **検証コマンドを提示** (実行はしない): 下記の Verification を参考に、ユーザーに何を試せばよいかを伝える。

## Verification

ユーザーに以下のコマンドを案内 (エージェント自身は実行しない):

```bash
# 構文チェック
python -m compileall -q <編集したファイル>

# 実行 (Lab 2 のローカル実行例)
cd solutions/lab2  # または対象ディレクトリ
python src/agent.py
```

期待される動作:

- MCP に関連する質問 (例: 「Azure AI Foundry Hosted Agent の概要を教えて」) に対し、エージェントが MCP ツールを呼び出して回答する。
- ターミナル出力に `[tool] Learn(...) called` のような MCP 呼び出しログが出る (Lab 4 で observability を入れた後はトレースに表示)。

エラーが出た場合の典型:

- `MCP timeout` → MCP サーバー側の応答時間。URL が正しいか / 認証ヘッダーが要るか確認。
- `tool not found` → `name` のスペル違い。一意になっているか確認。
- Hosted Agent で MCP が呼ばれない → `default_options={"store": False}` の設定漏れ、または `approval_mode` が `"always_require"` で対話的承認待ち。

## 参考

- [`kb-1.8.0/README.md`](../../kb-1.8.0/README.md) — Agent Framework 全般
- [`kb-1.8.0/api-reference/1.8.0/tools-mcp.md`](../../kb-1.8.0/api-reference/1.8.0/tools-mcp.md) — MCP 詳細 (Stdio / WebSocket 含む)
- [`docs/05-cicd.md`](../../docs/05-cicd.md) — Lab 5
