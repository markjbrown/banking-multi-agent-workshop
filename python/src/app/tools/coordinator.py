import sys
import os
import logging
from typing import Annotated
from colorama import Fore, Style
from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools.base import InjectedToolCallId
from mcp.server.fastmcp import FastMCP

# 🔁 Ensure project root is in sys.path before imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# ✅ Initialize MCP tool server
mcp = FastMCP("CoordinatorTools")

def create_agent_transfer(agent_name: str):
    tool_name = f"transfer_to_{agent_name}"

    @mcp.tool(tool_name)
    def transfer_to_agent(
        tool_call_id: Annotated[str, InjectedToolCallId],
        **kwargs
    ):
        state = kwargs.get("state", {})
        print(Fore.LIGHTMAGENTA_EX + f"→ Transferring to {agent_name.replace('_', ' ')}..." + Style.RESET_ALL)
        tool_message = {
            "role": "tool",
            "content": f"Successfully transferred to {agent_name.replace('_', ' ')}",
            "name": tool_name,
            "tool_call_id": tool_call_id,
        }
        return Command(
            goto=agent_name,
            graph=Command.PARENT,
            update={"messages": state.get("messages", []) + [tool_message]},
        )

# Register agent transfer tools
create_agent_transfer("sales_agent")
create_agent_transfer("customer_support_agent")
create_agent_transfer("transactions_agent")

# ✅ Entry point for stdio server
if __name__ == "__main__":
    print("Starting coordinator MCP tool server...")
    mcp.run(transport="stdio")
