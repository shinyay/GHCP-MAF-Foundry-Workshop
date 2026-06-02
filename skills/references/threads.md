# AgentSession — 会話の継続管理 (Python)

> 主軸 skill: [../SKILL.md](../SKILL.md)

複数ターンの会話を保持するには `AgentSession` を使います。

---

## 基本

```python
session = agent.create_session()

r1 = await agent.run("私の名前は花子です。", session=session)
print(r1.text)

r2 = await agent.run("私の名前を覚えていますか？", session=session)
print(r2.text)  # → 「はい、花子さんですね」
```

`session` を渡さないと、各 `agent.run()` は独立した会話として扱われます。

---

## ストリーミングと組み合わせる

`agent.run(..., stream=True)` は **`ResponseStream`** を返します。これを `async for chunk in stream:` で回して下さい。旧 `agent.run_stream(...)` API は 1.0.0 で削除されました。

```python
session = agent.create_session()

stream = agent.run("自己紹介して", stream=True, session=session)
async for chunk in stream:
    if chunk.text:
        print(chunk.text, end="", flush=True)
print()

stream = agent.run("もう一度短く言って", stream=True, session=session)
async for chunk in stream:
    if chunk.text:
        print(chunk.text, end="", flush=True)
print()
```

---

## 対話モードのループ実装パターン

ユーザーが「対話モードにして」「会話継続できるようにして」と書いた場合は、以下の `input()` ループを既定として生成してください。

- 1 つの `session` を作って `while True` の中で使い回す
- 終了ワード `quit` / `exit` / `終了` のいずれかが入力されたら break
- ストリーミング応答もあわせて指定された場合は **`agent.run(prompt, stream=True, session=session)`** を `async for chunk` で回す (旧 `agent.run_stream` は 1.0.0 で削除)
- 必要に応じて毎ターンの末尾で `session.conversation_id` を表示すると、会話の継続を確認しやすい

```python
session = agent.create_session()
print("Agent との対話を開始します (quit / exit / 終了 で終了)")

while True:
    user_input = input("\nYou: ").strip()
    if user_input.lower() in {"quit", "exit", "終了"}:
        break

    print("Agent: ", end="", flush=True)
    stream = agent.run(user_input, stream=True, session=session)
    async for chunk in stream:
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()
    # 会話の継続を確認したいとき:
    # print(f"  [conversation_id={session.conversation_id}]")
```

`session` をループの外で 1 度だけ作るのがポイントです。毎ターン作り直すと履歴がリセットされます。

---

## 会話 ID の取得・再開

Foundry の Responses API では、サーバー側で会話状態を保持する `conversation_id` がレスポンスに付きます。

```python
session = agent.create_session()
r1 = await agent.run("こんにちは", session=session)

print(r1.conversation_id)  # → "conv_xxxxx" など
```

再接続したい場合は、`AgentSession(conversation_id="conv_xxxxx")` のように既存 ID を渡すことで会話を引き継げます。

---

## ローカル履歴 vs サーバー保持

`Agent` / `FoundryChatClient` には会話履歴の管理方針を切り替えるオプションがあります。

| `default_options` | 動作 |
|---|---|
| `{"store": True}` (デフォルト) | Foundry サーバー側で会話履歴を保持 |
| `{"store": False}` | アプリ側で履歴を渡す。Hosted Agent では推奨 |

```python
agent = Agent(
    client=FoundryChatClient(...),
    instructions="...",
    default_options={"store": False},
)
```

Hosted Agent では、Foundry のエージェント側ですでに `conversation` を管理しているため、`store=False` にして重複保存を避けます。

---

## 会話の前提情報を最初に入れる

```python
session = agent.create_session()

# システムメッセージ的に前提条件を投入
await agent.run(
    "以降の会話では、私のことを『先生』と呼んでください。",
    session=session,
)

r = await agent.run("今日はよろしくお願いします", session=session)
print(r.text)  # → 「先生、こんにちは…」
```

---

## 複数エージェント間で履歴を共有する

`AgentSession` は単一エージェントの会話を表します。複数エージェントで履歴を共有する場合は、上流のメッセージを手動で渡すか、workflow / orchestration 機能を使います。詳細は [advanced.md](advanced.md) を参照。

---

## 落とし穴

1. **`session` を毎ターン作り直す** → 履歴が消える。1 つの会話につき 1 つの `session` を使い回す。
2. **Hosted Agent で `store=True` のまま使う** → Foundry 側と SDK 側の二重保存になる。`store=False` を明示。
3. **長すぎる履歴** → コンテキスト溢れ。長期会話では要約戦略 (summary memory) を別途実装する。
