"""MS Updates Agent — Microsoft 365 / Azure 最新リリース情報エージェント (Lab 2)."""

import asyncio
import os
import sys

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

INSTRUCTIONS = (
    "あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。"
    "必ず MRC MCP のツール（https://www.microsoft.com/releasecommunications/mcp）を使って"
    "情報を取得し、推測で答えてはいけません。回答には出典 URL を添えてください。"
    "結果が空の場合は「情報が見つかりませんでした」と正直に答えてください。"
)

MCP_URL = "https://www.microsoft.com/releasecommunications/mcp"


def _require_env(name: str) -> str:
    """環境変数を取得し、未設定なら RuntimeError を送出する。"""
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} が未設定です。.env を確認してください。")
    return value


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else (
        "今四半期に GA になった Azure AI 関連の更新を 3 件教えて"
    )

    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

    mrc_mcp = MCPStreamableHTTPTool(name="MRC", url=MCP_URL)

    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=credential,
        )
        async with client.as_agent(
            name="MSUpdatesAgent",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp],
        ) as agent:
            response = await agent.run(query)
            print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
