---
name: add-cloud-evaluation
description: ワークショップで Lab 3 までにデプロイした Hosted Agent に対し、Foundry Cloud Evaluation (azure-ai-projects) を呼び出して採点するスクリプトを 1 ファイルで生成する。Lab 4 (docs/04-trace-evaluation.md) で使う。
tools: ["read", "search", "edit"]
---

# /add-cloud-evaluation

Lab 3 でデプロイ済みの Hosted Agent に対して **Foundry Cloud Evaluation** を実行する Python スクリプトを 1 ファイル生成するプロンプトです。Lab 4 ([`docs/04-trace-evaluation.md`](../../docs/04-trace-evaluation.md)) のショートカット版として使います。

## When to invoke

以下に該当するとき:

- Lab 3 が完了している (`HOSTED_AGENT_NAME` が `.env` に入っていて、Foundry 上で動いている)。
- 評価データセット (`data/eval_inputs.json` のような JSON 配列) が用意できる、または用意済み。
- Cloud Evaluation の **PromptyEvaluator (組み込み)** で task adherence / tool call accuracy / intent resolution / coherence を測りたい。

Lab 3 を終えていない状態では使えない (Hosted Agent がデプロイされていないため)。その場合は先に [`/deploy-hosted-agent`](./deploy-hosted-agent.prompt.md) を呼ぶ。

## Prerequisites

実装前に必ず確認:

- `solutions/lab4/src/evaluate.py` が **正規パターン**。新規ファイルもこの構造に合わせる。
- 依存パッケージ: `azure-ai-projects>=2.2.0`、`azure-identity`、`python-dotenv`。
- `.env` に必要な変数が揃っていること:

  ```text
  FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
  FOUNDRY_MODEL=gpt-4.1-mini             # ジャッジモデルにも使う
  HOSTED_AGENT_NAME=<Lab 3 でデプロイした名前>
  HOSTED_AGENT_VERSION=1
  ```

- 評価データ: `data/eval_inputs.json` が `[{"query": "..."}, ...]` 形式で存在。
- 詳細パターン: [`skills/references/advanced.md`](../../skills/references/advanced.md) の Evaluation セクション。

## Inputs

ユーザーに 1 ターンで確認:

| 入力 | 必須 | デフォルト / 例 |
|---|---:|---|
| **出力先ファイル** | はい | `src/evaluate.py` |
| **評価入力 JSON のパス** | はい | `data/eval_inputs.json` |
| **使う評価器** | 推測可 | `task_adherence` / `tool_call_accuracy` / `intent_resolution` / `coherence` の 4 つを既定とする |
| **ジャッジモデル** | 推測可 | 既定で `FOUNDRY_MODEL` (= `gpt-4.1-mini`) を流用 |
| **結果出力先** | 推測可 | `outputs/eval-result-<timestamp>.json` |

## Expected output

1 ファイル (`src/evaluate.py` または指定先) の生成または更新。**[`solutions/lab4/src/evaluate.py`](../../solutions/lab4/src/evaluate.py) と同じ構造** にする:

1. `dotenv.load_dotenv()` 呼び出し。
2. `AIProjectClient` + `AzureCliCredential` で接続。
3. `data/eval_inputs.json` を読み込んで inline content に変換。
4. `data_source_config` (custom + `include_sample_schema=True`)。
5. `testing_criteria` 配列に評価器を並べる (`builtin.task_adherence` 他)。
6. `client.evals.create(...)` で評価定義を作成。
7. `azure_ai_target_completions` を `data_source` に指定し、Hosted Agent をターゲットに。
8. `client.evals.runs.create(...)` を呼んでジョブ起動。
9. 完了までポーリング → 結果サマリをファイル出力。

不要な抽象化はしない (クラス化、設定ファイル分離、ロガー注入など)。**Lab 4 と同じスクリプト形式**を保つ。

## Steps

1. **既存実装を読む**: `read_file` で [`solutions/lab4/src/evaluate.py`](../../solutions/lab4/src/evaluate.py) を全文確認し、コピー元として使う。
2. **`.env.sample` を確認**: 評価に必要な環境変数がすべて参加者の `.env.sample` に含まれているか。不足があれば追記提案。
3. **`data/eval_inputs.json` の存在確認**: なければサンプル ({"query": "Azure AI Foundry の主要機能を 3 つ"} 等 3 件) を一緒に作る提案を出す。
4. **生成**: 指定された出力先ファイル名でスクリプトを生成。`solutions/lab4/src/evaluate.py` を雛形にする (コピペ + パス調整)。
5. **`outputs/` ディレクトリ作成**: 結果書き出し先がなければ作る。
6. **import の整理**: `json`, `os`, `time`, `datetime`, `pathlib.Path`, `dotenv.load_dotenv`, `azure.ai.projects.AIProjectClient`, `azure.identity.AzureCliCredential` を最小限揃える。
7. **評価器の選定**: ユーザーが指定しない限り、Lab 4 既定の 4 評価器 (`task_adherence`, `tool_call_accuracy`, `intent_resolution`, `coherence`) を入れる。
8. **タイムスタンプ**: `datetime.utcnow().strftime("%Y%m%d-%H%M%S")` を eval 名と出力ファイル名に使う。
9. **ポーリング**: `client.evals.runs.retrieve(...)` を 10 秒間隔でループ。`status` が `completed` / `failed` / `canceled` になったら終了。タイムアウト目安は 10 分。
10. **結果保存**: 完了レスポンスを `outputs/eval-result-<timestamp>.json` に整形書き出し (`json.dumps(..., indent=2, ensure_ascii=False)`)。
11. **検証コマンドを提示** (実行はしない)。

## Verification

ユーザーに案内 (実行はしない):

```bash
# 1. ローカルで動作確認
python src/evaluate.py

# 2. 完了後、結果を確認
cat outputs/eval-result-*.json | head -100
```

期待される挙動:

- 起動時に `Eval definition: <id>` `Eval run: <id>` のような ID が表示される。
- Foundry ポータルの **Evaluations** タブにジョブが出現し、進捗が表示される。
- 数分後に `status: completed` で終了し、`outputs/` に結果 JSON が書き出される。
- スコアは 0.0 〜 5.0 の範囲。`task_adherence` が 3.0 未満なら instructions の見直し候補。

トラブル時:

- `403 Forbidden` → 自分の Entra ID に **`Foundry Project Manager`** ロール (`eadc314b-6967-41eb-b9ec-2c8f0d3cd3a5`) が割当たっているか確認 ([Lab 0](../../docs/00-setup.md))。
- `HostedAgentNotFound` → `HOSTED_AGENT_NAME` の綴りと `HOSTED_AGENT_VERSION` を確認。Foundry ポータルで実在することを確認。
- `evaluator deployment_name not found` → `FOUNDRY_MODEL` が Foundry にデプロイ済みか確認。
- 評価ジョブが `failed` で終わる → Foundry ポータルの **Evaluations** からエラー詳細を確認。多くは Hosted Agent 側のランタイム エラー。

## 参考

- [`solutions/lab4/src/evaluate.py`](../../solutions/lab4/src/evaluate.py) — 完成版コピー元
- [`docs/04-trace-evaluation.md`](../../docs/04-trace-evaluation.md) — Lab 4 手順書
- [`skills/references/advanced.md`](../../skills/references/advanced.md) — Cloud Evaluation 詳細
- [`skills/SKILL.md`](../../skills/SKILL.md) — Agent Framework 全般
