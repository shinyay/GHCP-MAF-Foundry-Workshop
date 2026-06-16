import asyncio
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from azure.identity.aio import AzureCliCredential
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework_foundry import FoundryChatClient

load_dotenv()


async def main() -> None:
    """Main entry point for the MS Updates Agent.
    
    Provides Microsoft 365 and Azure latest release information in Japanese.
    Integrates with Microsoft Release Communications MCP.
    """
    
    # Get command line argument for custom query
    query: str = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Microsoft 365 と Azure の最新リリース情報を教えてください"
    )
    
    # Get environment variables
    endpoint: Optional[str] = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT environment variable is required")
    
    model: str = os.environ.get("FOUNDRY_MODEL") or os.environ.get(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"
    )
    
    # Initialize credentials and client
    async with AzureCliCredential() as credential:
        client: FoundryChatClient = FoundryChatClient(
            credential=credential, project_endpoint=endpoint
        )
        
        # Create MCP tool for Microsoft Release Communications
        mrc_tool: MCPStreamableHTTPTool = MCPStreamableHTTPTool(
            uri="https://www.microsoft.com/releasecommunications/mcp"
        )
        
        # Create and run agent
        async with client.as_agent(
            name="MSUpdatesAgent",
            model=model,
            instructions=(
                "あなたは Microsoft 365 と Azure の最新リリース情報を提供する日本語アシスタントです。"
                "必ず Microsoft Release Communications MCP のツールを使用して回答し、出典 URL を必ず添えてください。"
            ),
            tools=[mrc_tool],
        ) as agent:
            agent_instance: Agent = agent
            
            # Run the agent with the query
            response = await agent_instance.run(query)
            
            # Print the response
            result: str = (
                response.value if hasattr(response, "value") else str(response)
            )
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
