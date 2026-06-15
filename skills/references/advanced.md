# Advanced — 構造化出力 / Observability / Evaluation / Middleware (Python)

> 主軸 skill: [../SKILL.md](../SKILL.md)

---

## 構造化出力 (Pydantic / JSON Schema)

### Pydantic モデル

```python
from pydantic import BaseModel, ValidationError
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


class WeatherReport(BaseModel):
    location: str
    temperature_c: float
    conditions: str


agent = Agent(
    client=FoundryChatClient(
        project_endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
        model="gpt-4.1-mini",
        credential=AzureCliCredential(),
    ),
    instructions="あなたは天気アシスタント。常に WeatherReport スキーマで返してください。",
)

response = await agent.run(
    "東京の今の天気を教えて",
    options={"response_format": WeatherReport},
)

try:
    report = response.value
    print(f"{report.location}: {report.temperature_c}°C ({report.conditions})")
except ValidationError as err:
    print("構造化応答ではありませんでした:", response.text)
    print(err)
```

`response.value` は **parse 成功時に Pydantic インスタンス** (失敗時は `pydantic.ValidationError`) を返します。Agent Framework Python 1.0.0 で `try_parse_value` は削除されたため、`response.value` を `try/except ValidationError` で受けるのが標準パターンです。

### default_options で全 run 共通化

```python
agent = Agent(
    client=FoundryChatClient(...),
    instructions="...",
    default_options={"response_format": WeatherReport},
)
```

### JSON Schema を直接渡す

```python
schema = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "highlights": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "highlights"],
}

response = await agent.run("ニュース要約をして", options={"response_format": schema})
data = response.value  # dict が返る
```

### ファイルに保存するパターン

「Pydantic で受け取って JSON で保存」という要件のときは、`response.value` を `try/except ValidationError` で受けて `model_dump_json` で書き出すパターンを既定としてください。ファイル名が指定されていない場合は `<出力ディレクトリ>/<ネーミング>_<YYYYMMDD-HHMMSS>.json` (例: `data/report_20260601-101530.json`) を既定にします。

```python
from datetime import datetime
from pathlib import Path
import sys

from pydantic import ValidationError

response = await agent.run(prompt, options={"response_format": MyModel})
try:
    parsed = response.value
except ValidationError as err:
    # スキーマに合わなかったときは生テキストを見せて異常終了
    print("構造化失敗:", err)
    print(response.text)
    sys.exit(1)

out_dir = Path("data")
out_dir.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
out_path = out_dir / f"report_{stamp}.json"
out_path.write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
print(f"Saved: {out_path}")
```

---

## Observability — OpenTelemetry

### 環境変数だけで構成 (推奨)

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers()  # 環境変数を読む
```

| 環境変数 | 用途 |
|---|---|
| `ENABLE_INSTRUMENTATION=true` | Agent Framework の自動計装を有効化 |
| `ENABLE_SENSITIVE_DATA=true` | プロンプト / 応答 / 関数引数を span に記録 (**本番では false**) |
| `ENABLE_CONSOLE_EXPORTERS=true` | コンソールへ trace 出力 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector / Aspire Dashboard のエンドポイント (例: `http://localhost:4317`) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` (default) / `http/protobuf` |
| `OTEL_SERVICE_NAME` | サービス名 |

### Foundry App Insights 連携

```python
import os
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import enable_instrumentation

configure_azure_monitor(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
)
enable_instrumentation()
```

`configure_azure_monitor()` は `azure-monitor-opentelemetry` パッケージの関数です。インストールは `pip install azure-monitor-opentelemetry`。この 2 つを両方呼んで初めて、Agent Framework のスパンが App Insights へ送信されます。Hosted Agent では Foundry が自動でこれを行うので、上記コードはローカル実行時だけ追加します。

### カスタム span / metric

```python
from agent_framework.observability import get_tracer, get_meter

tracer = get_tracer()
meter = get_meter()

with tracer.start_as_current_span("my_business_logic"):
    response = await agent.run("...")

counter = meter.create_counter("agent.runs")
counter.add(1, {"agent": "research"})
```

### Aspire Dashboard でローカル可視化

```bash
docker run --rm -it -d -p 18888:18888 -p 4317:18889 --name aspire-dashboard \
    mcr.microsoft.com/dotnet/aspire-dashboard:latest

export ENABLE_INSTRUMENTATION=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# あなたのアプリを実行 → http://localhost:18888 で trace 閲覧
```

### Hosted Agent の自動 observability

`azd ai agent init` で生成された Hosted Agent は **Application Insights 接続文字列がコンテナへ自動注入**され、OTEL トレースが Foundry の Observability ビューにそのまま流れます。追加コードは不要です。

---

## Evaluation — Foundry Cloud Evaluation

### インストール

```bash
pip install "azure-ai-projects>=2.2.0" azure-identity
```

### 評価の基本フロー

```python
import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

client = AIProjectClient(
    endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

# 1. データソース構成 (custom スキーマ)
data_source_config = {
    "type": "custom",
    "item_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    "include_sample_schema": True,  # エージェントの応答を含める
}

# 2. 評価器 (testing criteria)
testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "task_adherence",
        "evaluator_name": "builtin.task_adherence",
        "initialization_parameters": {
            "deployment_name": os.environ["FOUNDRY_MODEL"],
        },
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_items}}",
        },
    },
]

# 3. 評価を作成
evaluation = client.evals.create(
    name="My Agent Quality Evaluation",
    data_source_config=data_source_config,
    testing_criteria=testing_criteria,
)
```

### 主要なパラメータ (testing_criteria の中身)

| key | 意味 |
|---|---|
| `type` | 常に `"azure_ai_evaluator"` (組み込み評価器を使う場合) |
| `name` | 表示上のラベル (任意) |
| `evaluator_name` | `builtin.task_adherence` など (実装を選ぶ) |
| `initialization_parameters.deployment_name` | LLM-based 評価器で必須。コンテンツ安全性系は不要 |
| `data_mapping.query` / `response` | 評価器への入力マッピング。`{{item.*}}` が入力データ、`{{sample.output_text}}` がターゲットのテキスト出力、`{{sample.output_items}}` がツール呼出しを含む JSON |

### `data_mapping.response` の評価器ごとの推奨値

評価器によって `response` に何をマッピングすべきかは変わります。複数評価器を一括で生成するときは次の振り分けを既定としてください。

| evaluator_name | `response` にマッピングするもの |
|---|---|
| `builtin.tool_call_accuracy` | `"{{sample.output_items}}"` (ツール呼出しを含む JSON) |
| `builtin.task_adherence` | `"{{sample.output_items}}"` (タスクの達成をツール呼出し含めて見る) |
| `builtin.intent_resolution` / `builtin.coherence` / `builtin.relevance` / `builtin.fluency` など | `"{{sample.output_text}}"` |
| `builtin.groundedness` | `"{{sample.output_text}}"` + 「出典」を `context` にマッピング |

### Hosted Agent をターゲットに評価実行

```python
evaluation_run = client.evals.runs.create(
    eval_id=evaluation.id,
    name="run-1",
    data_source={
        "type": "azure_ai_target_completions",
        "source": {
            "type": "file_content",
            "content": [
                {"item": {"query": "東京の天気は？"}},
                {"item": {"query": "MAF とは？"}},
            ],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "user",
                    "content": {"type": "input_text", "text": "{{item.query}}"},
                },
            ],
        },
        "target": {
            "type": "azure_ai_agent",
            "name": "agent-framework-agent-basic-responses",  # Hosted Agent 名
            "version": "1",
        },
    },
)
print(evaluation_run.id, evaluation_run.status)
```

> **重要**: `azure_ai_target_completions` を使うときは **`input_messages` テンプレートが必須**。ここで `{{item.query}}` を user メッセージに展開し、それをターゲットに送信してから評価されます。

### 完了までポーリングして結果 URL を表示するパターン

run は非同期に走るため、`client.evals.runs.retrieve(eval_id=..., run_id=...)` をポーリングしてステータスを見ます。既定は **60 秒間隔 / 最大 30 分**。ターミナル状態は `completed` / `failed` / `canceled` の 3 つ。

```python
import time

TERMINAL = {"completed", "failed", "canceled"}
run = client.evals.runs.retrieve(eval_id=evaluation.id, run_id=evaluation_run.id)
for _ in range(30):  # 30 min cap
    if run.status in TERMINAL:
        break
    time.sleep(60)
    run = client.evals.runs.retrieve(eval_id=evaluation.id, run_id=evaluation_run.id)

print(f"status: {run.status}")
print(f"result: https://ai.azure.com/evaluation/{evaluation.id}/runs/{evaluation_run.id}")
```

CI やスクリプトで使い回すときは、ターゲットの Hosted Agent 名・バージョンを **環境変数から読む** のが一般的です (ユーザーが標準名を指定しない場合は `HOSTED_AGENT_NAME` / `HOSTED_AGENT_VERSION` を推奨)。

### 主要な data source タイプ

| タイプ | 用途 |
|---|---|
| `azure_ai_target_completions` | テストデータをエージェント (target) に流して応答を生成 + 評価 |
| `azure_ai_responses` | 既存の response ID を再評価 (regression test) |
| `azure_ai_traces` | App Insights traces から評価 (本番モニタリング) |
| `azure_ai_synthetic_data_gen_preview` | 合成データ生成 + 評価 (preview) |
| `azure_ai_red_team` | 敵対的テスト (preview) |

### 主要な builtin evaluators

| evaluator_name | 評価内容 |
|---|---|
| `builtin.task_adherence` | エージェントが指示に従っているか |
| `builtin.tool_call_accuracy` | ツール呼び出しの正確性 |
| `builtin.intent_resolution` | ユーザー意図を解決しているか |
| `builtin.coherence` | 応答の一貫性 |
| `builtin.relevance` | 質問への関連性 |
| `builtin.groundedness` | 出典 (retrieved data) に基づいているか |
| `builtin.fluency` | 流暢さ |
| `builtin.violence` / `builtin.self_harm` / etc. | コンテンツ安全性 |

公式サンプル: [sample_agent_evaluation.py](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/evaluations/sample_agent_evaluation.py)

---

## Middleware

`agent.run()` の前後にカスタム処理を挟めます (ロギング、メトリクス、PII マスキングなど)。

```python
from agent_framework import Agent, ChatClientMiddleware


class LoggingMiddleware(ChatClientMiddleware):
    async def on_request(self, ctx):
        print(f"[req] {ctx.messages}")
        await ctx.next()
        print(f"[res] {ctx.response.text[:80]}")


agent = Agent(
    client=FoundryChatClient(...),
    instructions="...",
    middleware=[LoggingMiddleware()],
)
```

---

## 落とし穴

1. **`response_format` を渡したのに `.value` が `None`** → モデルがスキーマに従えなかった。`response.text` を見て instructions を強化。
2. **`ENABLE_SENSITIVE_DATA=true` を本番で有効化** → プロンプト / 応答が trace に出る。コンプライアンス違反の温床。
3. **`configure_otel_providers()` と `configure_azure_monitor()` を二重呼び出し** → 重複 exporter が登録される。Azure Monitor に送るなら `configure_azure_monitor()` だけ、OTLP なら `configure_otel_providers()` だけを使う。両方とも `enable_instrumentation()` は必須。
4. **`testing_criteria` を `{"type": "builtin.xxx"}` だけで書く** → サービスが拒否する。とりあえず `type="azure_ai_evaluator"` + `evaluator_name="builtin.xxx"` + `data_mapping` の 3 点セットを忘れない。
5. **`azure_ai_target_completions` で `input_messages` を渡さない** → ターゲットにメッセージが届かず評価がはじまらない。
