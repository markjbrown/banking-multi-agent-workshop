import logging
from datetime import datetime
from typing import List, Dict
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langsmith import traceable
from langchain_mcp_adapters.tools import to_fastmcp

from src.app.services.azure_cosmos_db import (
    fetch_latest_transaction_number,
    fetch_account_by_number,
    create_transaction_record,
    patch_account_record,
    fetch_transactions_by_date_range,
)

from mcp.server.fastmcp import FastMCP


@tool
@traceable
def transfer(config: RunnableConfig, toAccount: str, fromAccount: str, amount: float) -> str:
    """Transfer funds between two accounts."""
    print(f"Transferring ${amount} from {fromAccount} to {toAccount}...")
    debit_result = bank_transaction(config, fromAccount, amount, credit_account=0, debit_account=amount)
    if "Failed" in debit_result:
        return f"Failed to debit amount from {fromAccount}: {debit_result}"

    credit_result = bank_transaction(config, toAccount, amount, credit_account=amount, debit_account=0)
    if "Failed" in credit_result:
        return f"Failed to credit amount to {toAccount}: {credit_result}"

    return f"Successfully transferred ${amount} from account {fromAccount} to account {toAccount}"


def bank_transaction(config: RunnableConfig, account_number: str, amount: float, credit_account: float,
                     debit_account: float) -> str:
    print(f"Processing transaction for account {account_number}: "
          f"credit=${credit_account}, debit=${debit_account}, total amount=${amount}")
    """Helper to execute bank debit or credit."""
    tenantId = config["configurable"].get("tenantId", "UNKNOWN_TENANT_ID")
    userId = config["configurable"].get("userId", "UNKNOWN_USER_ID")

    account = fetch_account_by_number(account_number, tenantId, userId)
    if not account:
        return f"Account {account_number} not found for tenant {tenantId} and user {userId}"

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            latest_transaction_number = fetch_latest_transaction_number(account_number)
            transaction_id = f"{account_number}-{latest_transaction_number + 1}"
            new_balance = account["balance"] + credit_account - debit_account

            transaction_data = {
                "id": transaction_id,
                "tenantId": tenantId,
                "accountId": account["accountId"],
                "type": "BankTransaction",
                "debitAmount": debit_account,
                "creditAmount": credit_account,
                "accountBalance": new_balance,
                "details": "Bank Transfer",
                "transactionDateTime": datetime.utcnow().isoformat() + "Z"
            }

            create_transaction_record(transaction_data)
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_attempts - 1:
                return f"Failed to create transaction record after {max_attempts} attempts: {e}"

    patch_account_record(tenantId, account["accountId"], new_balance)
    return f"Successfully transferred ${amount} to account number {account_number}"


@tool
@traceable
def transaction_history(accountId: str, startDate: datetime, endDate: datetime) -> List[Dict]:
    """Retrieve transactions for an account between two dates."""
    try:
        return fetch_transactions_by_date_range(accountId, startDate, endDate)
    except Exception as e:
        logging.error(f"Error fetching transaction history for account {accountId}: {e}")
        return []


@tool
@traceable
def balance(config: RunnableConfig, account_number: str) -> str:
    """Retrieve the balance for a specific bank account."""
    tenantId = config["configurable"].get("tenantId", "UNKNOWN_TENANT_ID")
    userId = config["configurable"].get("userId", "UNKNOWN_USER_ID")

    account = fetch_account_by_number(account_number, tenantId, userId)
    if not account:
        return f"Account {account_number} not found for tenant {tenantId} and user {userId}"

    balance = account.get("balance", 0)
    return f"The balance for account number {account_number} is ${balance}"


@tool
@traceable
def transfer_to_customer_support_agent() -> dict:
    """Transfer control to the customer support agent."""
    return {
        "graph": "__parent__",
        "update": {
            "messages": [
                {
                    "role": "tool",
                    "content": "Successfully transferred to customer support agent",
                    "name": "transfer_to_customer_support_agent",
                    "tool_call_id": "1"
                }
            ]
        },
        "goto": "customer_support_agent"
    }


# Convert tools for MCP
bank_transfer = to_fastmcp(transfer)
bank_balance = to_fastmcp(balance)
get_transaction_history = to_fastmcp(transaction_history)
transfer_tool = to_fastmcp(transfer_to_customer_support_agent)

# Initialize FastMCP with a proper instructions string
mcp = FastMCP(
    instructions="MCP server providing banking tools for transfers, balance checking, and agent redirection.",
    tools=[
        bank_transfer,
        bank_balance,
        get_transaction_history,
        transfer_tool
    ]
)

if __name__ == "__main__":
    mcp.run(transport="stdio")
