---
applyTo: "**/*.py"
description: ワークショップ内の Python コード (Lab 2/3/4/5 の src/ や solutions/) を Microsoft Agent Framework 1.8.1 のパターンに沿って書くための規約。
---

# Python コーディング規約 (Agent Framework × Foundry ワークショップ)

このリポジトリの **すべての `.py` ファイル**に適用されます。リポジトリ ルートの [`.github/copilot-instructions.md`](../copilot-instructions.md) と [`skills/SKILL.md`](../../skills/SKILL.md) を合わせて参照してください。

## 必須ルール

- **Python 3.11+** を前提とする。
- すべての関数 / メソッドの引数と戻り値に **型ヒントを付ける** (`-> None` を含む)。
- I/O や Foundry / MCP / credential を扱うコードは **`async def` + `async with`** で書く。リソースは必ず `async with` でクリーンアップする。
- `print()` 直接呼び出しは Lab デモ目的に限定。本番想定のコードでは `logging` を使う。

## 環境変数の扱い

- **`.env` は自動ロードされない**。スクリプトのエントリポイント (`if __name__ == "__main__":` の直前あたり) で必ず:

  ```python
  from dotenv import load_dotenv
  load_dotenv()
  ```

- アプリ コードから読むモデル名の正規変数名は **`FOUNDRY_MODEL`**。`AZURE_AI_MODEL_DEPLOYMENT_NAME` や `AZURE_OPENAI_MODEL` を新規に導入しない。
- 環境変数が未設定 / 空文字のときは **fail-fast** で `RuntimeError` を投げる (Codespaces の空 `.env` 問題対策)。

  ```python
  import os
  endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
  if not endpoint:
      raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT が未設定です。.env を確認してください。")
  ```

## エージェント作成の定型パターン

**シングル エージェントは `FoundryChatClient(...).as_agent(...)` ショートカットを優先**します (公式 Quickstart スタイル)。`Agent(client=...)` を使うのは `client` を別の用途と共有するケースに限る。

```python
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async def main() -> None:
    async with AzureCliCredential() as credential:
        async with FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        ) as client:
            agent = client.as_agent(
                name="HelloAgent",
                instructions="あなたは親切な日本語アシスタントです。",
                tools=[],
            )
            response = await agent.run("自己紹介して")
            print(response.text)
```

## 関数ツール (`@tool`)

- 引数には `Annotated[T, Field(description="...")]` を付ける (Pydantic v2 の `Field` を使う)。
- 関数の docstring 1 行目に「**いつ呼ぶべきか**」を書く (モデルが選択する判断材料)。
- 検証 / Lab 用途では `@tool(approval_mode="never_require")`、本番では `"always_require"`。
- 副作用のあるツール (DB 書き込みなど) は **`async def`** にする。

```python
from typing import Annotated
from pydantic import Field
from agent_framework import tool

@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="天気を取得したい場所 (例: 東京)")],
) -> str:
    """ユーザーが特定の都市の天気を尋ねたときに呼ぶ。"""
    ...
```

## ホスト型ツール

- **`FoundryChatClient.get_*_tool()` クラスメソッド** から取得 (`get_web_search_tool()`, `get_code_interpreter_tool()`, `get_bing_grounding_tool()` 等)。インスタンス化しない。
- 旧 `HostedWebSearchTool` などの import は 1.8 系で削除済み。提案しない。

## 認証 (どの credential を使うか)

| シーン | 推奨 |
|---|---|
| Lab 2 のローカル実行 | `AzureCliCredential()` (`azure.identity.aio` から) |
| Lab 3 の Hosted Agent (`main.py`) | `DefaultAzureCredential()` |
| Lab 4 の評価スクリプト | どちらでも可 |
| Lab 5 (CI/CD) | OIDC + Workload Identity、credential 引数は `DefaultAzureCredential()` のまま |

`credential` は **必ず `async with` で閉じる**。`asyncio.run(main())` で main を駆動する。

## Observability (Lab 4)

- `APPLICATIONINSIGHTS_CONNECTION_STRING` が空のときは初期化をスキップ (fail-fast せず、警告のみ)。
- `ENABLE_SENSITIVE_DATA=true` は **本番禁止** (プロンプト / 応答が App Insights に記録される)。Lab デモで使うときも `.env` だけにとどめる。

```python
from agent_framework.observability import setup_observability
setup_observability(
    connection_string=os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"),
    enable_sensitive_data=os.environ.get("ENABLE_SENSITIVE_DATA", "false").lower() == "true",
)
```

## アンチパターン (提案しない)

- ❌ `agent.run_stream(...)` → 1.8 系では `agent.run(..., stream=True)` を使う。
- ❌ `Message(text="...")` → `Message(contents=[TextContent(text="...")])`。
- ❌ `response.try_parse_value()` → `response.value` を `try / except ValidationError` で受ける。
- ❌ `AzureAIClient` / `AzureAIAgentClient` / `AzureAIAgentsProvider` の import → `FoundryChatClient` / `FoundryAgent` に統一済み。
- ❌ 同期 `with FoundryChatClient(...)` → 非同期コンテキストで使う場合は `async with`。
- ❌ `pip install agent-framework-foundry --pre` の案内 → 1.8.1 は GA 済みのため不要。

## 出力規約

- スクリプトの最後で **必ず `asyncio.run(main())`** を呼ぶ。
- print 出力は日本語で OK (ワークショップ言語)。
- インデントは 4 スペース、行長は 100 文字を目安。

詳細パターン (構造化出力 / MCP / Session) は [`skills/SKILL.md`](../../skills/SKILL.md) と [`skills/references/`](../../skills/references/) を参照。
