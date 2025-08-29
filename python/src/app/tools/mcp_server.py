"""
🚀 SHARED MCP SERVER - Long-lived background server for optimal performance
This runs as a persistent server that multiple clients can connect to
"""
import asyncio
import json
import sys
import os
import time
import signal
from typing import Any, Dict, Optional, Annotated
from mcp.server.fastmcp import FastMCP
from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from langgraph.types import Command
from langchain_core.tools.base import InjectedToolCallId

# 🔁 Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    
# Also add the src directory explicitly
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

print(f"🚀 SHARED MCP SERVER: Python paths configured:")
print(f"   - Project root: {project_root}")
print(f"   - Src path: {src_path}")
print(f"   - Working directory: {os.getcwd()}")

# � Global singleton server instance for direct calls (ZERO subprocess overhead)
_cached_server_instance = None
_cached_azure_services = None

async def get_cached_server_instance():
    """Get or create the singleton server instance with cached Azure services"""
    global _cached_server_instance, _cached_azure_services
    
    if _cached_server_instance is None:
        print("🔄 SHARED MCP: Initializing singleton server instance...")
        
        # Initialize Azure services once and cache them (NOT awaited - it's synchronous)
        _cached_azure_services = get_cached_azure_services()
        
        # Create singleton server instance
        _cached_server_instance = SharedMCPServerInstance(_cached_azure_services)
        print("✅ SHARED MCP: Singleton server instance ready for direct calls")
    
    return _cached_server_instance

class SharedMCPServerInstance:
    """Direct server instance that bypasses subprocess overhead"""
    
    def __init__(self, azure_services: dict):
        self.azure_services = azure_services
        print("🚀 SHARED MCP: Direct server instance created with cached services")
    
    def get_available_tools(self) -> list:
        """Return list of available tools with proper parameter schemas"""
        return [
            {
                "name": "transfer_to_sales_agent",
                "description": "Transfer the conversation to the sales agent",
                "parameters": {}
            },
            {
                "name": "transfer_to_customer_support_agent", 
                "description": "Transfer the conversation to the customer support agent",
                "parameters": {}
            },
            {
                "name": "transfer_to_transactions_agent",
                "description": "Transfer the conversation to the transactions agent",
                "parameters": {}
            },
            {
                "name": "get_offer_information",
                "description": "Get information about banking offers and products",
                "parameters": {
                    "prompt": {
                        "type": "string", 
                        "description": "The user's query about banking offers and products",
                        "required": True
                    },
                    "type": {
                        "type": "string", 
                        "description": "Type of offer (optional, e.g., 'credit_card', 'loan', 'savings')",
                        "required": False
                    }
                }
            },
            {
                "name": "create_account",
                "description": "Create a new bank account for the user",
                "parameters": {}
            },
            {
                "name": "bank_balance",
                "description": "Get the current balance of a user's bank account. Requires the account number as a parameter.",
                "parameters": {
                    "account_number": {
                        "type": "string", 
                        "description": "The account number to check balance for (e.g., 'Acc001', '123', 'ABC123')",
                        "required": True
                    }
                }
            },
            {
                "name": "bank_transfer",
                "description": "Transfer money between bank accounts",
                "parameters": {
                    "fromAccount": {
                        "type": "string",
                        "description": "Source account number for the transfer",
                        "required": True
                    },
                    "toAccount": {
                        "type": "string",
                        "description": "Destination account number for the transfer", 
                        "required": True
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount to transfer (positive number)",
                        "required": True
                    },
                    "tenantId": {
                        "type": "string",
                        "description": "Tenant ID for the transaction",
                        "required": True
                    },
                    "userId": {
                        "type": "string", 
                        "description": "User ID for the transaction",
                        "required": True
                    },
                    "thread_id": {
                        "type": "string",
                        "description": "Thread ID for the transaction",
                        "required": True
                    }
                }
            },
            {
                "name": "get_transaction_history", 
                "description": "Get transaction history for a specific account and date range",
                "parameters": {
                    "account_number": {
                        "type": "string",
                        "description": "Account number to get transaction history for",
                        "required": True
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date for transaction history (YYYY-MM-DD format)",
                        "required": True
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date for transaction history (YYYY-MM-DD format)", 
                        "required": True
                    },
                    "tenantId": {
                        "type": "string",
                        "description": "Tenant ID",
                        "required": True
                    },
                    "userId": {
                        "type": "string",
                        "description": "User ID",
                        "required": True
                    }
                }
            },
            {
                "name": "calculate_monthly_payment",
                "description": "Calculate monthly payment for a loan based on loan amount and years",
                "parameters": {
                    "loan_amount": {
                        "type": "number",
                        "description": "The total loan amount in dollars",
                        "required": True
                    },
                    "years": {
                        "type": "integer", 
                        "description": "The loan term in years",
                        "required": True
                    }
                }
            },
            {
                "name": "service_request",
                "description": "Create a customer service request",
                "parameters": {
                    "recipientPhone": {
                        "type": "string",
                        "description": "Phone number of the recipient for the service request",
                        "required": True
                    },
                    "recipientEmail": {
                        "type": "string",
                        "description": "Email address of the recipient for the service request", 
                        "required": True
                    },
                    "requestSummary": {
                        "type": "string",
                        "description": "Summary description of the service request",
                        "required": True
                    },
                    "tenantId": {
                        "type": "string",
                        "description": "Tenant ID for the request",
                        "required": True
                    },
                    "userId": {
                        "type": "string",
                        "description": "User ID for the request", 
                        "required": True
                    }
                }
            },
            {
                "name": "get_branch_location",
                "description": "Get bank branch locations by state",
                "parameters": {
                    "state": {
                        "type": "string",
                        "description": "State name to get branch locations for (e.g., 'California', 'Texas')",
                        "required": True
                    }
                }
            },
            {
                "name": "health_check",
                "description": "Check the health status of the banking system",
                "parameters": {}
            }
        ]
    
    async def call_tool_directly(self, tool_name: str, arguments: dict) -> Any:
        """Execute tool directly without subprocess overhead"""
        with TimingContext(f"DIRECT_{tool_name}", f"args={str(arguments)[:50]}") as timing:
            
            # Map tool names to direct function calls
            if tool_name == "bank_balance":
                return await self._call_bank_balance_direct(arguments)
            elif tool_name == "get_offer_information":
                return await self._call_get_offer_information_direct(arguments)
            elif tool_name == "create_account":
                return await self._call_create_account_direct(arguments)
            elif tool_name == "transfer_to_sales_agent":
                return await self._call_transfer_to_sales_agent_direct(arguments)
            elif tool_name == "transfer_to_customer_support_agent":
                return await self._call_transfer_to_customer_support_agent_direct(arguments)
            elif tool_name == "transfer_to_transactions_agent":
                return await self._call_transfer_to_transactions_agent_direct(arguments)
            elif tool_name == "bank_transfer":
                return await self._call_bank_transfer_direct(arguments)
            elif tool_name == "get_transaction_history":
                return await self._call_get_transaction_history_direct(arguments)
            elif tool_name == "calculate_monthly_payment":
                return await self._call_calculate_monthly_payment_direct(arguments)
            elif tool_name == "service_request":
                return await self._call_service_request_direct(arguments)
            elif tool_name == "get_branch_location":
                return await self._call_get_branch_location_direct(arguments)
            elif tool_name == "health_check":
                return await self._call_health_check_direct(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
    
    async def _call_bank_balance_direct(self, arguments: dict) -> str:
        """Direct bank balance call with cached services"""
        account_number = arguments.get("account_number", "")
        tenant_id = "Contoso"  # Hardcoded for now
        user_id = "Mark"       # Hardcoded for now
        
        # Use cached fetch_account_by_number function (it's synchronous, not async)
        fetch_account_by_number = self.azure_services['fetch_account_by_number']
        account_data = fetch_account_by_number(account_number, tenant_id, user_id)
        
        if account_data:
            return f"The balance for your account ({account_number}) is ${account_data['balance']:,}."
        else:
            return f"Sorry, I couldn't find account {account_number}. Please check the account number and try again."
    
    async def _call_get_offer_information_direct(self, arguments: dict) -> str:
        """Direct offer information call with cached services"""
        prompt = arguments.get("prompt", "")
        offer_type = arguments.get("type", "")
        
        generate_embedding = self.azure_services['generate_embedding']
        vector_search = self.azure_services['vector_search']
        
        # Generate embedding for the prompt (synchronous function)
        embedding = generate_embedding(prompt)
        
        # Search for relevant offers (synchronous function, takes vectors and accountType)
        results = vector_search(embedding, offer_type)
        
        if results:
            return f"Here are the {offer_type} offers: " + "; ".join([
                f"{offer['name']}: {offer['text']}" 
                for offer in results[:3]  # Top 3 results
            ])
        else:
            return f"No {offer_type} offers found matching your request."
    
    async def _call_create_account_direct(self, arguments: dict) -> str:
        """Direct account creation call"""
        # Simple implementation for now
        account_type = arguments.get("account_type", "checking")
        return f"Account creation request received for {account_type} account. Please visit a branch to complete the process."
    
    async def _call_transfer_to_transactions_agent_direct(self, *args, **kwargs) -> str:
        """Direct call to transfer to transactions agent"""
        print(f"🔧 DEBUG: _call_transfer_to_transactions_agent_direct called with arguments: args={args}, kwargs={kwargs}")
        result = json.dumps({"goto": "transactions_agent", "status": "success"})
        print(f"🔧 DEBUG: _call_transfer_to_transactions_agent_direct returning: {result}")
        return result

    async def _call_transfer_to_sales_agent_direct(self, *args, **kwargs) -> str:
        """Direct call to transfer to sales agent"""
        print(f"🔧 DEBUG: _call_transfer_to_sales_agent_direct called with arguments: args={args}, kwargs={kwargs}")
        result = json.dumps({"goto": "sales_agent", "status": "success"})
        print(f"🔧 DEBUG: _call_transfer_to_sales_agent_direct returning: {result}")
        return result

    async def _call_transfer_to_customer_support_agent_direct(self, *args, **kwargs) -> str:
        """Direct call to transfer to customer support agent"""
        print(f"🔧 DEBUG: _call_transfer_to_customer_support_agent_direct called with arguments: args={args}, kwargs={kwargs}")
        result = json.dumps({"goto": "customer_support_agent", "status": "success"})
        print(f"🔧 DEBUG: _call_transfer_to_customer_support_agent_direct returning: {result}")
        return result
    
    async def _call_health_check_direct(self, arguments: dict) -> str:
        """Direct health check"""
        return "✅ SHARED MCP Server is healthy and running with ZERO subprocess overhead!"
    
    async def _call_bank_transfer_direct(self, arguments: dict) -> str:
        """Direct bank transfer with cached services"""
        from_account = arguments.get("fromAccount", "")
        to_account = arguments.get("toAccount", "")
        amount = float(arguments.get("amount", 0))
        tenant_id = arguments.get("tenantId", "Contoso")  # Default for now
        user_id = arguments.get("userId", "Mark")       # Default for now
        
        if amount <= 0:
            return "Transfer amount must be greater than zero."
        
        if not from_account or not to_account:
            return "Both from and to account numbers are required."
        
        # Get service functions
        fetch_account_by_number = self.azure_services['fetch_account_by_number']
        create_transaction_record = self.azure_services['create_transaction_record']
        patch_account_record = self.azure_services['patch_account_record']
        fetch_latest_transaction_number = self.azure_services['fetch_latest_transaction_number']
        
        try:
            # Check source account exists and has sufficient funds
            from_account_data = fetch_account_by_number(from_account, tenant_id, user_id)
            if not from_account_data:
                return f"Source account {from_account} not found."
            
            if from_account_data['balance'] < amount:
                return f"Insufficient funds in account {from_account}. Current balance: ${from_account_data['balance']}"
            
            # Check destination account exists
            to_account_data = fetch_account_by_number(to_account, tenant_id, user_id)
            if not to_account_data:
                return f"Destination account {to_account} not found."
            
            # Get next transaction numbers (use source account for numbering)
            next_txn_number = fetch_latest_transaction_number(from_account)
            
            # Create debit transaction
            from datetime import datetime
            debit_txn_data = {
                "id": f"{from_account}-{next_txn_number + 1}",
                "tenantId": tenant_id,
                "accountId": from_account_data["accountId"],
                "type": "BankTransaction",
                "debitAmount": amount,
                "creditAmount": 0,
                "accountBalance": from_account_data['balance'] - amount,
                "details": f"Transfer to {to_account}",
                "transactionDateTime": datetime.utcnow().isoformat() + "Z"
            }
            print(f"🔧 DEBUG: Creating debit transaction: {debit_txn_data}")
            create_transaction_record(debit_txn_data)
            print(f"✅ DEBUG: Debit transaction created successfully")
            
            # Update source account balance
            patch_account_record(tenant_id, from_account_data["accountId"], from_account_data['balance'] - amount)
            
            # Get next transaction number for destination account
            next_credit_txn_number = fetch_latest_transaction_number(to_account)
            
            # Create credit transaction
            credit_txn_data = {
                "id": f"{to_account}-{next_credit_txn_number + 1}",
                "tenantId": tenant_id,
                "accountId": to_account_data["accountId"],
                "type": "BankTransaction",
                "debitAmount": 0,
                "creditAmount": amount,
                "accountBalance": to_account_data['balance'] + amount,
                "details": f"Transfer from {from_account}",
                "transactionDateTime": datetime.utcnow().isoformat() + "Z"
            }
            print(f"🔧 DEBUG: Creating credit transaction: {credit_txn_data}")
            create_transaction_record(credit_txn_data)
            print(f"✅ DEBUG: Credit transaction created successfully")
            
            # Update destination account balance
            patch_account_record(tenant_id, to_account_data["accountId"], to_account_data['balance'] + amount)
            
            return f"Successfully transferred ${amount} from {from_account} to {to_account}."
            
        except Exception as e:
            return f"Transfer failed: {str(e)}"
    
    async def _call_get_transaction_history_direct(self, arguments: dict) -> str:
        """Direct transaction history with cached services"""
        account_number = arguments.get("account_number", "")
        start_date = arguments.get("start_date", "")
        end_date = arguments.get("end_date", "")
        tenant_id = arguments.get("tenantId", "Contoso")  # Default for now
        user_id = arguments.get("userId", "Mark")       # Default for now
        
        if not account_number:
            return "Account number is required."
        
        # Get service functions
        fetch_account_by_number = self.azure_services['fetch_account_by_number']
        fetch_transactions_by_date_range = self.azure_services['fetch_transactions_by_date_range']
        
        try:
            from datetime import datetime
            
            # First, get the account by number to get its ID
            account = fetch_account_by_number(account_number, tenant_id, user_id)
            if not account:
                return f"Account {account_number} not found."
            
            print(f"🔧 DEBUG: Found account: {account}")
            
            # Get the account ID (which is what the transaction query needs)
            account_id = account.get('accountId')  # Try accountId field first
            if not account_id:
                account_id = account.get('id')  # Fallback to id field
            if not account_id:
                return f"Could not retrieve account ID for {account_number}."
            
            print(f"🔧 DEBUG: Using account_id for transaction query: {account_id}")
            
            # Parse dates if provided, otherwise use reasonable defaults
            if start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            else:
                start_dt = datetime.now().replace(day=1)  # First day of current month
                
            if end_date:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            else:
                end_dt = datetime.now()  # Today
            
            # Fetch transactions using the account ID (not account number)
            print(f"🔧 DEBUG: Fetching transactions for account_id={account_id}, start_date={start_dt}, end_date={end_dt}")
            transactions = fetch_transactions_by_date_range(account_id, start_dt, end_dt)
            print(f"🔧 DEBUG: Found {len(transactions) if transactions else 0} transactions")
            if transactions:
                print(f"🔧 DEBUG: First transaction: {transactions[0]}")
            
            if not transactions:
                return f"No transactions found for account {account_number} in the specified date range."
                return f"No transactions found for account {account_number} in the specified date range."
            
            # Format response with correct field names from database
            result = f"Transaction history for account {account_number}:\n"
            for txn in transactions[:10]:  # Limit to 10 most recent
                # Extract transaction details from database fields
                date = txn.get('transactionDateTime', 'N/A')
                if date != 'N/A':
                    # Convert ISO date to readable format
                    try:
                        from datetime import datetime
                        date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                        date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass  # Keep original if conversion fails
                
                # Determine transaction type and amount
                debit = txn.get('debitAmount', 0)
                credit = txn.get('creditAmount', 0)
                if debit > 0:
                    amount_str = f"-${debit:,.2f}"
                    txn_type = "Debit"
                elif credit > 0:
                    amount_str = f"+${credit:,.2f}"
                    txn_type = "Credit"
                else:
                    amount_str = "$0.00"
                    txn_type = "Unknown"
                
                details = txn.get('details', 'No details')
                balance = txn.get('accountBalance', 0)
                
                result += f"- {date}: {txn_type} {amount_str} - {details} (Balance: ${balance:,.2f})\n"
            
            return result
            
        except Exception as e:
            return f"Failed to retrieve transaction history: {str(e)}"
    
    async def _call_calculate_monthly_payment_direct(self, arguments: dict) -> str:
        """Direct monthly payment calculation"""
        try:
            loan_amount = float(arguments.get("loan_amount", 0))
            years = int(arguments.get("years", 0))
            
            if loan_amount <= 0:
                return "Loan amount must be greater than zero."
            
            if years <= 0:
                return "Loan term must be greater than zero years."
            
            # Calculate monthly payment with 5% annual interest rate (matching original)
            interest_rate = 0.05  # Hardcoded annual interest rate (5%)
            monthly_rate = interest_rate / 12  # Convert annual rate to monthly
            total_payments = years * 12  # Total number of monthly payments

            if monthly_rate == 0:
                monthly_payment = loan_amount / total_payments  # If interest rate is 0, simple division
            else:
                monthly_payment = (loan_amount * monthly_rate * (1 + monthly_rate) ** total_payments) / \
                                ((1 + monthly_rate) ** total_payments - 1)

            monthly_payment = round(monthly_payment, 2)  # Rounded to 2 decimal places
            
            return f"Monthly payment for a ${loan_amount:,} loan over {years} years at 5% APR: ${monthly_payment:,}"
            
        except Exception as e:
            return f"Failed to calculate monthly payment: {str(e)}"
    
    async def _call_service_request_direct(self, arguments: dict) -> str:
        """Direct service request creation with cached services"""
        try:
            recipient_phone = arguments.get("recipientPhone", "")
            recipient_email = arguments.get("recipientEmail", "")
            request_summary = arguments.get("requestSummary", "")
            tenant_id = arguments.get("tenantId", "Contoso")  # Default for now
            user_id = arguments.get("userId", "Mark")       # Default for now
            
            if not recipient_phone or not recipient_email or not request_summary:
                return "Phone number, email address, and request summary are all required."
            
            # Get service function
            create_service_request_record = self.azure_services['create_service_request_record']
            
            from datetime import datetime
            import uuid
            
            request_id = str(uuid.uuid4())
            requested_on = datetime.utcnow().isoformat() + "Z"
            request_annotations = [
                request_summary,
                f"[{datetime.utcnow().strftime('%d-%m-%Y %H:%M:%S')}] : Urgent"
            ]

            service_request_data = {
                "id": request_id,
                "tenantId": tenant_id,
                "userId": user_id,
                "type": "ServiceRequest",
                "requestedOn": requested_on,
                "scheduledDateTime": "0001-01-01T00:00:00",
                "accountId": "A1",
                "srType": 0,
                "recipientEmail": recipient_email,
                "recipientPhone": recipient_phone,
                "debitAmount": 0,
                "isComplete": False,
                "requestAnnotations": request_annotations,
                "fulfilmentDetails": None
            }

            create_service_request_record(service_request_data)
            return f"Service request created successfully with ID: {request_id}"
            
        except Exception as e:
            return f"Failed to create service request: {str(e)}"
    
    async def _call_get_branch_location_direct(self, arguments: dict) -> str:
        """Direct branch location lookup"""
        try:
            state = arguments.get("state", "").strip()
            
            if not state:
                return "State name is required."
            
            # Static branch location data (matching original implementation)
            branches = {
                "Alabama": {"Jefferson County": ["Central Bank - Birmingham", "Trust Bank - Hoover"],
                            "Mobile County": ["Central Bank - Mobile", "Trust Bank - Prichard"]},
                "Alaska": {"Anchorage": ["Central Bank - Anchorage", "Trust Bank - Eagle River"],
                        "Fairbanks North Star Borough": ["Central Bank - Fairbanks", "Trust Bank - North Pole"]},
                "Arizona": {"Maricopa County": ["Central Bank - Phoenix", "Trust Bank - Scottsdale"],
                            "Pima County": ["Central Bank - Tucson", "Trust Bank - Oro Valley"]},
                "Arkansas": {"Pulaski County": ["Central Bank - Little Rock", "Trust Bank - North Little Rock"],
                            "Benton County": ["Central Bank - Bentonville", "Trust Bank - Rogers"]},
                "California": {"Los Angeles County": ["Central Bank - Los Angeles", "Trust Bank - Long Beach"],
                            "San Diego County": ["Central Bank - San Diego", "Trust Bank - Chula Vista"]},
                "Colorado": {"Denver County": ["Central Bank - Denver", "Trust Bank - Aurora"],
                            "El Paso County": ["Central Bank - Colorado Springs", "Trust Bank - Fountain"]},
                "Connecticut": {"Fairfield County": ["Central Bank - Bridgeport", "Trust Bank - Stamford"],
                                "Hartford County": ["Central Bank - Hartford", "Trust Bank - New Britain"]},
                "Delaware": {"New Castle County": ["Central Bank - Wilmington", "Trust Bank - Newark"],
                            "Sussex County": ["Central Bank - Seaford", "Trust Bank - Lewes"]},
                "Florida": {"Miami-Dade County": ["Central Bank - Miami", "Trust Bank - Hialeah"],
                            "Orange County": ["Central Bank - Orlando", "Trust Bank - Winter Park"]},
                "Georgia": {"Fulton County": ["Central Bank - Atlanta", "Trust Bank - Sandy Springs"],
                            "Cobb County": ["Central Bank - Marietta", "Trust Bank - Smyrna"]},
                "Hawaii": {"Honolulu County": ["Central Bank - Honolulu", "Trust Bank - Pearl City"],
                            "Hawaii County": ["Central Bank - Hilo", "Trust Bank - Kailua-Kona"]},
                "Texas": {"Harris County": ["Central Bank - Houston", "Trust Bank - Pasadena"],
                        "Dallas County": ["Central Bank - Dallas", "Trust Bank - Plano"]},
                "New York": {"New York County": ["Central Bank - Manhattan", "Trust Bank - Brooklyn"],
                            "Kings County": ["Central Bank - Brooklyn", "Trust Bank - Queens"]},
                "Washington": {"King County": ["Central Bank - Seattle", "Trust Bank - Bellevue"],
                            "Pierce County": ["Central Bank - Tacoma", "Trust Bank - Lakewood"]}
            }
            
            # Case-insensitive state lookup
            state_match = None
            for state_key in branches.keys():
                if state_key.lower() == state.lower():
                    state_match = state_key
                    break
            
            if not state_match:
                available_states = ", ".join(sorted(branches.keys()))
                return f"No branches found for '{state}'. Available states: {available_states}"
            
            # Format response
            result = f"Branch locations in {state_match}:\n"
            for county, branch_list in branches[state_match].items():
                result += f"\n{county}:\n"
                for branch in branch_list:
                    result += f"  - {branch}\n"
            
            return result
            
        except Exception as e:
            return f"Failed to get branch locations: {str(e)}"

async def get_available_tools():
    """Get list of available tools for direct execution"""
    # This mimics the tool definitions but for direct calls
    from langchain_core.tools import tool
    
    @tool
    def bank_balance_tool():
        """Get account balance for a specific account number"""
        pass
    
    @tool  
    def get_offer_information_tool():
        """Get information about banking offers"""
        pass
    
    @tool
    def create_account_tool():
        """Create a new bank account"""
        pass
        
    @tool
    def transfer_to_sales_agent_tool():
        """Transfer user to sales agent"""
        pass
        
    @tool
    def transfer_to_customer_support_agent_tool():
        """Transfer user to customer support agent"""
        pass
        
    @tool
    def transfer_to_transactions_agent_tool():
        """Transfer user to transactions agent"""
        pass
        
    @tool
    def health_check_tool():
        """Check if the server is healthy"""
        pass
    
    # Return the tool definitions
    return [
        bank_balance_tool,
        get_offer_information_tool, 
        create_account_tool,
        transfer_to_sales_agent_tool,
        transfer_to_customer_support_agent_tool,
        transfer_to_transactions_agent_tool,
        health_check_tool
    ]

# �🕒 Timing utilities for performance debugging (copied from original mcp_server.py)
import logging
logger = logging.getLogger(__name__)

def log_timing(operation: str, duration_ms: float, additional_info: str = ""):
    """Log timing information with consistent formatting"""
    log_msg = f"⏱️  TIMING: {operation} took {duration_ms:.2f}ms"
    if additional_info:
        log_msg += f" | {additional_info}"
    print(log_msg)
    logger.info(log_msg)

class TimingContext:
    """Context manager for measuring operation timing"""
    def __init__(self, operation_name: str, additional_info: str = ""):
        self.operation_name = operation_name
        self.additional_info = additional_info
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        log_timing(self.operation_name, duration_ms, self.additional_info)

# 🚀 Global caches for maximum performance
_azure_services_cache: Optional[Dict[str, Any]] = None
_azure_credentials_cache: Optional[Any] = None
_cosmos_client_cache: Optional[Any] = None
_openai_client_cache: Optional[Any] = None
_server_start_time = time.time()

print(f"🚀 SHARED MCP SERVER: Starting at {time.strftime('%H:%M:%S')}")

# Initialize FastMCP server
mcp = FastMCP("Banking Tools Shared Server")

def get_cached_azure_services() -> Dict[str, Any]:
    """Get cached Azure services with connection pooling"""
    global _azure_services_cache, _azure_credentials_cache, _cosmos_client_cache, _openai_client_cache
    
    if _azure_services_cache is not None:
        return _azure_services_cache
    
    print(f"🔧 SHARED MCP SERVER: Initializing Azure services (one-time setup)...")
    start_time = time.time()
    
    try:
        # Pre-initialize Azure credentials
        from azure.identity import DefaultAzureCredential
        _azure_credentials_cache = DefaultAzureCredential()
        
        # Import services directly - don't pre-initialize clients as they're already initialized
        from src.app.services.azure_open_ai import generate_embedding
        from src.app.services.azure_cosmos_db import (
            vector_search,
            create_account_record,
            fetch_latest_account_number,
            fetch_latest_transaction_number,
            fetch_account_by_number,
            create_transaction_record,
            patch_account_record,
            fetch_transactions_by_date_range,
            create_service_request_record,
        )
        
        print("✅ SHARED MCP SERVER: All Azure services imported successfully")
        
        # Import the actual service functions with proper error handling
        try:
            from src.app.services.azure_open_ai import generate_embedding
            print("✅ SHARED MCP SERVER: azure_open_ai imported successfully")
        except ImportError as e:
            print(f"❌ SHARED MCP SERVER: Failed to import azure_open_ai: {e}")
            raise
        
        try:
            from src.app.services.azure_cosmos_db import (
                vector_search,
                create_account_record,
                fetch_latest_account_number,
                fetch_latest_transaction_number,
                fetch_account_by_number,
                create_transaction_record,
                patch_account_record,
                fetch_transactions_by_date_range,
                create_service_request_record,
            )
            print("✅ SHARED MCP SERVER: azure_cosmos_db imported successfully")
        except ImportError as e:
            print(f"❌ SHARED MCP SERVER: Failed to import azure_cosmos_db: {e}")
            raise
        
        _azure_services_cache = {
            'generate_embedding': generate_embedding,
            'vector_search': vector_search,
            'create_account_record': create_account_record,
            'fetch_latest_account_number': fetch_latest_account_number,
            'fetch_latest_transaction_number': fetch_latest_transaction_number,
            'fetch_account_by_number': fetch_account_by_number,
            'create_transaction_record': create_transaction_record,
            'patch_account_record': patch_account_record,
            'fetch_transactions_by_date_range': fetch_transactions_by_date_range,
            'create_service_request_record': create_service_request_record,
        }
        
        setup_time = (time.time() - start_time) * 1000
        print(f"✅ SHARED MCP SERVER: Azure services initialized in {setup_time:.2f}ms")
        
        return _azure_services_cache
        
    except Exception as e:
        print(f"❌ SHARED MCP SERVER: Failed to initialize Azure services: {e}")
        raise

# Transfer tools with proper implementation matching original mcp_server.py
def create_agent_transfer(agent_name: str):
    """Create agent transfer tool with proper Command structure - matches original mcp_server.py"""
    tool_name = f"transfer_to_{agent_name}"

    @mcp.tool(tool_name)
    def transfer_to_agent(
        tool_call_id: Annotated[str, InjectedToolCallId],
        **kwargs
    ):
        state = kwargs.get("state", {})
        print(f"🔄 SHARED MCP: Transferring to {agent_name.replace('_', ' ')}...")
        
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

# Register agent transfer tools exactly like original
create_agent_transfer("sales_agent")
create_agent_transfer("customer_support_agent") 
create_agent_transfer("transactions_agent")

@mcp.tool()
@traceable  
def get_offer_information(user_prompt: str, accountType: str) -> list[dict[str, Any]]:
    """Provide information about a product based on the user prompt.
    Takes as input the user prompt as a string."""
    
    with TimingContext("TOTAL_get_offer_information", f"prompt='{user_prompt[:50]}...', type={accountType}"):
        print(f"🔍 SHARED MCP: Starting get_offer_information: prompt='{user_prompt}', accountType='{accountType}'")
        
        # Use cached Azure services for maximum speed
        azure_services = get_cached_azure_services()
        
        # Time the embedding generation
        with TimingContext("generate_embedding", f"prompt_length={len(user_prompt)}"):
            vectors = azure_services['generate_embedding'](user_prompt)
        
        print(f"🔍 SHARED MCP: Generated embedding: length={len(vectors) if vectors else 'None'}")
        
        # Time the vector search
        with TimingContext("vector_search", f"accountType={accountType}, embedding_dims={len(vectors) if vectors else 0}"):
            search_results = azure_services['vector_search'](vectors, accountType)
        
        print(f"🔍 SHARED MCP: Vector search complete: found {len(search_results) if search_results else 0} results")
        
        return search_results

@mcp.tool()
@traceable
def create_account(account_holder: str, balance: float, config: RunnableConfig) -> str:
    """Create a new bank account for a user with optimized performance"""
    
    print(f"💰 SHARED MCP: Creating account for {account_holder}")
    
    try:
        # Use cached services
        azure_services = get_cached_azure_services()
        
        thread_id = config["configurable"].get("thread_id", "UNKNOWN_THREAD_ID")
        userId = config["configurable"].get("userId", "UNKNOWN_USER_ID") 
        tenantId = config["configurable"].get("tenantId", "UNKNOWN_TENANT_ID")
        
        account_number = azure_services['fetch_latest_account_number']()
        if account_number is None:
            account_number = 1
        else:
            account_number += 1

        account_data = {
            "id": f"{account_number}",
            "accountId": f"A{account_number}",
            "tenantId": tenantId,
            "userId": userId,
            "name": "Account",
            "type": "BankAccount",
            "accountName": account_holder,
            "balance": balance,
            "startDate": "01-01-2025",
            "accountDescription": "Banking account",
        }
        
        azure_services['create_account_record'](account_data)
        result = f"Successfully created account {account_number} for {account_holder} with balance ${balance}"
        print(f"✅ SHARED MCP: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Failed to create account: {str(e)}"
        print(f"❌ SHARED MCP: {error_msg}")
        return error_msg

@mcp.tool()
@traceable
def bank_balance(account_number: str) -> str:
    """Retrieve the balance for a specific bank account."""
    # Get cached Azure services
    azure_services = get_cached_azure_services()
    fetch_account_by_number = azure_services['fetch_account_by_number']
    
    # TODO: Get tenant/user context from somewhere else
    tenantId = "Contoso"  # Hardcoded for now
    userId = "Mark"       # Hardcoded for now

    account = fetch_account_by_number(account_number, tenantId, userId)
    if not account:
        return f"Account {account_number} not found for tenant {tenantId} and user {userId}"

    balance = account.get("balance", 0)
    return f"The balance for account number {account_number} is ${balance}"

@mcp.tool()
def health_check() -> str:
    """Health check with server uptime information"""
    uptime = (time.time() - _server_start_time)
    return f"🚀 SHARED MCP Server is healthy! Uptime: {uptime:.1f}s"

# Graceful shutdown handling
def signal_handler(signum, frame):
    print(f"🔄 SHARED MCP SERVER: Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    print("🚀 SHARED MCP SERVER: Starting long-lived server...")
    print(f"🚀 SHARED MCP SERVER: Server ready for connections")
    
    try:
        # Run the server
        mcp.run()
    except KeyboardInterrupt:
        print("🚀 SHARED MCP SERVER: Stopped by user")
    except Exception as e:
        print(f"❌ SHARED MCP SERVER: Error: {e}")
    finally:
        print("🚀 SHARED MCP SERVER: Cleanup complete")
