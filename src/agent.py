"""MSUpdatesAgent — Microsoft 365 / Azure の最新リリース情報を MRC MCP から取得して日本語で回答する。

設計ブリーフ: af-architect (2026-06-15)。MRC (Microsoft Release Communications) MCP を
client-side `MCPStreamableHTTPTool` で接続し、`FoundryChatClient.as_agent` の canonical 経路で
シングル エージェントを構築する。
"""

from __future__ import annotations

import asyncio
import os
import sys

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


AGENT_NAME = "MSUpdatesAgent"

AGENT_INSTRUCTIONS = (
    "あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。\n"
    "回答ポリシー:\n"
    "1. 情報を取得する際は必ず MRC MCP (Microsoft Release Communications) のツールを使い、"
    "そこで得られた内容のみを根拠にしてください。事前知識や推測で補完してはいけません。\n"
    "2. 回答は常に日本語で、簡潔にまとめてください。\n"
    "3. 回答の末尾に「出典」セクションを設け、参照した Microsoft 公式 URL を箇条書きで列挙してください。\n"
    "4. MRC MCP の検索結果に該当情報が無い場合は、推測せず「該当する情報が見つかりませんでした」と"
    "正直に伝えてください。"
)


def _require_env(name: str) -> str:
    """環境変数を必須として取得する。未設定または空文字なら fail-fast で RuntimeError を投げる。

    Codespaces の空 `.env` 注入対策として、空文字列も「未設定」として扱う。
    """
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"環境変数 {name} が未設定または空です。.env を確認してください。"
        )
    return value


async def main() -> None:
    load_dotenv()

    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")
    mrc_mcp_url = _require_env("MRC_MCP_URL")

    user_input = " ".join(sys.argv[1:]).strip() or (
        "ここ最近の Microsoft Entra ID に関する新しいロードマップを 3 件教えてください。"
    )

    mrc = MCPStreamableHTTPTool(
        name="mrc",
        description="Microsoft Release Communications (MRC) の MCP サーバー。"
        "Microsoft 365 と Azure の最新リリース情報を検索できる。",
        url=mrc_mcp_url,
    )

    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=credential,
        )
        async with client.as_agent(
            name=AGENT_NAME,
            instructions=AGENT_INSTRUCTIONS,
            tools=[mrc],
        ) as agent:
            response = await agent.run(user_input)
            print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
