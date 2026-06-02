# Lab 3 正解ファイル

このフォルダーには **`main.py` と `requirements.txt` の完成版のみ** を置いてあります。

## なぜ `azure.yaml` / `agent.manifest.yaml` / `infra/` を置いていないか

これらのファイルは **`azd ai agent init`** が対話的に生成します。
バージョンや回答内容（モデルバージョン、SKU、capacity、リージョン など）によって中身が変わるため、
**自分で `azd ai agent init` を回して生成したテンプレートをベースに、`main.py` だけここから差し替え** てください。

## 手順 (Lab 3 章立てに沿った最短ルート)

```bash
# リポジトリ ルートで
mkdir agent
cd agent
azd ai agent init        # docs/03 の 3-2 のとおり回答する
```

スキャフォールドが生成されたら、本フォルダーの `agent/main.py` で上書き：

PowerShell:

```pwsh
# リポジトリ ルートから
Copy-Item solutions/lab3/agent/main.py agent/main.py -Force
# 必要なら requirements.txt も追記内容を反映
```

Bash:

```bash
cp solutions/lab3/agent/main.py agent/main.py
```

あとは Lab 3 のとおり：

```bash
cd agent
azd provision
azd deploy
azd ai agent invoke "今四半期に GA になった Azure AI 関連の更新を 3 件教えて"
```
