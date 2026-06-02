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

    def get_token(self, *scopes, **kwargs):  # noqa: D401
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
    exec(compile(code, script, "exec"), {"__name__": "__main__"})  # noqa: S102


if __name__ == "__main__":
    main()
