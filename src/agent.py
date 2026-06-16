"""
MS Updates Agent - Microsoft 365 と Azure の最新リリース情報を回答する日本語エージェント

Usage:
    python src/agent.py "質問をここに入力"
"""

import asyncio
import os
import sys
from pathlib import Path

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


# --- 1. Load .env (fill-only, don't override) ---
_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
for _k, _v in dotenv_values(_DOTENV_PATH).items():
    if _v is None:
        continue
    if not (os.getenv(_k) or "").strip():
        os.environ[_k] = _v


def _require_env(name: str) -> str:
    """Load and validate a required environment variable."""
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable is missing or empty: {name}. "
            "Set it via .env / export / Codespaces secrets and try again."
        )
    return value


async def main() -> None:
    """Main entry point for the MS Updates Agent."""
    # Get question from CLI argument
    if len(sys.argv) < 2:
        raise ValueError(
            "Usage: python src/agent.py '<question>'\n"
            "Example: python src/agent.py 'Azure の最新リリース情報は？'"
        )
    question = " ".join(sys.argv[1:])

    # Load configuration
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = os.environ.get("FOUNDRY_MODEL") or os.environ.get(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME"
    )
    if not model:
        raise RuntimeError(
            "Model not configured. Set FOUNDRY_MODEL or AZURE_AI_MODEL_DEPLOYMENT_NAME."
        )

    # Create MCP tool for Microsoft Release Communications
    mrc_tool = MCPStreamableHTTPTool(
        name="microsoft_release_communications",
        url="https://www.microsoft.com/releasecommunications/mcp",
    )

    # Create agent and run
    async with AzureCliCredential() as credential:
        async with FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=credential,
        ).as_agent(
            name="MSUpdatesAgent",
            instructions=(
                "You are a helpful assistant that provides information about "
                "the latest releases and updates for Microsoft 365 and Azure products. "
                "Always respond in Japanese (日本語). "
                "Use the microsoft_release_communications tool to find the latest information. "
                "Always include source URLs when providing information. "
                "If you cannot find information, clearly state that you couldn't find it."
            ),
            tools=[mrc_tool],
        ) as agent:
            result = await agent.run(question)
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
