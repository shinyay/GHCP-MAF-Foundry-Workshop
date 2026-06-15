# Lab 3 正解ファイル

このフォルダーには **`main.py` と `requirements.txt` の完成版のみ** を置いてあります。

## なぜ `azure.yaml` / `agent.manifest.json` / `infra/` を置いていないか

これらのファイルは **`azd ai agent init --deploy-mode code`** が対話的に生成します。
バージョンや回答内容（モデルバージョン、SKU、capacity、リージョン など）によって中身が変わるため、
**自分で `azd ai agent init` を回して生成したテンプレートをベースに、`main.py` だけここから差し替え** てください。

## 手順 (Lab 3 章立てに沿った最短ルート — ソースコード方式)

```bash
# リポジトリ ルートで
mkdir agent
cd agent
# 公式 Quickstart 準拠: --deploy-mode code でソースコード方式
azd ai agent init --deploy-mode code --runtime python_3_13 --entry-point main.py
# (対話モードで `azd ai agent init` だけを実行して質問に答える形でも OK)
```

スキャフォールドが生成されたら、本フォルダーの `agent/main.py` と `requirements.txt` で上書き：

PowerShell:

```pwsh
Copy-Item solutions/lab3/agent/main.py         agent/main.py         -Force
Copy-Item solutions/lab3/agent/requirements.txt agent/requirements.txt -Force
```

Bash:

```bash
cp solutions/lab3/agent/main.py         agent/main.py
cp solutions/lab3/agent/requirements.txt agent/requirements.txt
```

> `azd ai agent init` が生成する `agent.manifest.json` の `env` セクションが `FOUNDRY_MODEL` を含んでいることを確認してください。最新の Quickstart テンプレートは既定で `FOUNDRY_MODEL` を出力します。`AZURE_AI_MODEL_DEPLOYMENT_NAME` だけしか書かれていない場合は `FOUNDRY_MODEL` への mapping を追記してください。

あとは Lab 3 のとおり：

```bash
cd agent
azd up                                  # provision + deploy を 1 コマンドで
azd ai agent invoke "今四半期に GA になった Azure AI 関連の更新を 3 件教えて"
```

> **コンテナ方式 (Stretch)**: `azd ai agent init --deploy-mode container` を選ぶと Dockerfile + Bicep 一式が生成され、`azd provision` → `azd deploy` の 2 段階デプロイになります。ソースコード方式より柔軟ですが、追加権限や事前ビルドが必要です。
