# Lab 2: MAF で Microsoft 最新情報エージェント作成

## この Lab で行うこと

**Lab 1 で確認した Agent Skill を使って、Copilot にエージェントを作らせます。** 自分で MAF の API を覚える必要はありません。Copilot に **何を作りたいか** を伝えるだけで、skill が裏で正しいパターンを供給します。

完成するエージェント：

- **名前**: MS Updates Agent
- **連携先**: [Microsoft Release Communications MCP Server](https://learn.microsoft.com/ja-jp/microsoft-365/admin/manage/mrc-mcp?view=o365-worldwide)
- **エンドポイント**: `https://www.microsoft.com/releasecommunications/mcp`（**認証不要**）
- **機能**: Microsoft 365 メッセージ センター、ロードマップ、Azure Updates、Microsoft Learn を自然言語で照会

> Lab 3 でこのコードをほぼそのまま **Foundry Hosted Agent** に載せます。Lab 2 で動かすコードと Lab 3 のコンテナ用 `main.py` の差分は最小限になるよう設計しています。

## 前提

- [Lab 0](00-setup.md) で `.venv` 有効化済み、`agent-framework-foundry` インストール済み（`from agent_framework.foundry import FoundryChatClient` が成功している）
- [Lab 1](01-agent-skills.md) で MAF × Foundry の skill が Copilot に認識されていることを確認済み
- `.env` に `FOUNDRY_PROJECT_ENDPOINT` と `AZURE_AI_MODEL_DEPLOYMENT_NAME` が設定済み

---

## 2-1. Copilot にエージェントの骨格を作らせる

VS Code で `src/agent.py` を新規作成（`src/` フォルダーがなければ Copilot が作ります）。

Copilot Chat（`Ctrl+Alt+I`）で以下のプロンプトを入力：

````
src/agent.py を新規作成してください。

要件：
- Microsoft Agent Framework Python SDK を使う
- Microsoft Foundry に接続
- エージェント名は "MSUpdatesAgent"
- instructions:
  「あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。
   必ず MRC MCP のツール（https://www.microsoft.com/releasecommunications/mcp）を使って情報を取得し、回答に出典 URL を添えてください。」
````

Copilot は [skills/SKILL.md](../skills/SKILL.md) と [skills/references/mcp.md](../skills/references/mcp.md) / [skills/references/tools.md](../skills/references/tools.md) を読み、以下を自動補完してくれます：

- `python-dotenv` で `.env` を読み込み、Foundry プロジェクトエンドポイントとモデルデプロイメント名を環境変数から取る
- ローカル CLI として走らせるため認証は `AzureCliCredential`
- `Agent(client=FoundryChatClient(...))` パターン
- 指示文中に MCP URL があるので ([mcp.md の推論ルール](../skills/references/mcp.md#ユーザー指示からの推論ルール)) `MCPStreamableHTTPTool` を `async with` で開いて `tools=` に渡す
- `main()` は `async def` + `asyncio.run(main())`。CLI 引数があればそれを質問に、無ければ妥当なサンプル質問を使う

だいたい以下のようなコードが生成されます：

```python
import asyncio
import os
import sys
from dotenv import load_dotenv

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

load_dotenv()

INSTRUCTIONS = """あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。必ず MRC MCP のツール（https://www.microsoft.com/releasecommunications/mcp）を使って情報を取得し、回答に出典 URL を添えてください。"""

MCP_URL = "https://www.microsoft.com/releasecommunications/mcp"


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else \
        "今四半期に GA になった Azure AI 関連の更新を 3 件教えて"

    async with MCPStreamableHTTPTool(name="MRC", url=MCP_URL) as mrc_mcp:
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                credential=AzureCliCredential(),
            ),
            name="MSUpdatesAgent",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp],
        )
        response = await agent.run(query)
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
```

> **ここが Agent Skill の価値**。あなたは「接続して、この instructions で、MCP と連携させる」だけ書いたのに、Copilot は認証クラス・環境変数名・`async with` の使い方・CLI スケルトンを skill から補ってくれます。SDK の細かな API を覚えている必要はありません。

---

## 2-2. 動作確認

```bash
python src/agent.py
```

数秒〜数十秒で応答が返ってきます。

質問を指定して：

```bash
python src/agent.py "Microsoft 365 Copilot のロードマップで Outlook 関連を 5 件教えて"
```

### よくあるエラー

| エラー | 原因 / 対処 |
|---|---|
| `KeyError: 'FOUNDRY_PROJECT_ENDPOINT'` | `.env` が読まれていない。スクリプト先頭で `load_dotenv()` が呼ばれているか確認 |
| `DefaultAzureCredentialError` / 401 / 403 | `az login` 未実行、別テナント、または `Foundry User` ロール不足。Lab 0 の 0-2 を再確認 |
| `Tool 'search_microsoft_*' not found` | MCP URL が間違っている。`https://www.microsoft.com/releasecommunications/mcp` を再確認 |
| MCP ツールが呼ばれない | `instructions` で**明示的に**ツール名を列挙してプロンプト誘導 |

---

## 2-3. 会話継続＋ストリーミングに拡張する

Copilot Chat で：

````
src/agent.py を「会話継続できる対話モード」に書き換えてください。
- 同じ session を使い回して文脈を保持
- 応答はストリーミングで逐次表示
- ターン毎に会話 ID を「[conv:xxxx]」の形で先頭表示
````

Copilot は `skills/references/threads.md` を参照し、「終了ワード (quit/exit/終了) でループを抜ける」「`agent.create_session()` を会話開始時に 1 回だけ作る」「`agent.run(prompt, stream=True, session=session)` を `async for chunk` で回す」という既定動作を補完して、おおむね以下のような構造に書き換えます：

```python
async def main() -> None:
    async with MCPStreamableHTTPTool(name="MRC", url=MCP_URL) as mrc_mcp:
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                credential=AzureCliCredential(),
            ),
            name="MSUpdatesAgent",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp],
        )
        session = agent.create_session()

        print("MS Updates Agent。質問を入力してください（quit/exit/終了で終わり）")
        while True:
            user_input = input("\nあなた: ").strip()
            if user_input.lower() in {"quit", "exit", "終了"}:
                break
            if not user_input:
                continue

            print(f"\n[conv:{getattr(session, 'conversation_id', 'pending')}]")
            print("エージェント: ", end="", flush=True)
            stream = agent.run(user_input, stream=True, session=session)
            async for chunk in stream:
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print()
```

### 動作確認

```bash
python src/agent.py
```

対話例：

```
あなた: 今四半期にGAになったAzure AI関連の更新を3件教えて
エージェント: 1. Azure AI Foundry のXX機能（YYYY-MM-DD GA）... [URL]
              2. ...

あなた: その1番目の更新の詳細をもっと教えて
エージェント: （前ターンを参照して掘り下げる）
```

文脈が引き継がれていればセッション成功です。

---

## 2-4. ★Stretch: 構造化出力でレポート化

「自然言語の応答」ではなく **Pydantic モデル** で受け取って、後段の処理（メール作成、Slack 投稿、CI 評価器など）に流したいケース用。

Copilot Chat で：

````
src/report.py を新規作成してください。
- src/agent.py と同じエージェント構成（MRC MCP 使用）
- あなたは Microsoft 365 と Azure のリリースレポートを Pydantic で構造化出力してください
- トップレベルは period(str) / summary(str) / items(list)
- items の各要素は product / title / status / released_at / url / summary
- 質問は「直近 GA になった主要な Microsoft 365 / Azure 更新を 5 件、構造化して」
- 結果は data/report_<日付>.json に保存
````

実行（`mkdir -p` は PowerShell でも bash でも動作）：

```bash
mkdir -p data
python src/report.py
```

> Copilot は [skills/references/advanced.md の「ファイルに保存するパターン」](../skills/references/advanced.md#ファイルに保存するパターン) から、`options={"response_format": MyModel}` と `response.value` を `try/except ValidationError` で受けるパターン、`data/<ネーミング>_<日付>.json` という出力先を自動で使ってくれます。構造化出力は **CI/CD の評価器が読みやすい** という大きな利点があります。Lab 4 / Lab 5 で再活用します。

---

## 2-5. ★Stretch: Web 検索を併用

MCP には Microsoft 365 / Azure Updates / Roadmap / Learn の情報があるので大半は足りますが、**個別ブログ記事や StackOverflow を引きたい**場合は Foundry の Hosted Web Search を追加できます（**Azure OpenAI モデルのみ動作**）。

Copilot Chat で：

```
src/agent.py の tools に FoundryChatClient.get_web_search_tool() を追加し、
instructions に「MCP で取得した一次情報に加えて、補足や関連ブログを探すときは
Web 検索を使ってよい」と追記してください。
```

---

## まとめ

- **Copilot + Skill** の組み合わせで、SDK の細かい API を覚えなくても正しいコードが書ける
- `Agent(client=FoundryChatClient(...))` パターンが MAF + Foundry の基本形
- 連続して機能拡張（セッション、ストリーミング、構造化出力）するときも、**自然言語で指示** すれば skill が裏で適切なリファレンスを引いてくれる
- できあがった `src/agent.py` は次の Lab 3 でほぼそのまま Foundry の Hosted Agent にデプロイします

---

次へ → [Lab 3: Hosted Agent を Foundry へデプロイ](03-foundry-deploy.md)
