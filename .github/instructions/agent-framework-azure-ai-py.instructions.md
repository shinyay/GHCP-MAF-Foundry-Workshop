---
applyTo: "**"
description: Microsoft Agent Framework Python SDK (agent-framework-foundry) で Microsoft Foundry のエージェントを作るための skill。FoundryChatClient / FoundryAgent によるエージェント作成、ホスト型ツール（Code Interpreter / File Search / Web Search / Bing Grounding / Image Generation / Azure AI Search / Hosted MCP）や関数ツール（@tool）の追加、ローカル MCP 連携 (MCPStreamableHTTPTool 等)、AgentSession による会話継続、ストリーミング応答 (agent.run(..., stream=True))、構造化出力 (Pydantic / JSON Schema)、Hosted Agent としての azd デプロイ、OpenTelemetry observability、Cloud Evaluation などのタスクで skills/SKILL.md を参照する。
---

# agent-framework-foundry-py

このリポジトリには [skills/SKILL.md](../../skills/SKILL.md) に Agent Skill が同梱されています。
以下のようなタスクで Copilot が自動的に参照します。

- Microsoft Foundry でエージェントを作る (`Agent(client=FoundryChatClient(...))` / `FoundryAgent`)
- ツールを追加する（Code Interpreter / File Search / Web Search / Bing Grounding / Image Generation / Azure AI Search / Hosted MCP / 関数ツール）
- MCP サーバー連携（local: `MCPStreamableHTTPTool` ほか / hosted: `FoundryChatClient.get_mcp_tool`）
- 会話継続（`AgentSession` / `agent.create_session()`）、ストリーミング応答 (`agent.run(..., stream=True)`)
- 構造化出力 (Pydantic / JSON Schema)、observability (`configure_otel_providers`)、Cloud Evaluation
- Foundry Hosted Agent としてのデプロイ (`ResponsesHostServer` + `azd ai agent init` + `azd deploy`)

詳細なリファレンスは [skills/references/](../../skills/references/) を参照してください。

## 関連する規約

ワークショップ全体の既定値・ファイル別スタイルは次に分離されています。本ファイルは API 知識への入口、以下はコーディング規約です。

- [`copilot-instructions.md`](../copilot-instructions.md) — ワークショップ全体のバージョン / 環境 / 認証 既定値
- [`python.instructions.md`](./python.instructions.md) — `**/*.py` 適用の Python 規約
- [`docs.instructions.md`](./docs.instructions.md) — `**/*.md` 適用の Markdown 規約
- [`../prompts/README.md`](../prompts/README.md) — スラッシュ プロンプト一覧と使い方

