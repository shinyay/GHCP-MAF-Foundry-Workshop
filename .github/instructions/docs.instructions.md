---
applyTo: "**/*.md"
description: ワークショップの Markdown ドキュメント (docs/、solutions/、kb-1.8.0/、README.md) を統一スタイルで書くための規約。
---

# Markdown 規約 (Agent Framework × Foundry ワークショップ)

このリポジトリの **すべての `.md` ファイル**に適用されます。Lab 手順書 (`docs/`)、模範解答の README (`solutions/`)、KB エントリ (`kb-1.8.0/`) のすべてに適用してください。

## 必須ルール

- **言語**: ワークショップ全体は日本語。コード コメント / 識別子は英語可。
- **改行**: LF (`\n`)。ファイル末尾に改行 1 つ。
- **見出しレベル**: ファイル冒頭は `# タイトル` 1 つだけ。`##` から階層化する。
- **リスト**: 箇条書きは `-` を使う (`*` や `+` は使わない)。
- **強調**: 用語や強調は `**` (bold)、コードや CLI コマンド断片は バッククォート 1 つ。

## コードブロック

- フェンスには **必ず言語タグを付ける**。

  ````markdown
  ```python
  agent = client.as_agent(instructions="...")
  ```

  ```bash
  azd ai agent init --deploy-mode code
  ```

  ```text
  FOUNDRY_MODEL=gpt-4.1-mini
  ```
  ````

- 言語タグの選択肢: `python` / `bash` / `text` / `json` / `yaml` / `bicep` / `powershell` / `mermaid`。
- PowerShell コマンドは `powershell`、Bash / azd / az / gh は `bash` (Linux 前提のため)。

## リンク

- リポジトリ内リンクは **repo-relative** で書く (`./` 起点ではなく、ファイル位置からの相対パス)。

  ```markdown
  [`kb-1.8.0/README.md`](../../kb-1.8.0/README.md)
  [`solutions/lab2/src/agent.py`](../../solutions/lab2/src/agent.py)
  ```

- 外部リンク (Microsoft Learn など) は完全 URL を使う。短縮 URL (aka.ms など) は **必要な場合のみ** (リダイレクト先が変わる可能性があるため)。
- リンク文字列は **意味のあるテキスト** にする。「[ここをクリック](url)」は禁止。

## GitHub Callout (推奨)

ワークショップ手順書では GitHub 標準の callout 構文を使う:

```markdown
> [!NOTE]
> 参考情報や補足。

> [!TIP]
> 任意の便利な代替手順。

> [!IMPORTANT]
> 飛ばすと後続 Lab が動かなくなる情報。

> [!WARNING]
> やると壊れる / お金がかかる / セキュリティ事故になる情報。

> [!CAUTION]
> WARNING より重大なもの (本番への影響、データ消失)。
```

- 1 ファイルあたり callout は **最大 5 個程度** にとどめる (多用すると視覚的に煩雑)。
- `> **重要**` のような擬似 callout は使わない (GitHub UI で装飾されないため)。

## 表

- 表の列ヘッダは bold にしない (Markdown レンダラ側で太字化されるため二重)。
- 数値列は `---:` で右寄せ。

  ```markdown
  | 項目 | 値 |
  |---|---:|
  | Python | 3.11 |
  ```

## 環境変数 / コマンド表記

- 環境変数名は バッククォート: `FOUNDRY_MODEL`、`FOUNDRY_PROJECT_ENDPOINT`。
- ファイルパスは バッククォート: `solutions/lab3/`、`docs/03-foundry-deploy.md`。
- コマンドは fenced code block で言語タグ付き。インラインは バッククォート: `azd up`。

## 文書間の参照

- **Lab 手順書 (`docs/00-*.md` 〜 `docs/05-*.md`)** は Lab 番号順に進む前提で書く。前後の Lab を参照するときは番号付きで明示:

  ```markdown
  詳細は [Lab 3](./03-foundry-deploy.md) を参照。
  ```

- **模範解答 (`solutions/lab*/README.md`)** からは対応する Lab 手順書を必ず先頭でリンクする。
- **スキル (`kb-1.8.0/README.md` と `kb-1.8.0/`)** はパッケージ API の事実関係を扱う。Lab 手順を書かない (役割を混ぜない)。

## やってはいけないこと

- ❌ コードブロックに言語タグを付けない。
- ❌ `> 重要:` のような擬似 callout で済ます (GitHub Callout を使う)。
- ❌ 絶対 URL で同一リポジトリの別ファイルを参照する。
- ❌ 「v1.0.0 GA」「1.7.0」「preview 7」など、本リポジトリで指定されていないバージョン番号を書く (正規は `1.8.1+`)。
- ❌ `eastus` / `gpt-4o` / `gpt-5` 等、ワークショップ既定外のリージョン・モデル名を例示する。
- ❌ 1 段落 800 文字超え (3〜5 文で改段落)。

## 参考

- [`copilot-instructions.md`](../copilot-instructions.md) — ワークショップ全体の既定値
- [`python.instructions.md`](./python.instructions.md) — Python コードの書き方
- [GitHub Markdown alerts](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts) — `> [!NOTE]` の正式仕様
