import asyncio
import os

from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

load_dotenv()


async def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=AzureCliCredential(),
        ),
        instructions="あなたは日本語アシスタントです。簡潔に答えてください。",
    )
    response = await agent.run("こんにちは。1 行で自己紹介して。")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
