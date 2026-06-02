# Lab 1: Agent Skills の作成と Copilot での利用

## この Lab で行うこと

- **Agent Skills**（`.instructions.md` / `SKILL.md` の仕組み）を理解する
- このリポジトリに同梱されている **MAF × Foundry 用 skill** が **Copilot に自動認識されている**ことを確認する
- skill の `description` を読み解き、**Copilot に skill を呼ばせる**簡単なテストを行う
- 自作 skill を 1 つ作って、Copilot がそれを参照することを確認する

> Lab 2 以降では、ここで動かす **Copilot + Skills** をフル活用してエージェントを作るので、ここで仕組みを腑に落としておきましょう。

---

## 1-1. Agent Skills とは（解説）

| 用語 | 意味 |
|------|------|
| **Skill** | ある領域の知識・手順をまとめた Markdown ファイル。YAML フロントマターに `name` / `description` を持つ |
| **Instruction** | ワークスペース起動時に Copilot が**自動ロード**する `.instructions.md`。`applyTo` で適用範囲を指定 |
| **トリガー** | `description` の文章で Copilot が「今このタスクに関係するか」を判断 |

**典型構成**：

```
your-repo/
├─ .github/
│  └─ instructions/
│     └─ xxx.instructions.md      ← Copilot が起動時に常時読む（ポインター）
└─ skills/
   ├─ SKILL.md                    ← 詳細な知識本体（必要時に読まれる）
   └─ references/                 ← 更に深掘り用（必要時に読まれる）
```

**動作の流れ**：

```
ワークスペース起動
  ↓
.github/instructions/*.instructions.md を Copilot がロード
  ↓
ユーザーが何か質問
  ↓
description の文章にマッチ？
  ├─ Yes → skills/SKILL.md を read_file
  │        ↓
  │        必要なら references/*.md も追加で read_file
  │        ↓
  │        skill の内容に従ってコード生成・回答
  └─ No  → 通常の回答
```

---

## 1-2. このリポジトリの skill 構成を見る

エクスプローラーで以下のファイルを開いて中身を確認してください。

### ① エントリポイント（Copilot が自動ロード）

[.github/instructions/agent-framework-azure-ai-py.instructions.md](../.github/instructions/agent-framework-azure-ai-py.instructions.md)

```yaml
---
applyTo: "**"
description: Microsoft Agent Framework Python SDK (agent-framework-foundry) で Microsoft Foundry のエージェントを作るための skill。...
---
```

**ここの 2 行が肝**：

| フィールド | 役割 |
|-----------|------|
| `applyTo: "**"` | 全ファイルで有効（常時ロード） |
| `description` | Copilot が「いつ skill 本体を読みに行くか」を判断する説明文 |

### ② 知識本体

[skills/SKILL.md](../skills/SKILL.md) ← Microsoft Foundry × MAF Python の基本パターン

### ③ 詳細リファレンス

[skills/references/](../skills/references/) ← 必要時にだけ Copilot が読みに行く

| ファイル | 内容 |
|---------|------|
| `tools.md` | Hosted Tools の使い方 |
| `threads.md` | 会話スレッド管理 |
| `mcp.md` | MCP サーバー連携（Lab 2 で重要） |
| `advanced.md` | 構造化出力・observability・evaluation |

---

## 1-3. Copilot に skill が認識されているか確認

VS Code の **Copilot Chat** を開き（`Ctrl+Alt+I`）、以下を入力：

```
このワークスペースで現在有効になっている instruction や skill を一覧で教えて
```

`agent-framework-azure-ai-py`（または `MAF × Foundry` 系の説明文を持つ skill）が含まれていればOKです。

> **トラブル時**：表示されない場合は、
> - VS Code を `Developer: Reload Window` で再読み込み
> - `.github/instructions/` 配下に `agent-framework-azure-ai-py.instructions.md` が実在するか確認
> - YAML フロントマターの `---` が前後に正しく付いているか確認

---

## 1-4. skill 発火テスト

### テスト 1: 関連質問（発火する）

Copilot Chat で：

```
Microsoft Agent Framework Python で、Foundry の Web 検索ツール付きのエージェントを最小コードで作って
```

Copilot が以下のような動作をしていれば成功：
- 応答に `FoundryChatClient` と `FoundryChatClient.get_web_search_tool()` が登場
- 関数ツールには `@tool` デコレータを使う
- 応答中に `skills/SKILL.md` や `skills/references/tools.md` への参照が出る

### テスト 2: 無関係質問（発火しない）

```
Pythonでフィボナッチ数列を返す関数を書いて
```

これは MAF と無関係なので skill は読まれないはずです。応答に SKILL.md への参照が出ないことを確認。

> **学び**：`description` が**いつ呼ぶか**の判断材料。書き方ひとつで精度が変わります。

---

## 1-5. 自作 skill を 1 つ作ってみる

社内コーディング規約を skill 化する例。`skills/` の隣に作るのではなく、**プロジェクト固有ルール**として `.github/instructions/` に直接書きます。

### 作成

**PowerShell**

```pwsh
New-Item -ItemType Directory -Force .github/instructions | Out-Null
@"
---
applyTo: "**/*.py"
description: このリポジトリ独自の Python コーディング規約。Python ファイルを編集・新規作成する際に必ず参照する。
---

# Python コーディング規約（このリポジトリ専用）

- すべての関数に **型ヒント** を付ける（戻り値も含む）
- I/O 系処理は **async def** で実装する
- 設定値は **環境変数** から `os.environ[...]` で取得し、ハードコードしない
- ログは `logging` モジュールを使い、`print` は使わない（デバッグ時を除く）
- エラーメッセージは **日本語** で書く
"@ | Set-Content .github/instructions/python-coding-style.instructions.md
```

**Bash**

```bash
mkdir -p .github/instructions
cat <<'EOF' > .github/instructions/python-coding-style.instructions.md
---
applyTo: "**/*.py"
description: このリポジトリ独自の Python コーディング規約。Python ファイルを編集・新規作成する際に必ず参照する。
---

# Python コーディング規約（このリポジトリ専用）

- すべての関数に **型ヒント** を付ける（戻り値も含む）
- I/O 系処理は **async def** で実装する
- 設定値は **環境変数** から `os.environ[...]` で取得し、ハードコードしない
- ログは `logging` モジュールを使い、`print` は使わない（デバッグ時を除く）
- エラーメッセージは **日本語** で書く
EOF
```

### 発火テスト

VS Code をリロード（`Developer: Reload Window`）した後、Copilot Chat で：

```
Pythonで「指定URLからJSONを取得して辞書で返す」関数を src/utils.py に作って
```

Copilot の生成コードが以下を満たしていれば、自作 skill が効いています：

- [ ] `async def` で書かれている
- [ ] 引数と戻り値に型ヒントがある
- [ ] `print` ではなく `logging` を使う
- [ ] エラーメッセージが日本語

> ★Stretch：`applyTo: "**/*.py"` を `"src/**/*.py"` に変えて、再生成すると `src/` 外では発火しないことを確認できます。

---

## 1-6. ★Stretch（時間があれば）: SKILL.md スタイルで深い知識を分離する

[skills/SKILL.md](../skills/SKILL.md) のように、**大量の知識**を 1 つの instruction に詰めると Copilot のコンテキストを浪費します。**ポインター instruction + 本体 SKILL.md** のパターンは「**普段は軽く、必要時だけ深く**」読ませる工夫です。

「いつポインター方式にすべきか」の目安：

| 内容 | 推奨 |
|------|------|
| 50 行以内のルール集 | `.github/instructions/*.instructions.md` に全部書く |
| 300 行を超える詳細ガイド + サブ topic | `skills/` 配下に本体を置き、ポインター instruction で参照 |

---

## まとめ

- **Skill** = YAML フロントマター付き Markdown 知識ファイル
- **Instruction** (`.github/instructions/*.instructions.md`) = Copilot が常時ロードするエントリポイント
- `description` の質が **Copilot の判断精度** に直結する
- 規模が大きい知識は **ポインター方式**（instruction + skills/SKILL.md）が効率的

---

次へ → [Lab 2: MAF で Microsoft 最新情報エージェント作成](02-maf-agent.md)
