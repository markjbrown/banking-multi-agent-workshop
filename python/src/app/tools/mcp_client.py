"""
🚀 ENHANCED MCP CLIENT - HTTP and Direct Server Support
This client manages connections to both HTTP MCP servers and direct server instances
"""
import asyncio
import subprocess
import time
import os
import signal
import contextvars
import httpx
import jwt
from typing import Optional, Dict, Any, List
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import StructuredTool
from dotenv import load_dotenv

load_dotenv(override=False)

# Context variables for tenant/user information
TENANT_CONTEXT = contextvars.ContextVar('tenant_context', default=None)
USER_CONTEXT = contextvars.ContextVar('user_context', default=None) 
THREAD_CONTEXT = contextvars.ContextVar('thread_context', default=None)

def set_mcp_context(tenantId: Optional[str], userId: Optional[str], thread_id: Optional[str]):
    """Set the MCP context for automatic parameter injection"""
    if tenantId:
        TENANT_CONTEXT.set(tenantId)
    if userId:
        USER_CONTEXT.set(userId)
    if thread_id:
        THREAD_CONTEXT.set(thread_id)
    print(f"🔧 MCP CONTEXT: Set context - tenantId='{tenantId}', userId='{userId}', thread_id='{thread_id}'")

def get_mcp_context():
    """Get the current MCP context"""
    return {
        'tenantId': TENANT_CONTEXT.get(),
        'userId': USER_CONTEXT.get(),
        'thread_id': THREAD_CONTEXT.get()
    }

class HTTPMCPClient:
    """HTTP-based MCP client for connecting to remote MCP servers"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv("MCP_SERVER_ENDPOINT", "http://localhost:8080")
        self.access_token = None
        self.tools_cache: Optional[List] = None
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
    async def authenticate(self) -> bool:
        """Authenticate with the HTTP MCP server"""
        try:
            print(f"🔐 HTTP MCP: Authenticating with server at {self.base_url}")
            
            # Get token from auth endpoint (in production, use proper OAuth2 flow)
            response = await self.http_client.post(f"{self.base_url}/auth/token")
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            
            if not self.access_token:
                print("❌ HTTP MCP: No access token received")
                return False
                
            print("✅ HTTP MCP: Successfully authenticated")
            return True
            
        except Exception as e:
            print(f"❌ HTTP MCP: Authentication failed: {e}")
            return False
    
    async def connect_to_server(self) -> bool:
        """Connect to the HTTP MCP server"""
        try:
            print(f"🔌 HTTP MCP: Connecting to server at {self.base_url}")
            
            # Authenticate first
            if not await self.authenticate():
                return False
            
            # Test connection with health check
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await self.http_client.get(f"{self.base_url}/health", headers=headers)
            response.raise_for_status()
            
            health_data = response.json()
            print(f"✅ HTTP MCP: Connected to server (status: {health_data.get('status')})")
            
            # Get available tools
            response = await self.http_client.get(f"{self.base_url}/tools", headers=headers)
            response.raise_for_status()
            
            tools_data = response.json()
            self.tools_cache = tools_data
            
            print(f"🛠️  HTTP MCP: Retrieved {len(self.tools_cache)} tools")
            for tool in self.tools_cache:
                print(f"   - {tool.get('name', 'unknown')}")
            
            return True
            
        except Exception as e:
            print(f"❌ HTTP MCP: Failed to connect to server: {e}")
            return False
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool via HTTP API"""
        if not self.access_token:
            if not await self.authenticate():
                raise Exception("Could not authenticate with HTTP MCP server")
        
        call_start = time.time()
        print(f"📞 HTTP MCP: Calling tool '{tool_name}' via HTTP")
        print(f"🔧 DEBUG: Tool arguments: {arguments}")
        
        # Inject context information
        context = get_mcp_context()
        
        request_data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "tenant_id": context.get('tenantId'),
            "user_id": context.get('userId'),
            "thread_id": context.get('thread_id')
        }
        
        print(f"🔧 DEBUG HTTP CLIENT: Making request to {self.base_url}/tools/call")
        print(f"🔧 DEBUG HTTP CLIENT: Request data: {request_data}")
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await self.http_client.post(
                f"{self.base_url}/tools/call",
                json=request_data,
                headers=headers
            )
            response.raise_for_status()
            
            result_data = response.json()
            call_time = (time.time() - call_start) * 1000
            
            if result_data.get("success"):
                print(f"✅ HTTP MCP: Tool call completed in {call_time:.2f}ms")
                return result_data.get("result")
            else:
                error_msg = result_data.get("error", "Unknown error")
                print(f"❌ HTTP MCP: Tool call failed in {call_time:.2f}ms: {error_msg}")
                raise Exception(error_msg)
                
        except Exception as e:
            call_time = (time.time() - call_start) * 1000
            print(f"❌ HTTP MCP: Tool call failed in {call_time:.2f}ms: {e}")
            raise
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools from HTTP server"""
        if not self.tools_cache:
            if not await self.connect_to_server():
                raise Exception("Could not connect to HTTP MCP server to get tools")
        
        # Convert HTTP server tool format to expected MCP format
        mcp_tools = []
        for tool in self.tools_cache:
            mcp_tool = {
                'name': tool.get('name'),
                'description': tool.get('description'),
                'input_schema': tool.get('input_schema', {}),
                'parameters': tool.get('parameters', {})  # ← PRESERVE parameters for SharedMCP client
            }
            mcp_tools.append(mcp_tool)
        
        return mcp_tools
    
    async def cleanup(self):
        """Clean up HTTP client"""
        print("🔄 HTTP MCP: Cleaning up HTTP client...")
        if self.http_client:
            await self.http_client.aclose()
        self.access_token = None
        self.tools_cache = None

class SharedMCPClient:
    """Enhanced MCP client with HTTP and direct server support"""
    
    def __init__(self):
        self.http_client: Optional[HTTPMCPClient] = None
        self.direct_server = None
        self.use_http = os.getenv("MCP_USE_HTTP", "false").lower() == "true"
        self.tools_cache: Optional[List] = None
        
        # Legacy stdio support
        self.server_process: Optional[subprocess.Popen] = None
        self.client: Optional[MultiServerMCPClient] = None
        self.server_ready = False
        
    async def start_shared_server(self) -> bool:
        """Start the shared MCP server as a background process"""
        if self.server_process and self.server_process.poll() is None:
            print("🔄 ENHANCED MCP: Shared server already running")
            return True
            
        print("🚀 ENHANCED MCP: Starting shared server process...")
        self.server_start_time = time.time()
        
        try:
            # Start the shared server with correct working directory
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            server_path = os.path.join(os.path.dirname(__file__), "mcp_server.py")
            
            print(f"🚀 ENHANCED MCP: Starting server from {project_root}")
            
            self.server_process = subprocess.Popen(
                ["python3", server_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=project_root,  # Set correct working directory
                preexec_fn=os.setsid  # Create new process group for clean shutdown
            )
            
            # Wait for server to be ready (give it time to initialize)
            await asyncio.sleep(2.0)  # Allow server startup time
            
            if self.server_process.poll() is None:
                startup_time = (time.time() - self.server_start_time) * 1000
                print(f"✅ ENHANCED MCP: Shared server started in {startup_time:.2f}ms (PID: {self.server_process.pid})")
                self.server_ready = True
                return True
            else:
                stdout, stderr = self.server_process.communicate()
                print(f"❌ ENHANCED MCP: Server failed to start")
                print(f"   stdout: {stdout}")
                print(f"   stderr: {stderr}")
                return False
                
        except Exception as e:
            print(f"❌ ENHANCED MCP: Failed to start shared server: {e}")
            return False
    
    async def connect_to_server(self) -> bool:
        """Connect to either HTTP or direct server based on configuration"""
        if self.use_http:
            print("🌐 ENHANCED MCP: Using HTTP MCP server")
            self.http_client = HTTPMCPClient()
            return await self.http_client.connect_to_server()
        else:
            print("🔗 ENHANCED MCP: Using direct MCP server")
            try:
                from src.app.tools.mcp_server import get_cached_server_instance
                self.direct_server = await get_cached_server_instance()
                
                if not self.direct_server:
                    print("❌ ENHANCED MCP: No direct server instance available")
                    return False
                
                tools_info = self.direct_server.get_available_tools()
                self.tools_cache = tools_info if isinstance(tools_info, list) else []
                
                print(f"🛠️  ENHANCED MCP: Connected to direct server with {len(self.tools_cache)} tools")
                return True
                
            except Exception as e:
                print(f"❌ ENHANCED MCP: Failed to connect to direct server: {e}")
                return False
    
    async def get_tools(self):
        """Get LangChain-compatible tools from the shared MCP server."""
        try:
            if self.use_http and self.http_client:
                print("🔧 ENHANCED MCP: Getting tools from HTTP server")
                tools_list = await self.http_client.get_tools()
            else:
                print("🔧 ENHANCED MCP: Getting tools from direct server")
                from src.app.tools.mcp_server import get_cached_server_instance
                server_instance = await get_cached_server_instance()
                tools_list = server_instance.get_available_tools()
            
            if not tools_list:
                print("❌ ENHANCED MCP: No tools available from direct server")
                return []
            
            # Convert list tools to LangChain compatible tools
            langchain_tools = []
            
            for tool_dict in tools_list:
                try:
                    tool_name = tool_dict.get('name')
                    if not tool_name:
                        print("❌ ENHANCED MCP: Tool missing name, skipping")
                        continue
                        
                    print(f"🔄 ENHANCED MCP: Converting tool {tool_name}")
                    
                    # Create a proper tool function with closure to capture tool_name and self reference
                    def create_tool_function(captured_tool_name, client_instance):
                        async def tool_execution(*args, **kwargs):
                            """Execute tool through context-aware call_tool method."""
                            print(f"🚀 TOOL EXECUTION: Calling {captured_tool_name} with args={args}, kwargs={kwargs}")
                            print(f"🔧 DEBUG: INITIAL - args type: {type(args)}, len: {len(args)}")
                            print(f"🔧 DEBUG: INITIAL - kwargs type: {type(kwargs)}, keys: {list(kwargs.keys()) if kwargs else 'None'}")
                            print(f"🔧 DEBUG: INITIAL - kwargs content: {kwargs}")
                            
                            # Special case: if LangGraph passes parameters directly as kwargs (which it should)
                            if captured_tool_name == "bank_transfer" and not args and kwargs:
                                # Check if we have the expected bank_transfer parameters directly in kwargs
                                expected_params = ["fromAccount", "toAccount", "amount"]
                                has_direct_params = any(param in kwargs for param in expected_params)
                                print(f"🔧 DEBUG: bank_transfer direct kwargs check - has_direct_params: {has_direct_params}")
                                if has_direct_params:
                                    print(f"🔧 DEBUG: bank_transfer using direct kwargs - parameters already correct")
                                    # Parameters are already in the right place, no mapping needed
                                    pass
                            
                            # Enhanced parameter mapping for tools with specific parameter needs
                            if captured_tool_name == "bank_balance" and args and not kwargs.get("account_number"):
                                kwargs["account_number"] = args[0]
                                print(f"🔧 DEBUG: Fixed bank_balance args - account_number: {args[0]}")
                            
                            elif captured_tool_name == "get_offer_information" and (
                                (args and not kwargs) or 
                                (kwargs.get('args') and len(args) == 0)
                            ):
                                # Map positional args to expected parameters
                                actual_args = args if args else kwargs.get('args', ())
                                if len(actual_args) >= 1:
                                    kwargs["prompt"] = actual_args[0]
                                if len(actual_args) >= 2:
                                    kwargs["type"] = actual_args[1]
                                # Remove the 'args' key if it exists
                                kwargs.pop('args', None)
                                print(f"🔧 DEBUG: Fixed get_offer_information args - prompt: {kwargs.get('prompt', 'N/A')}, type: {kwargs.get('type', 'N/A')}")
                            
                            elif captured_tool_name == "bank_transfer" and (
                                (args and not kwargs) or 
                                (kwargs.get('args') and len(args) == 0)
                            ):
                                # Map positional args to bank transfer parameters
                                actual_args = args if args else kwargs.get('args', ())
                                param_names = ["fromAccount", "toAccount", "amount", "tenantId", "userId", "thread_id"]
                                for i, arg in enumerate(actual_args[:len(param_names)]):
                                    kwargs[param_names[i]] = arg
                                # Remove the 'args' key if it exists
                                kwargs.pop('args', None)
                                print(f"🔧 DEBUG: Fixed bank_transfer args - mapped {len(actual_args)} parameters")
                            
                            elif captured_tool_name == "bank_transfer" and not args and (not kwargs or not any(k for k in kwargs.keys() if k != 'args')):
                                # Handle case where bank_transfer is called with no meaningful arguments
                                print(f"🔧 DEBUG: bank_transfer called with no arguments - this suggests the agent isn't providing required parameters")
                                print(f"🔧 DEBUG: The agent should provide: fromAccount, toAccount, amount, tenantId, userId, thread_id")
                                print(f"🔧 DEBUG: This is likely a prompt/instruction issue with the LangGraph agent")
                                # We can't fix this here - the agent needs to provide the transfer details
                                # Let it fall through to call_tool which will return an appropriate error
                            
                            elif captured_tool_name == "get_transaction_history" and (
                                (args and not kwargs) or 
                                (kwargs.get('args') and len(args) == 0)
                            ):
                                # Map positional args to transaction history parameters
                                actual_args = args if args else kwargs.get('args', ())
                                param_names = ["account_number", "start_date", "end_date", "tenantId", "userId"]
                                for i, arg in enumerate(actual_args[:len(param_names)]):
                                    kwargs[param_names[i]] = arg
                                # Remove the 'args' key if it exists
                                kwargs.pop('args', None)
                                print(f"🔧 DEBUG: Fixed get_transaction_history args - mapped {len(actual_args)} parameters")
                            
                            elif captured_tool_name == "calculate_monthly_payment" and (
                                (args and not kwargs) or 
                                (kwargs.get('args') and len(args) == 0)
                            ):
                                # Map positional args to loan calculation parameters
                                actual_args = args if args else kwargs.get('args', ())
                                if len(actual_args) >= 1:
                                    kwargs["loan_amount"] = actual_args[0]
                                if len(actual_args) >= 2:
                                    kwargs["years"] = actual_args[1]
                                # Remove the 'args' key if it exists
                                kwargs.pop('args', None)
                                print(f"🔧 DEBUG: Fixed calculate_monthly_payment args - loan_amount: {kwargs.get('loan_amount')}, years: {kwargs.get('years')}")
                            
                            elif captured_tool_name == "create_account" and (
                                (args and not kwargs) or 
                                (kwargs.get('args') and len(args) == 0)
                            ):
                                # Map positional args to create account parameters
                                actual_args = args if args else kwargs.get('args', ())
                                param_names = ["account_holder", "balance", "tenantId", "userId"]
                                for i, arg in enumerate(actual_args[:len(param_names)]):
                                    kwargs[param_names[i]] = arg
                                # Remove the 'args' key if it exists
                                kwargs.pop('args', None)
                                print(f"🔧 DEBUG: Fixed create_account args - mapped {len(actual_args)} parameters")
                            
                            elif captured_tool_name == "service_request" and (
                                (args and not kwargs) or 
                                (kwargs.get('args') and len(args) == 0)
                            ):
                                # Map positional args to service request parameters
                                actual_args = args if args else kwargs.get('args', ())
                                param_names = ["recipientPhone", "recipientEmail", "requestSummary", "tenantId", "userId"]
                                for i, arg in enumerate(actual_args[:len(param_names)]):
                                    kwargs[param_names[i]] = arg
                                # Remove the 'args' key if it exists
                                kwargs.pop('args', None)
                                print(f"🔧 DEBUG: Fixed service_request args - mapped {len(actual_args)} parameters")
                            
                            # Generic fallback for other tools with single parameter
                            elif args and not kwargs:
                                if len(args) == 1 and captured_tool_name not in ["transfer_to_sales_agent", "transfer_to_customer_support_agent", "transfer_to_transactions_agent", "create_account", "health_check"]:
                                    kwargs["input"] = args[0]
                                    print(f"🔧 DEBUG: Generic parameter mapping for {captured_tool_name} - input: {args[0]}")
                            
                            print(f"🔧 DEBUG: Final arguments passed: {kwargs}")
                            
                            # 🔧 CRITICAL FIX: Use context-aware call_tool instead of direct server call
                            result = await client_instance.call_tool(captured_tool_name, kwargs)
                            print(f"🔧 DEBUG: tool_execution received result: {result} (type: {type(result)})")
                            return result
                        
                        # Set proper name attribute for LangChain compatibility
                        tool_execution.__name__ = captured_tool_name
                        return tool_execution
                    
                    # Create the actual tool function with self reference for context injection
                    tool_func = create_tool_function(tool_name, self)
                    
                    # Get parameter schema if available
                    parameters = tool_dict.get('parameters', {})
                    print(f"🔧 DEBUG: Processing tool {tool_name}, parameters: {parameters}")
                    
                    # Create StructuredTool with proper parameter schema for tools that need parameters
                    if tool_name == "bank_balance" and parameters:
                        # Bank balance tool with account_number parameter
                        from pydantic import BaseModel, Field
                        
                        class BankBalanceInput(BaseModel):
                            account_number: str = Field(description="The account number to check balance for (e.g., 'Acc001', '123', 'ABC123')")
                        
                        structured_tool = StructuredTool.from_function(
                            coroutine=tool_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}'),
                            args_schema=BankBalanceInput
                        )
                    
                    elif tool_name == "get_offer_information" and parameters:
                        # Offer information tool with prompt and type parameters
                        from pydantic import BaseModel, Field
                        
                        class OfferInfoInput(BaseModel):
                            prompt: str = Field(description="The user's query about banking offers and products")
                            type: str = Field(default="", description="Type of offer (optional, e.g., 'credit_card', 'loan', 'savings')")
                        
                        structured_tool = StructuredTool.from_function(
                            coroutine=tool_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}'),
                            args_schema=OfferInfoInput
                        )
                    
                    elif tool_name == "bank_transfer" and parameters:
                        print(f"🔧 DEBUG: Creating WRAPPER FUNCTION for bank_transfer tool with parameters: {parameters}")
                        # Bank transfer tool with required parameters - create proper function signature
                        # Use closure to capture self reference
                        def create_bank_transfer_wrapper(client_ref):
                            async def bank_transfer_wrapper(fromAccount: str, toAccount: str, amount: float, tenantId: str, userId: str, thread_id: str):
                                """Bank transfer wrapper with proper Pydantic signature"""
                                print(f"🚀 BANK_TRANSFER_WRAPPER: Called with fromAccount={fromAccount}, toAccount={toAccount}, amount={amount}")
                                kwargs = {
                                    "fromAccount": fromAccount,
                                    "toAccount": toAccount, 
                                    "amount": amount,
                                    "tenantId": tenantId,
                                    "userId": userId,
                                    "thread_id": thread_id
                                }
                                try:
                                    print(f"🔧 BANK_TRANSFER_WRAPPER: Calling client_ref.call_tool with kwargs: {kwargs}")
                                    result = await client_ref.call_tool("bank_transfer", kwargs)
                                    print(f"🔧 BANK_TRANSFER_WRAPPER: Got result: {result}")
                                    return result
                                except Exception as e:
                                    print(f"❌ BANK_TRANSFER_WRAPPER: Exception occurred: {e}")
                                    raise
                            return bank_transfer_wrapper
                        
                        # Create wrapper with proper client reference
                        bank_transfer_func = create_bank_transfer_wrapper(self)
                        
                        from pydantic import BaseModel, Field
                        
                        class BankTransferInput(BaseModel):
                            fromAccount: str = Field(description="Source account number for the transfer")
                            toAccount: str = Field(description="Destination account number for the transfer")
                            amount: float = Field(description="Amount to transfer (positive number)")
                            tenantId: str = Field(description="Tenant ID for the transaction")
                            userId: str = Field(description="User ID for the transaction")
                            thread_id: str = Field(description="Thread ID for the transaction")
                        
                        structured_tool = StructuredTool.from_function(
                            coroutine=bank_transfer_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}'),
                            args_schema=BankTransferInput
                        )
                    
                    elif tool_name == "get_transaction_history" and parameters:
                        # Transaction history tool with proper wrapper function
                        def create_transaction_history_wrapper(client_ref):
                            async def transaction_history_wrapper(account_number: str, start_date: str, end_date: str, tenantId: str, userId: str):
                                """Transaction history wrapper with proper Pydantic signature"""
                                print(f"🚀 TRANSACTION_HISTORY_WRAPPER: Called with account_number={account_number}, start_date={start_date}, end_date={end_date}")
                                kwargs = {
                                    "account_number": account_number,
                                    "start_date": start_date,
                                    "end_date": end_date,
                                    "tenantId": tenantId,
                                    "userId": userId
                                }
                                return await client_ref.call_tool("get_transaction_history", kwargs)
                            return transaction_history_wrapper
                        
                        transaction_history_func = create_transaction_history_wrapper(self)
                        
                        from pydantic import BaseModel, Field
                        
                        class TransactionHistoryInput(BaseModel):
                            account_number: str = Field(description="Account number to get transaction history for")
                            start_date: str = Field(description="Start date for transaction history (YYYY-MM-DD format)")
                            end_date: str = Field(description="End date for transaction history (YYYY-MM-DD format)")
                            tenantId: str = Field(description="Tenant ID")
                            userId: str = Field(description="User ID")
                        
                        structured_tool = StructuredTool.from_function(
                            coroutine=transaction_history_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}'),
                            args_schema=TransactionHistoryInput
                        )
                    
                    elif tool_name == "calculate_monthly_payment" and parameters:
                        from pydantic import BaseModel, Field
                        
                        class MonthlyPaymentInput(BaseModel):
                            loan_amount: float = Field(description="The total loan amount in dollars")
                            years: int = Field(description="The loan term in years")
                        
                        structured_tool = StructuredTool.from_function(
                            coroutine=tool_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}'),
                            args_schema=MonthlyPaymentInput
                        )
                    
                    elif tool_name == "service_request" and parameters:
                        # Service request tool with proper wrapper function
                        def create_service_request_wrapper(client_ref):
                            async def service_request_wrapper(recipientPhone: str, recipientEmail: str, requestSummary: str, tenantId: str, userId: str):
                                """Service request wrapper with proper Pydantic signature"""
                                print(f"🚀 SERVICE_REQUEST_WRAPPER: Called with recipientPhone={recipientPhone}, recipientEmail={recipientEmail}")
                                kwargs = {
                                    "recipientPhone": recipientPhone,
                                    "recipientEmail": recipientEmail,
                                    "requestSummary": requestSummary,
                                    "tenantId": tenantId,
                                    "userId": userId
                                }
                                return await client_ref.call_tool("service_request", kwargs)
                            return service_request_wrapper
                        
                        service_request_func = create_service_request_wrapper(self)
                        
                        from pydantic import BaseModel, Field
                        
                        class ServiceRequestInput(BaseModel):
                            recipientPhone: str = Field(description="Phone number of the recipient for the service request")
                            recipientEmail: str = Field(description="Email address of the recipient for the service request")
                            requestSummary: str = Field(description="Summary description of the service request")
                            tenantId: str = Field(description="Tenant ID for the request")
                            userId: str = Field(description="User ID for the request")
                        
                        structured_tool = StructuredTool.from_function(
                            coroutine=service_request_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}'),
                            args_schema=ServiceRequestInput
                        )
                    
                    elif tool_name == "get_branch_location" and parameters:
                        from pydantic import BaseModel, Field
                        
                        class BranchLocationInput(BaseModel):
                            state: str = Field(description="State name to get branch locations for (e.g., 'California', 'Texas')")
                        
                        structured_tool = StructuredTool.from_function(
                            coroutine=tool_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}'),
                            args_schema=BranchLocationInput
                        )
                    
                    else:
                        print(f"🔧 DEBUG: Using GENERIC tool creation for {tool_name} (no specific schema)")
                        # Standard tool creation for transfer tools and other parameter-less tools
                        structured_tool = StructuredTool.from_function(
                            coroutine=tool_func,
                            name=tool_name,
                            description=tool_dict.get('description', f'Execute {tool_name}')
                        )
                    
                    langchain_tools.append(structured_tool)
                    print(f"✅ ENHANCED MCP: Successfully converted {tool_name} to LangChain tool")
                    if tool_name in ["bank_balance", "get_offer_information", "bank_transfer", "get_transaction_history", "calculate_monthly_payment", "service_request", "get_branch_location"]:
                        print(f"🔧 ENHANCED MCP: {tool_name} schema: {structured_tool.args_schema if hasattr(structured_tool, 'args_schema') else 'No schema'}")
                    
                except Exception as e:
                    print(f"❌ ENHANCED MCP: Failed to convert tool {tool_dict}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"🛠️ ENHANCED MCP: Converted {len(langchain_tools)} tools to LangChain format")
            
            # Verify tools are proper LangChain objects
            for tool in langchain_tools:
                if hasattr(tool, 'name'):
                    print(f"✅ VERIFIED: Tool {tool.name} has proper LangChain structure")
                else:
                    print(f"❌ ERROR: Tool {tool} missing LangChain structure")
            
            return langchain_tools
            
        except Exception as e:
            print(f"❌ ENHANCED MCP: Failed to get tools: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool via HTTP or direct connection"""
        if self.use_http:
            if not self.http_client:
                if not await self.connect_to_server():
                    raise Exception("Could not connect to HTTP MCP server")
            return await self.http_client.call_tool(tool_name, arguments)
        else:
            if not self.direct_server:
                if not await self.connect_to_server():
                    raise Exception("Could not connect to direct MCP server")
            
            # Inject context for direct calls
            context = get_mcp_context()
            tools_needing_context = ['bank_balance', 'bank_transfer', 'get_transaction_history', 'create_account', 'service_request']
            
            if tool_name in tools_needing_context:
                if context.get('tenantId') and 'tenantId' not in arguments:
                    arguments['tenantId'] = context['tenantId']
                if context.get('userId') and 'userId' not in arguments:
                    arguments['userId'] = context['userId']
                if context.get('thread_id') and 'thread_id' not in arguments:
                    arguments['thread_id'] = context['thread_id']
            
            return await self.direct_server.call_tool_directly(tool_name, arguments)
    
    async def cleanup(self):
        """Clean up all connections"""
        print("🔄 ENHANCED MCP: Cleaning up MCP client...")
        
        if self.http_client:
            await self.http_client.cleanup()
            self.http_client = None
        
        if self.direct_server:
            self.direct_server = None
        
        self.tools_cache = None

# Global instance for reuse
_shared_mcp_client: Optional[SharedMCPClient] = None

async def get_shared_mcp_client() -> SharedMCPClient:
    """Get or create the shared MCP client"""
    global _shared_mcp_client
    
    if _shared_mcp_client is None:
        print("🔄 ENHANCED MCP: Initializing shared client...")
        _shared_mcp_client = SharedMCPClient()
        
        if not await _shared_mcp_client.connect_to_server():
            raise Exception("Failed to initialize shared MCP client")
    
    return _shared_mcp_client

async def cleanup_shared_mcp_client():
    """Clean up the shared client"""
    global _shared_mcp_client
    
    if _shared_mcp_client:
        await _shared_mcp_client.cleanup()
        _shared_mcp_client = None
