# Lab 5: GitHub Actions for CI/CD

## この Lab で行うこと

1. **完成版の PR Check ワークフローと CI 用ラッパーを fork したリポジトリにコピペで配置**
   - PR Check: pytest + Lab 4 の `src/evaluate.py` を `ci/run_evaluate.py` 経由で呼んで Cloud Evaluation → 結果を PR にコメント
2. **自分のアクセス トークンを 1 行で発行して GitHub Secret に登録**（`az account get-access-token` + `gh secret set`。Entra アプリ/SP/UAMI 作成権限不要、自分の RBAC だけで完結。トークンは 60-90 分有効なので Lab 5 を走らせる直前に 1 回到達すれば OK）
3. **Lab 2 の `src/agent.py` に Microsoft Learn MCP を 1 ツール追加** し、ブランチを push & PR
4. PR で評価結果コメントを確認 → main にマージ後、デプロイはローカルで `azd deploy` を手動実行 (5-5 参照)

> Lab 0 でリポジトリを **自分の GitHub に fork 済み** (`git remote -v` で `origin` が自分の fork)、Lab 3 で Hosted Agent デプロイ済み、Lab 4 の `src/evaluate.py` がローカルで動くこと、が前提です。

---

## 5-1. 自分のアクセス トークンを Secret に登録する

GitHub Actions から Foundry に認証するために、`az account get-access-token` で自分の bearer トークンを一時発行し、GitHub Secret に上げるだけです。

> **なぜトークン方式なのか**
>
> SP / Entra アプリ作成には Entra ディレクトリ権限 (`Application.Create`) が、UAMI 作成にも RG への Contributor が必要ですが、社内テナントポリシーで参加者にこれらが付与されていないケースが多いです。さらにここでは `az login` 済みの本人アカウントがもつ RBAC (Foundry Project Manager ・ Cognitive Services User 等) をそのまま使いたいため、`az` で発行した **自分の bearer トークンをそのまま Secret として使う** のが最もシンプルです。
>
> トークンの有効期限は 60-90 分で、本 Lab 1 回を回せるのに十分です。失効したら 5-1-1 のコマンドをもう 1 回走らせて Secret を上書きするだけです。
>
> 💡 **本番運用での推奨**
>
> ユーザートークン方式はトークン失効ごとに手動更新が必要で、もちろん本番長期運用には不向きです。Entra アプリ管理チームと連携できるなら、本番では **Entra App + Federated Credentials (OIDC)** を使って長期シークレットが不要な構成にするのが推奨されます。

### 5-1-1. トークン発行 + GitHub Secrets / Variables 登録

`gh` CLI で 1 ショットで設定できます。`gh auth login` 済み ・ `origin` が自分の fork であることを確認して、リポジトリ ルートで実行してください。

**PowerShell**

```pwsh
# 1. トークン発行 (Foundry データプレーンの主 audience、有効期限 60-90 分)
$token = az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv

# 2. Secret に登録 (古いトークンは上書きされる)
gh secret set AZURE_AI_AUTH_TOKEN --body $token

# 3. ワークフローが使う Variables (公開されても良い値。.env / Lab 4 で設定したものをそのまま)
gh variable set FOUNDRY_PROJECT_ENDPOINT --body "<Lab 0 で取得した endpoint>"
gh variable set FOUNDRY_MODEL            --body "gpt-4.1-mini"
gh variable set HOSTED_AGENT_NAME        --body "ms-updates-agent"
gh variable set HOSTED_AGENT_VERSION     --body "1"
```

**Bash**

```bash
# 1. トークン発行
TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv)

# 2. Secret に登録
gh secret set AZURE_AI_AUTH_TOKEN --body "$TOKEN"

# 3. Variables
gh variable set FOUNDRY_PROJECT_ENDPOINT --body "<Lab 0 で取得した endpoint>"
gh variable set FOUNDRY_MODEL            --body "gpt-4.1-mini"
gh variable set HOSTED_AGENT_NAME        --body "ms-updates-agent"
gh variable set HOSTED_AGENT_VERSION     --body "1"
```

> ブラウザ操作派の場合: **Settings** > **Secrets and variables** > **Actions** で `AZURE_AI_AUTH_TOKEN` を Secret、残り 4 つを Variables として手動追加。

### 5-1-2. トークンが失効したときのリフレッシュ

Workflow が `AADSTS70043: The refresh token has expired` / `401 Unauthorized` で落ちたら、`az login` し直してから 5-1-1 の 1・2 をもう一度走らせ、Actions タブで **Re-run jobs** だけで OK です。

```pwsh
gh secret set AZURE_AI_AUTH_TOKEN --body (az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv)
```

---

## 5-2. PR Check ワークフローと CI 用ラッパーを配置

2 つのファイルをコピペで作るだけです。

```bash
mkdir -p .github/workflows ci
```

### `ci/run_evaluate.py`

GitHub Actions では `az login` ができないため、`src/evaluate.py` の `AzureCliCredential()` を **その場だけ `AZURE_AI_AUTH_TOKEN`を返す軽量クラスに差し替える** 軽いラッパーを使います。こうしておけば Lab 4 で作った `src/evaluate.py` は一行も手を入れずにそのまま CI で走ります。

```python
"""GitHub Actions 用のラッパー: src/evaluate.py を無改変で実行する。

ワークショップ参加者は Entra ディレクトリ権限 (App / SP 作成) を持っていないため、
GitHub Actions から Foundry へ認証する手段として **自分のユーザー アクセス トークン** を
GitHub Secret 経由で渡す方式を採る。

事前にローカルで以下を 1 回流す (有効期限 60-90 分):

    az login
    gh secret set AZURE_AI_AUTH_TOKEN --body "$(az account get-access-token \
        --scope https://ai.azure.com/.default --query accessToken -o tsv)"

ワークフローはこのスクリプトに `AZURE_AI_AUTH_TOKEN` を env で渡すだけで、
評価本体 (src/evaluate.py) には一切手を入れない。
"""

from __future__ import annotations

import os
import sys
import time

import azure.identity
from azure.core.credentials import AccessToken


class _StaticTokenCredential:
    """env から渡されたトークンを返すだけの最小 TokenCredential 互換クラス。"""

    def __init__(self, token: str, lifetime_seconds: int = 3600) -> None:
        self._token = token
        self._expires_on = int(time.time()) + lifetime_seconds

    def get_token(self, *scopes, **kwargs):
        return AccessToken(self._token, self._expires_on)


def _install_credential() -> None:
    token = os.environ.get("AZURE_AI_AUTH_TOKEN")
    if not token:
        sys.stderr.write(
            "ERROR: AZURE_AI_AUTH_TOKEN が未設定です。ワークフローの env から渡してください。\n"
        )
        sys.exit(1)
    # src/evaluate.py が AzureCliCredential() を呼んでいる箇所をそっくり差し替える
    azure.identity.AzureCliCredential = (
        lambda *args, **kwargs: _StaticTokenCredential(token)
    )


def main() -> None:
    _install_credential()
    script = os.path.join("src", "evaluate.py")
    with open(script, encoding="utf-8") as fp:
        code = fp.read()
    exec(compile(code, script, "exec"), {"__name__": "__main__"})


if __name__ == "__main__":
    main()
```

### `.github/workflows/pr-check.yml`

```yaml
name: PR Check
on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install agent-framework-foundry aiohttp
          pip install azure-identity python-dotenv pytest "azure-ai-projects>=2.2.0"
      - name: Test
        run: pytest tests/ -v || true

  evaluate:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install agent-framework-foundry aiohttp
          pip install azure-identity python-dotenv "azure-ai-projects>=2.2.0"
      - name: Run Cloud Evaluation
        id: eval
        env:
          # 5-1 で発行した自分のユーザー アクセス トークン (60-90 分有効)
          # ci/run_evaluate.py がこれを AzureCliCredential の代わりに使う
          AZURE_AI_AUTH_TOKEN: ${{ secrets.AZURE_AI_AUTH_TOKEN }}
          FOUNDRY_PROJECT_ENDPOINT: ${{ vars.FOUNDRY_PROJECT_ENDPOINT }}
          FOUNDRY_MODEL: ${{ vars.FOUNDRY_MODEL }}
          HOSTED_AGENT_NAME: ${{ vars.HOSTED_AGENT_NAME }}
          HOSTED_AGENT_VERSION: ${{ vars.HOSTED_AGENT_VERSION }}
        run: |
          python ci/run_evaluate.py | tee eval.log
          RUN_ID=$(grep "Run started:" eval.log | awk '{print $3}')
          URL=$(grep "^Result:"      eval.log | awk '{print $2}')
          echo "run_id=${RUN_ID}" >> $GITHUB_OUTPUT
          echo "url=${URL}"       >> $GITHUB_OUTPUT
      - uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## Cloud Evaluation 結果\n- Run ID: \`${{ steps.eval.outputs.run_id }}\`\n- Result: ${{ steps.eval.outputs.url }}`,
            })
```

### 5-2-1. ワークフローを main に push

```bash
git checkout main
# CI の evaluate ジョブが実行する評価スクリプト本体 (Lab 4 で作った src/evaluate.py) も
# 一緒に main へ載せる。これが無いと CI 側で `FileNotFoundError: src/evaluate.py` になる。
git add .github/workflows/pr-check.yml ci/run_evaluate.py src/evaluate.py
git commit -m "ci: add PR check workflow + evaluation script"
git push origin main
```

main への push では何も起動しません (PR Check は `pull_request` トリガのみ)。次の 5-3 で作る PR で初めて Actions が走ります。

> `src/evaluate.py` は Lab 4 で作成済みのものをそのまま載せます (CI はこれを無改変で実行します)。まだ手元に無い場合は Lab 4 を先に完了してください。

---

## 5-3. Lab 2 のエージェントに Microsoft Learn MCP を追加する

ここからは **「実際の開発者が機能追加 PR を出して、CI が動く」** という体験フローです。Lab 2 で作った `src/agent.py` に Microsoft Learn 公式の MCP サーバー (<https://learn.microsoft.com/api/mcp>) を 1 ツール追加します。

```bash
git checkout -b feat/add-learn-mcp
```

VS Code で Copilot Chat に：

````
src/agent.py を更新してください。
- 既存の MRC MCP に加えて、Microsoft Learn MCP (https://learn.microsoft.com/api/mcp) も使えるようにする
- instructions に「MRC で取得できない技術詳細や手順は Learn MCP で補足してよい」を追加
````

Copilot は [kb-1.8.0/api-reference/1.8.0/tools-mcp.md](../kb-1.8.0/api-reference/1.8.0/tools-mcp.md) を参照し、`async with` で複数 MCP を同時に開く形に書き換えてくれます。完成イメージ：

```python
# src/agent.py (抜粋)
INSTRUCTIONS = """あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。
必ず MRC MCP のツール（https://www.microsoft.com/releasecommunications/mcp）を使って一次情報を取得し、
回答に出典 URL を添えてください。MRC で取得できない技術詳細や手順は Microsoft Learn MCP
（https://learn.microsoft.com/api/mcp）で補足してかまいません。"""

MRC_URL   = "https://www.microsoft.com/releasecommunications/mcp"
LEARN_URL = "https://learn.microsoft.com/api/mcp"


async def main() -> None:
    async with (
        MCPStreamableHTTPTool(name="MRC",   url=MRC_URL)   as mrc_mcp,
        MCPStreamableHTTPTool(name="Learn", url=LEARN_URL) as learn_mcp,
    ):
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model=os.environ["FOUNDRY_MODEL"],
                credential=AzureCliCredential(),
            ),
            name="MSUpdatesAgent",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp, learn_mcp],
        )
        # ... 既存の対話ループはそのまま
```

Lab 3 でデプロイ済みの `agent/main.py` も同様に Learn MCP を追加します (Hosted Agent では `client.get_mcp_tool` を使う点に注意 — [kb-1.8.0/api-reference/1.8.0/tools-mcp.md の推論ルール](../kb-1.8.0/api-reference/1.8.0/tools-mcp.md#ユーザー指示からの推論ルール) で Copilot が自動判別)。

````
agent/main.py にも同じく Microsoft Learn MCP を Hosted MCP として追加してください。
````

ローカル疎通だけ確認しておきます。

```bash
python src/agent.py "Azure Functions の Premium プランの最新の機能更新と、その設定手順を Learn で確認して教えて"
```

---

## 5-4. PR を出して CI を体験する

```bash
git add src/agent.py agent/main.py
git commit -m "feat(agent): add Microsoft Learn MCP for technical follow-up"
git push -u origin feat/add-learn-mcp
gh pr create --title "feat: add Learn MCP" --body "MRC に加えて Microsoft Learn MCP を追加。Copilot Skill の推論ルールで Hosted Agent 側は get_mcp_tool に自動切替。" --base main
```

数十秒後、GitHub の **Actions** > **PR Check** が動き始めます。

1. `test` job: `pytest` (空でも fail しません)
2. `evaluate` job: `ci/run_evaluate.py` が `src/evaluate.py` を **Lab 4 と同じスクリプトのまま** 走らせて Cloud Evaluation を発行 (`AzureCliCredential()` はラッパーがユーザー トークンに差し替え)
3. 5〜15 分で評価が完了すると、PR に以下のようなコメントが自動投稿されます：

> ## Cloud Evaluation 結果
> - Run ID: `evalrun_xxxxxxxx`
> - Result: <https://ai.azure.com/evaluation/eval_xxxx/runs/evalrun_xxxx>

URL を開いて、`task_adherence` / `tool_call_accuracy` / `intent_resolution` / `coherence` の各スコアを確認してください。

> [!NOTE]
> この PR 時点での評価対象は **まだ再デプロイ前の Hosted Agent (`ms-updates-agent` version 1 = MRC のみ)** です。コードに Learn MCP を足しても、デプロイは 5-5 (マージ後) なので評価には反映されません。Learn MCP 追加の効果を測りたい場合は、5-5 で `azd deploy` した後に評価を再実行してスコアを比較してください。

---

## 5-5. main にマージしてローカルで Hosted Agent をデプロイ

PR をマージしたら、`azd deploy` は **手元で手動実行** します。Hosted Agent へのデプロイはコンテナビルドや ARM 操作を伴うため、ターゲットスコープが広い件の認証 (Contributor + Foundry Project Manager) をその都度取り直してそこに済むユーザー トークンでは不向きだからです。

```bash
git checkout main
git pull
cd agent
azd deploy            # 本人の az login セッションでデプロイ
azd ai agent show --output table   # 新 version が active であることを確認
```

> もし main マージ時点でも GitHub 上で自動デプロイさせたい場合は、本番運用と同じく **Entra App + Federated Credentials (OIDC)** を用意する必要があります。ワークショップのスコープ外なので、会社の Entra 管理者と相談してください。

---

## 5-6. ★Stretch: PR で評価スコアが閾値未満なら fail

`src/evaluate.py` の最後に以下を追記すれば、CI が品質ゲートになります。

```python
final  = client.evals.runs.retrieve(eval_id=eval_def.id, run_id=run.id)
passed = getattr(final.result_counts, "passed", 0)
total  = getattr(final.result_counts, "total",  0)
ratio  = passed / total if total else 0
print(f"pass_ratio={ratio:.2f} ({passed}/{total})")

THRESHOLD = 0.7
if ratio < THRESHOLD:
    print(f"::error::pass_ratio {ratio:.2f} < {THRESHOLD}")
    sys.exit(1)
```

`::error::` は GitHub Actions の注釈構文で、PR の Files changed タブに警告マーカーが出ます。

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `AADSTS70043` / `401 Unauthorized` / `Token has expired` | `AZURE_AI_AUTH_TOKEN` の 60-90 分有効期限切れ。5-1-2 の 1 行をもう一度走らせてから Actions の **Re-run jobs** |
| `ERROR: AZURE_AI_AUTH_TOKEN が未設定です` | Secret を登録していない。5-1-1 を実行するか、`gh secret list` で `AZURE_AI_AUTH_TOKEN` が見えるか確認 |
| `AADSTS500011: The resource principal named ... was not found` | `--scope` を `https://ai.azure.com/.default` で発行したか確認。`https://management.azure.com` など他 audience だと Foundry データプレーンが受け付けない |
| `403 Forbidden` from Foundry API | 本人の Azure アカウントに Foundry Project へのロール不足。Lab 0 で付与した **Foundry Project Manager** が生きているか Azure ポータル > Foundry resource > IAM で確認 |
| Evaluate job がタイムアウト | `src/evaluate.py` のポーリング上限 (30 分) を伸ばす |
| PR コメントが付かない | `permissions: pull-requests: write` がワークフローにあるか確認 |
| `MFA required` / `interaction_required` | ローカルで `az login --tenant <tenant-id>` し直して MFA をクリアしてからトークンを再発行 |
| GitHub 上で Secret が見える/読める | 見えません。Repo Settings > Secrets は作成者でも後から読めず、Actions のログ上でも `***` にマスクされるので安心して使ってください |

---

## チェックリスト

- [ ] 5-1 で `az account get-access-token` を発行し、`AZURE_AI_AUTH_TOKEN` Secret + 4 つの Variables を GitHub に登録
- [ ] `.github/workflows/pr-check.yml` + `ci/run_evaluate.py` を main に push
- [ ] `feat/add-learn-mcp` ブランチで `src/agent.py` + `agent/main.py` に Learn MCP を追加
- [ ] PR を作成 → Actions > PR Check が動く → PR に評価結果コメント (トークンが失効したら 5-1-2 でリフレッシュ → Re-run)
- [ ] main にマージ → ローカルで `azd deploy` を手動実行 → `azd ai agent show` で新 version が active

---

## ワークショップ終了！

これで以下が完成しました：

- Lab 0: Foundry プロジェクト + リポジトリ fork + Foundry Project Manager 割り当て
- Lab 1: GHCP に MAF × Foundry の skill を読ませて、最新 API での提案を引き出せる状態
- Lab 2: ローカル MAF エージェント（FoundryChatClient + MCP + AgentSession + ストリーミング）
- Lab 3: Foundry Hosted Agent としてデプロイ (`azd ai agent init` → `azd deploy`)
- Lab 4: Hosted Agent のトレース確認 + ローカルから Foundry SDK で走らせる Cloud Evaluation
- Lab 5: GitHub Actions で「機能追加 PR → 自動評価 → マージ後にローカルで `azd deploy`」を体験

クリーンアップしたいときは：

```bash
cd agent
azd down --purge --force
```

参考リンク：

- [Microsoft Agent Framework Python](https://github.com/microsoft/agent-framework/tree/main/python)
- [Foundry samples — hosted-agents](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents)
- [azure-ai-projects evaluations sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/evaluations)
- [Microsoft Foundry quickstart (ユーザー トークン方式の公式手順)](https://learn.microsoft.com/azure/foundry/quickstarts/get-started-code#set-environment-variables-and-get-the-code)
- [GitHub Actions から Azure に OIDC で接続 (本番推奨)](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect)
