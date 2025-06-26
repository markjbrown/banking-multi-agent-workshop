import logging
import os
import sys
import uuid
import asyncio
from langchain.schema import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from typing import Literal, TypedDict
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command, interrupt
from langgraph_checkpoint_cosmosdb_local import CosmosDBSaver
from langgraph.checkpoint.memory import MemorySaver
from langsmith import traceable
from src.app.services.azure_open_ai import model
from src.app.services.azure_cosmos_db import DATABASE_NAME, checkpoint_container, chat_container, \
    update_chat_container, patch_active_agent

local_interactive_mode = False

logging.basicConfig(level=logging.DEBUG)

PROMPT_DIR = os.path.join(os.path.dirname(__file__), 'prompts')

import json
from langchain_core.messages import ToolMessage

def has_tool_call(messages):
    """Returns True if any message includes a tool call."""
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return True
    return False


def extract_goto_from_tool_messages(response, agent_name: str) -> str:
    """Extract 'goto' from a ToolMessage content, or default to 'human'."""
    messages = response.get("messages", []) if isinstance(response, dict) else response
    for m in messages:
        if isinstance(m, ToolMessage):
            try:
                content = json.loads(m.content)
                if "goto" in content:
                    goto_target = content["goto"]
                    print(f"[DEBUG] {agent_name} extracted goto → {goto_target}")
                    return goto_target
            except Exception as e:
                print(f"[WARN] Failed to parse ToolMessage in {agent_name}: {e}")
    print(f"[DEBUG] {agent_name} found no goto — defaulting to 'human'")
    return "human"



def load_prompt(agent_name):
    file_path = os.path.join(PROMPT_DIR, f"{agent_name}.prompty")
    print(f"Loading prompt for {agent_name} from {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"Prompt file not found for {agent_name}, using default placeholder.")
        return "You are an AI banking assistant."


async def setup_agents():
    global coordinator_agent, customer_support_agent, transactions_agent, sales_agent

    print("Starting coordinator agent tools MCP client...")
    #  uvicorn mcp_servers.coordinator_server:app --host 0.0.0.0 --port 9010
    coordinator_agent_tools_client = MultiServerMCPClient({
        "coordinator_agent": {
            "command": "python",
            "args": ["-m", "src.app.tools.coordinator"],
            "transport": "stdio",
        },
    })
    coordinator_tools = await coordinator_agent_tools_client.get_tools()
    print("[DEBUG] Tools registered with coordinator MCP:")
    for tool in coordinator_tools:
        print("  -", tool.name)
    coordinator_agent = create_react_agent(model, coordinator_tools, state_modifier=load_prompt("coordinator_agent"))

    print("Starting customer support agent tools MCP client...")
    # uvicorn mcp_servers.support_server:app --host 0.0.0.0 --port 9011
    customer_support_agent_tools_client = MultiServerMCPClient({
        "customer_support_agent": {
            "command": "python",
            "args": ["-m", "src.app.tools.support"],
            "transport": "stdio",
        },
    })
    support_tools = await customer_support_agent_tools_client.get_tools()
    customer_support_agent = create_react_agent(model, support_tools,
                                                state_modifier=load_prompt("customer_support_agent"))

    print("Starting transactions agent tools MCP client...")
    # uvicorn mcp_servers.transactions_server:app --host 0.0.0.0 --port 9012
    transactions_agent_tools_client = MultiServerMCPClient({
        "transactions_agent": {
            "command": "python",
            "args": ["-m", "src.app.tools.transactions"],
            "transport": "stdio",
        },
    })
    transactions_tools = await transactions_agent_tools_client.get_tools()
    transactions_agent = create_react_agent(model, transactions_tools, state_modifier=load_prompt("transactions_agent"))

    print("Starting sales agent tools MCP client...")
    # uvicorn mcp_servers.sales_server:app --host 0.0.0.0 --port 9013
    sales_agent_tools_client = MultiServerMCPClient({
        "sales_agent": {
            "command": "python",
            "args": ["-m", "src.app.tools.sales"],
            "transport": "stdio",
        },
    })
    sales_tools = await sales_agent_tools_client.get_tools()
    sales_agent = create_react_agent(model, sales_tools, state_modifier=load_prompt("sales_agent"))

    # Once agents are ready, compile the graph and start chat
    # interactive_chat()


@traceable(run_type="llm")
async def call_coordinator_agent(state: MessagesState, config) -> Command[Literal["coordinator_agent", "human"]]:
    thread_id = config["configurable"].get("thread_id", "UNKNOWN_THREAD_ID")
    userId = config["configurable"].get("userId", "UNKNOWN_USER_ID")
    tenantId = config["configurable"].get("tenantId", "UNKNOWN_TENANT_ID")

    print(f"Calling coordinator agent with Thread ID: {thread_id}")

    try:
        activeAgent = chat_container.read_item(item=thread_id, partition_key=[tenantId, userId, thread_id]).get(
            'activeAgent', 'unknown')
    except Exception as e:
        logging.debug(f"No active agent found: {e}")
        activeAgent = None

    if activeAgent is None:
        if local_interactive_mode:
            update_chat_container({
                "id": thread_id,
                "tenantId": "cli-test",
                "userId": "cli-test",
                "sessionId": thread_id,
                "name": "cli-test",
                "age": "cli-test",
                "address": "cli-test",
                "activeAgent": "unknown",
                "ChatName": "cli-test",
                "messages": []
            })

    print(f"Active agent from point lookup: {activeAgent}")
    last_agent = state.get("last_agent", None)

    if activeAgent not in [None, "unknown", "coordinator_agent"]:
        # if activeAgent == last_agent:
        #     print(f"[WARN] coordinator_agent would loop back to {activeAgent} — overriding to 'human'")
        #     return Command(update={**state, "last_agent": "coordinator_agent"}, goto="human")
        print(f"Routing straight to last active agent: {activeAgent}")
        return Command(update=state, goto=activeAgent)
    else:
        response = await coordinator_agent.ainvoke(state)
        print("response from coordinator_agent:", response)
        # print("[DEBUG] LangGraph response from coordinator:", response)
        # return Command(update=response, goto="human")
        goto = extract_goto_from_tool_messages(response, coordinator_agent.name)
        if goto == "coordinator_agent":
            print("[WARN] coordinator_agent attempted to self-route — overriding to 'human'")
            goto = "human"
        # if has_tool_call(response.get("messages", [])):
        #     # 🧠 Suppress text output if it's just a tool transfer
        #     return Command(update={"last_agent": "coordinator_agent"}, goto=goto)
        return Command(update=response, goto=goto)


@traceable(run_type="llm")
async def call_customer_support_agent(state: MessagesState, config) -> Command[Literal["customer_support_agent", "human"]]:
    thread_id = config["configurable"].get("thread_id", "UNKNOWN_THREAD_ID")
    if local_interactive_mode:
        patch_active_agent("cli-test", "cli-test", thread_id, "customer_support_agent")
    response = await customer_support_agent.ainvoke(state, config)
    print ("response from customer_support_agent:", response)
    goto = extract_goto_from_tool_messages(response, customer_support_agent.name)
    if goto == "customer_support_agent":
        print("[WARN] customer_support_agent attempted to self-route — overriding to 'human'")
    #     goto = "human"
    # if has_tool_call(response.get("messages", [])):
    #     return Command(update={"last_agent": "customer_support_agent"}, goto=goto)
    return Command(update=response, goto=goto)


@traceable(run_type="llm")
async def call_sales_agent(state: MessagesState, config) -> Command[Literal["sales_agent", "human"]]:
    thread_id = config["configurable"].get("thread_id", "UNKNOWN_THREAD_ID")
    if local_interactive_mode:
        patch_active_agent("cli-test", "cli-test", thread_id, "sales_agent")
    response = await sales_agent.ainvoke(state, config)
    print("response from sales_agent:", response)
    goto = extract_goto_from_tool_messages(response, sales_agent.name)
    if goto == "sales_agent":
        print("[WARN] sales_agent attempted to self-route — overriding to 'human'")
        goto = "human"
        # 🧠 Suppress text output if it's just a tool transfer
    # if has_tool_call(response["messages"]):
    #     return Command(update={"last_agent": "sales_agent"}, goto=goto)
    return Command(update=response, goto=goto)



@traceable(run_type="llm")
async def call_transactions_agent(state: MessagesState, config) -> Command[Literal["transactions_agent", "human"]]:
    thread_id = config["configurable"].get("thread_id", "UNKNOWN_THREAD_ID")
    if local_interactive_mode:
        patch_active_agent("cli-test", "cli-test", thread_id, "transactions_agent")
    response = await transactions_agent.ainvoke(state, config)
    print("response from transactions_agent:", response)
    goto = extract_goto_from_tool_messages(response, transactions_agent.name)
    if goto == "transactions_agent":
        print("[WARN] transactions_agent attempted to self-route — overriding to 'human'")
        goto = "human"
    # if has_tool_call(response.get("messages", [])):
    #     # 🧠 Suppress text output if it's just a tool transfer
    #     return Command(update={"last_agent": "transactions_agent"}, goto=goto)
    return Command(update=response, goto=goto)



@traceable
def human_node(state: MessagesState, config) -> None:
    interrupt(value="Ready for user input.")
    return None

builder = StateGraph(MessagesState)
# declare last_agent as a state value
# builder = StateGraph(state_schema={"messages": list, "last_agent": str})
builder.add_node("coordinator_agent", call_coordinator_agent)
builder.add_node("customer_support_agent", call_customer_support_agent)
builder.add_node("sales_agent", call_sales_agent)
builder.add_node("transactions_agent", call_transactions_agent)
builder.add_node("human", human_node)

builder.add_edge(START, "coordinator_agent")

# #Allow agent-to-agent transitions (required for MCP tool-initiated transfers)
agents = ["coordinator_agent", "customer_support_agent", "sales_agent", "transactions_agent"]

# for source in agents:
#     for target in agents:
#         if source != target:
#             builder.add_edge(source, target)

# Only allow coordinator to launch agents
for agent in agents:
    if agent != "coordinator_agent":
        builder.add_edge("coordinator_agent", agent)

# Each agent can go to `human` only
for agent in agents:
    if agent != "coordinator_agent":
        builder.add_edge(agent, "human")

# Resume flow: human → coordinator
builder.add_edge("human", "coordinator_agent")



checkpointer = CosmosDBSaver(database_name=DATABASE_NAME, container_name=checkpoint_container)
import inspect
print("✅ Using CosmosDBSaver from:", checkpointer.__class__.__module__)
print("🧠 CosmosDBSaver.aput signature:", inspect.signature(checkpointer.aput))
#checkpointer = MemorySaver()  # Use MemorySaver for local testing
graph = builder.compile(checkpointer=checkpointer)


def interactive_chat():
    thread_config = {"configurable": {"thread_id": str(uuid.uuid4()), "userId": "Mark", "tenantId": "Contoso"}}
    global local_interactive_mode
    local_interactive_mode = True
    print("Welcome to the interactive multi-agent shopping assistant.")
    print("Type 'exit' to end the conversation.\n")

    user_input = input("You: ")

    while user_input.lower() != "exit":
        input_message = {"messages": [{"role": "user", "content": user_input}]}
        # input_message = {
        #     "messages": [{"role": "user", "content": user_input}],
        #     "last_agent": "human"
        # }  # Ensure we start with human as the last agent

        response_found = False

        for update in graph.stream(input_message, config=thread_config, stream_mode="updates"):
            for node_id, value in update.items():
                if isinstance(value, dict) and value.get("messages"):
                    last_message = value["messages"][-1]
                    if isinstance(last_message, AIMessage):
                        print(f"{node_id}: {last_message.content}\n")
                        response_found = True

        if not response_found:
            print("DEBUG: No AI response received.")

        user_input = input("You: ")


if __name__ == "__main__":
    if sys.platform == "win32":
        print("Setting up Windows-specific event loop policy...")
        # Set the event loop to ProactorEventLoop on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(setup_agents())
