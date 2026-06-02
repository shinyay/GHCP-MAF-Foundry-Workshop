# 各 Lab の正解ファイル (Solutions)

このフォルダーには、各 Lab で **Copilot Chat に書かせる予定** のコード / 設定ファイルの **完成版** を置いてあります。

## 使い方

- 困ったとき、または **Lab を急いで通したいとき** に参照してください。
- ファイルを **そのまま自分のリポジトリ ルートにコピー** すれば動きます (パス構造を維持してください)。
- まずは「自分で Copilot に指示して書かせる」を **優先** してください。Skill が機能していることを体験するのが Lab の主目的です。

## 構成

```
solutions/
├── lab0/
│   └── scripts/check_setup.py       # 0-8 の疎通テストスクリプト
├── lab2/
│   └── src/
│       ├── agent.py                  # 2-3 完成版 (MRC MCP + AgentSession + ストリーミング)
│       └── report.py                 # 2-4 ★Stretch 完成版 (Pydantic 構造化出力)
├── lab3/
│   └── agent/
│       ├── main.py                   # 3-3 完成版 (ResponsesHostServer + Hosted MCP)
│       └── requirements.txt          # 3-3 完成版
├── lab4/
│   └── src/
│       └── evaluate.py               # 4-2-3 完成版 (Cloud Evaluation スクリプト)
└── lab5/
    └── .github/
        └── workflows/
            ├── pr-check.yml          # 5-2 完成版 (PR 評価 + コメント)
            └── deploy.yml            # 5-2 完成版 (main マージで azd deploy)
```

> **データファイル** (`data/eval_inputs.json`)、**環境変数テンプレート** (`.env.sample`)、**`.gitignore`** は **リポジトリ ルートに最初から配置済み** です。Lab 0 / Lab 4 でそのまま使えるようにしてあります。

## コピー方法 (例)

PowerShell:

```pwsh
# Lab 2 の正解を取得
Copy-Item -Recurse solutions/lab2/src .
```

Bash:

```bash
# Lab 2 の正解を取得
cp -r solutions/lab2/src .
```
