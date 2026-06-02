"""Lab 4 完成版: Lab 3 でデプロイした Hosted Agent を Cloud Evaluation で採点する。

Lab 5 (GitHub Actions) からも同じスクリプトをそのまま呼び出します。
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

load_dotenv()

# --- 1. Foundry project クライアントを作り、OpenAI 互換クライアントを取得 ---
project_client = AIProjectClient(
    endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    credential=AzureCliCredential(),
)
client = project_client.get_openai_client()

# --- 2. ジャッジモデルと Hosted Agent 名 ---
model_deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
agent_name = os.environ["HOSTED_AGENT_NAME"]
agent_version = os.environ.get("HOSTED_AGENT_VERSION", "1")

# --- 3. テストデータを読み込み inline content に変換 ---
inputs_path = Path("data/eval_inputs.json")
inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

# --- 4. 評価定義 (data_source_config + testing_criteria) ---
data_source_config = {
    "type": "custom",
    "item_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    "include_sample_schema": True,  # ターゲット出力を sample.* で参照するため必須
}

testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "task_adherence",
        "evaluator_name": "builtin.task_adherence",
        "initialization_parameters": {"deployment_name": model_deployment},
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_items}}",  # tool_call を含む JSON
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

# --- 5. ターゲット (Hosted Agent) + input_messages テンプレート + inline ソース ---
input_messages = {
    "type": "template",
    "template": [
        {
            "type": "message",
            "role": "developer",
            "content": {
                "type": "input_text",
                "text": "与えられた質問に出典付きで簡潔に答えてください。",
            },
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

# --- 6. ポーリング (30 × 60s = 最大 30 分) ---
final_status = "unknown"
for _ in range(30):
    status = client.evals.runs.retrieve(eval_id=eval_def.id, run_id=run.id)
    print(f"  status={status.status}")
    final_status = status.status
    if status.status in ("completed", "failed", "canceled"):
        break
    time.sleep(60)

result_url = f"https://ai.azure.com/evaluation/{eval_def.id}/runs/{run.id}"
print(f"\nResult: {result_url}")

# Lab 5 (GitHub Actions) からも参照しやすいよう、結果を JSON ファイルにも書き出す
out_dir = Path("data")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"eval_result_{ts}.json"
out_path.write_text(
    json.dumps(
        {
            "eval_id": eval_def.id,
            "run_id": run.id,
            "status": final_status,
            "result_url": result_url,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"Saved: {out_path}")
