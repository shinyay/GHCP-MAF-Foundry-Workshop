# Lab 4: トレース確認と Cloud Evaluation

## この Lab で行うこと

- Lab 3 でデプロイした Hosted Agent の **トレース** を Foundry ポータルと Application Insights で確認する
- **Lab 3 でデプロイした Hosted Agent をターゲット**に、手元の PC から **Foundry SDK (`azure-ai-projects`)** を使って評価ジョブを走らせる
- 組み込み評価器（`builtin.task_adherence`, `builtin.tool_call_accuracy`, `builtin.intent_resolution`, `builtin.coherence`）でエージェント品質を採点する
- ここで作る `src/evaluate.py` は、**Lab 5 の CI/CD パイプラインからそのまま再利用**します

> Lab 3 完了済み（Hosted Agent が `azd ai agent show` で Active）が前提です。ローカルエージェント (Lab 2) のトレースは本ワークショップでは扱いません (Hosted Agent が自動で OpenTelemetry を送信してくれるため)。

---

## 4-1. Foundry ポータルでトレースを見る

Hosted Agent は **デフォルトで OpenTelemetry トレースを Foundry に送信** します。あなたはコード変更も追加設定も不要です。

### 4-1-1. トラフィックを発生させる

```bash
# agent/ ディレクトリで
azd ai agent invoke "Azure Functions の最新の機能更新を 5 件、新しい順に教えて"
azd ai agent invoke "Microsoft Copilot Studio で今四半期に GA になった機能は？"
azd ai agent invoke "Defender for Cloud で Retiring になる機能を教えて"
```

### 4-1-2. Foundry ポータルで確認

1. [https://ai.azure.com](https://ai.azure.com) を開く
2. 該当プロジェクトを選択
3. 左メニュー **Observability** > **Traces**
4. 直近のリクエストが時系列で表示される（**90 日間保持**）
5. 1 件クリック → スパン階層が展開

確認ポイント：

- ルート span: `agent.run` (ストリーミング時も同名。内部で `ResponseStream` を返す)
- 子 span: LLM 呼び出し (`chat.completions.create` 等) のレイテンシとトークン数
- 子 span: ツール呼び出し (`search_microsoft_release_messages` 等) の入出力
- エラー時は span が赤くなり stack trace が見える

### 4-1-3. Application Insights でも確認できる

`azd provision` で作られた Application Insights にも同じデータが流れています。Azure ポータル > 該当リソースグループ > Application Insights > **Transaction search** で SQL 風クエリも可。

```kusto
traces
| where timestamp > ago(1h)
| where operation_Name contains "agent"
| project timestamp, message, severityLevel
| order by timestamp desc
```

---

## 4-2. Cloud Evaluation：Lab 3 の Hosted Agent を SDK で評価

Foundry の **Cloud Evaluation** は、サーバー側で評価ジョブを走らせ結果を保存します。この Lab では、**ローカルの PC から `azure-ai-projects` SDK を叩いて** 、Lab 3 でデプロイした Hosted Agent をターゲットにした評価 run を作ります。同じスクリプトを Lab 5 で GitHub Actions からも走らせます。

```
あなたの PC                    Foundry サービス
─────────────────────────────────────────────────────────────────────────────
src/evaluate.py                  ┌────────────────────────────────┐
  ├─ client.evals.create()    ─→    │ Evaluation definition        │
  └─ client.evals.runs.create() ─→  │ Run → azure_ai_agent target │
                                   │ │└→ Lab 3 の Hosted Agent      │
                                   │  └→ builtin 評価器で採点      │
                                   └────────────────────────────────┘
```

### 4-2-1. パッケージ確認

```bash
pip install "azure-ai-projects>=2.2.0"
```

### 4-2-2. テストデータを用意

> このファイルは **リポジトリ ルートの `data/eval_inputs.json` として最初から配置済み** です。中身を変えたい場合のみ編集してください。スクラッチで書く練習をしたい場合は、いったん削除してから次の内容で再作成してもかまいません。

`data/eval_inputs.json`（**JSONL ではなく通常の JSON 配列**。スクリプト側で 1 件ずつ展開します）：

```json
[
  { "query": "今四半期に GA になった Azure AI 関連の更新を 3 件教えて" },
  { "query": "Microsoft 365 Copilot のロードマップで Outlook 関連を 5 件" },
  { "query": "Defender for Cloud で 90 日以内に Retiring になる機能" },
  { "query": "Microsoft Fabric のドキュメントで Lakehouse のベスト プラクティスは？" }
]
```

### 4-2-3. 評価スクリプトを書く

Copilot Chat で：

````
src/evaluate.py を新規作成してください。

要件:
- Microsoft Foundry の Cloud Evaluation を作成し、
  Lab 3 でデプロイした Hosted Agent をターゲットに評価する
- 評価器は task_adherence / tool_call_accuracy / intent_resolution / coherence
- テストデータは data/eval_inputs.json から読む
- run 完了までポーリングし、最後に Foundry の評価結果 URL を表示する
- このスクリプトは Lab 5 の CI/CD からも同じものをそのまま使うので、
  Hosted Agent の名前とバージョンは環境変数から読むこと
````

Copilot は [skills/SKILL.md](../skills/SKILL.md) と [skills/references/advanced.md の Evaluation セクション](../skills/references/advanced.md#evaluation--foundry-cloud-evaluation) を参照し、以下を自動で補完してくれます：

- `azure-ai-projects` の `AIProjectClient` → `get_openai_client()` で client を取得
- `data_source_config` に `"include_sample_schema": True` を必ず付ける
- 各評価器を `{"type": "azure_ai_evaluator", "evaluator_name": "builtin.xxx", "initialization_parameters": {"deployment_name": ...}, "data_mapping": {...}}` の正しい 5 点セットで構成
- `tool_call_accuracy` / `task_adherence` は `sample.output_items`、その他は `sample.output_text` を `data_mapping.response` に ([advanced.md の振り分け表](../skills/references/advanced.md#data_mappingresponse-の評価器ごとの推奨値))
- `data_source.type = "azure_ai_target_completions"` + `input_messages` テンプレート + `target.type = "azure_ai_agent"`
- run をポーリングして結果 URL を表示するパターン ([advanced.md のポーリング例](../skills/references/advanced.md#完了までポーリングして結果-url-を表示するパターン))
- Hosted Agent の名前とバージョンは環境変数から読む

完成イメージ：

```python
import json
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

load_dotenv()

# 1. Foundry project クライアントを作り、OpenAI 互換クライアントを取得
project_client = AIProjectClient(
    endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    credential=AzureCliCredential(),
)
client = project_client.get_openai_client()

# 2. ジャッジモデルと Hosted Agent 名
model_deployment = os.environ["FOUNDRY_MODEL"]
agent_name = os.environ["HOSTED_AGENT_NAME"]
agent_version = os.environ.get("HOSTED_AGENT_VERSION", "1")

# 3. テストデータを読み込み inline content に変換
inputs = json.load(open("data/eval_inputs.json", encoding="utf-8"))
ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

# 4. 評価定義 (data_source_config + testing_criteria)
data_source_config = {
    "type": "custom",
    "item_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    "include_sample_schema": True,   # ターゲット出力を sample.* で参照するため必須
}

testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "task_adherence",
        "evaluator_name": "builtin.task_adherence",
        "initialization_parameters": {"deployment_name": model_deployment},
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_items}}",   # tool_call を含む JSON
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "tool_call_accuracy",
        "evaluator_name": "builtin.tool_call_accuracy",
        "initialization_parameters": {"deployment_name": model_deployment},
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_items}}",
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "intent_resolution",
        "evaluator_name": "builtin.intent_resolution",
        "initialization_parameters": {"deployment_name": model_deployment},
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "coherence",
        "evaluator_name": "builtin.coherence",
        "initialization_parameters": {"deployment_name": model_deployment},
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
]

eval_def = client.evals.create(
    name=f"ms-updates-eval-{ts}",
    data_source_config=data_source_config,
    testing_criteria=testing_criteria,
)
print(f"Eval definition: {eval_def.id}")

# 5. ターゲット (Hosted Agent) + input_messages テンプレート + inline ソース
input_messages = {
    "type": "template",
    "template": [
        {
            "type": "message",
            "role": "developer",
            "content": {"type": "input_text", "text": "与えられた質問に出典付きで簡潔に答えてください。"},
        },
        {
            "type": "message",
            "role": "user",
            "content": {"type": "input_text", "text": "{{item.query}}"},
        },
    ],
}

data_source = {
    "type": "azure_ai_target_completions",
    "source": {
        "type": "file_content",
        "content": [{"item": {"query": q["query"]}} for q in inputs],
    },
    "input_messages": input_messages,
    "target": {
        "type": "azure_ai_agent",
        "name": agent_name,
        "version": agent_version,
    },
}

run = client.evals.runs.create(
    eval_id=eval_def.id,
    name=f"run-{ts}",
    data_source=data_source,
)
print(f"Run started: {run.id}")

# 6. ポーリング
for _ in range(30):
    status = client.evals.runs.retrieve(eval_id=eval_def.id, run_id=run.id)
    print(f"  status={status.status}")
    if status.status in ("completed", "failed", "canceled"):
        break
    time.sleep(60)

print(f"\nResult: https://ai.azure.com/evaluation/{eval_def.id}/runs/{run.id}")
```

> **重要ポイント**
> - `data_source_config` には `include_sample_schema: True` を必ず指定する（これがないと `sample.output_*` を `data_mapping` で参照できない）
> - `testing_criteria` の要素は **`type: "azure_ai_evaluator"`** で、組み込み評価器名は `evaluator_name: "builtin.xxx"` に書く
> - **`input_messages` テンプレート**を渡し、その中で `{{item.query}}` を `user` メッセージに展開する
> - `tool_call_accuracy` / `task_adherence` は `{{sample.output_items}}`（tool_call を含む構造化 JSON）、`coherence` / `intent_resolution` は `{{sample.output_text}}`（プレーンテキスト）を使う
> - run status は `succeeded` ではなく **`completed`** で終了する（公式 enum）

### 4-2-4. 環境変数追加

`.env` に追記：

```env
HOSTED_AGENT_NAME=ms-updates-agent
HOSTED_AGENT_VERSION=1
```

### 4-2-5. 実行

```bash
python src/evaluate.py
```

5〜15 分で完了。表示された URL を開くと、評価器ごとのスコアと各サンプルの判定理由が表示されます。

### 4-2-6. Foundry ポータルで結果確認

1. ポータル > **Evaluation** > 該当 run
2. **Metrics** タブ: 評価器ごとの平均スコア
3. **Items** タブ: サンプル毎の入出力と各評価器の判定 / 理由

### 評価器のヒント

| 評価器 | 何を見る |
|---|---|
| `builtin.task_adherence` | エージェントが指示通りのタスクを完了したか |
| `builtin.tool_call_accuracy` | 適切なツールを適切な引数で呼んだか |
| `builtin.intent_resolution` | ユーザー意図を正しく解釈したか |
| `builtin.coherence` | 応答が論理的に一貫しているか |
| `builtin.relevance` | 質問への関連性 |
| `builtin.groundedness` | 取得した情報に基づいているか（hallucination 検出） |
| `builtin.fluency` | 自然な言語表現か |

---

## 4-3. ★Stretch: コンテンツ安全性評価

`builtin.violence` / `builtin.self_harm` / `builtin.hate_unfairness` / `builtin.sexual` を `testing_criteria` に追加すると、生成内容の有害性をスキャンできます。コンテンツ安全性評価器は `initialization_parameters` 不要 (Foundry がサービスで判定) です。

```python
safety_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "violence",
        "evaluator_name": "builtin.violence",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "self_harm",
        "evaluator_name": "builtin.self_harm",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "hate_unfairness",
        "evaluator_name": "builtin.hate_unfairness",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "sexual",
        "evaluator_name": "builtin.sexual",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
]

testing_criteria = testing_criteria + safety_criteria   # 4-2-3 のリストに追加
```

---

## 4-4. ★Stretch: 評価結果を CI に流す

Lab 5 で、PR ごとに自動評価し結果を PR コメントに投稿するワークフローを作ります。**この Lab で書いた `src/evaluate.py` がそのまま CI でも召される**ため、評価用コードを重複して書く必要はありません。

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| Hosted Agent のトレースが Foundry ポータルに出ない | 90 秒〜数分の遅延あり / `azd ai agent invoke` で何回かリクエストを送ってから見てみる |
| `client.evals` で AttributeError | `AIProjectClient` を直接使わず `project_client.get_openai_client()` 経由で client を取る |
| `Unknown evaluator type` 系エラー | `testing_criteria[i].type` は **`"azure_ai_evaluator"`** にして、組み込み名は `evaluator_name: "builtin.xxx"` に書く |
| `sample.output_text を data_mapping で解決できない` 系エラー | `data_source_config` に `"include_sample_schema": True` を追加 |
| Cloud Eval が `failed` で終わる | エージェントが `Active` か / `HOSTED_AGENT_NAME` / `HOSTED_AGENT_VERSION` / `input_messages` の有無を確認 |
| `builtin.tool_call_accuracy` が常に低い | `instructions` でツールの使い方を具体的に書く |
| 評価料金が心配 | サンプル件数を 3〜5 に絞る、4-2-3 で件数を `inputs[:3]` に |

---

## チェックリスト

- [ ] `azd ai agent invoke` 3 回以上叩いて Foundry > Observability > Traces にスパンが出る
- [ ] `data/eval_inputs.json` 作成
- [ ] `src/evaluate.py` 作成（Lab 5 でそのまま再利用するので、ローカルで走らせておくことが重要）
- [ ] `python src/evaluate.py` で run id 取得・ステータス `completed`
- [ ] Foundry ポータル > Evaluation で各評価器のスコア確認

---

次へ → [Lab 5: GitHub Actions で CI/CD 化](05-cicd.md)
