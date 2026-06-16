"""MS Updates Agent — Microsoft 365 / Azure 最新リリース情報エージェント (Lab 2, Haiku 修正版)."""

import asyncio
import os
import sys

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

INSTRUCTIONS = (
    "あなたは Microsoft 365 と Azure の最新リリース情報を提供する日本語アシスタントです。"
    "必ず Microsoft Release Communications MCP のツールを使用して回答し、出典 URL を必ず添えてください。"
    "推測で答えてはいけません。結果が空の場合は「情報が見つかりませんでした」と答えてください。"
)

MCP_URL = "https://www.microsoft.com/releasecommunications/mcp"


async def main() -> None:
    query: str = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Microsoft 365 と Azure の最新リリース情報を教えてください"
    )

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT が未設定です。.env を確認してください。")

    model = os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

    mrc_mcp = MCPStreamableHTTPTool(name="MRC", url=MCP_URL)

    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=endpoint,
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
