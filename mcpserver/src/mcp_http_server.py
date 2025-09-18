"""
HTTP MCP Server for Banking Multi-Agent Application

This server exposes MCP tools via HTTP endpoints with enhanced security features:
- JWT authentication with expiration and refresh tokens
- Role-based access control (RBAC)
- Input validation and sanitization
- Rate limiting and audit logging
- Secure CORS configuration
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List
from fastapi import FastAPI, HTTPException, Depends, Security, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
from dotenv import load_dotenv

# Import enhanced security modules
from security import (
    SecurityConfig, UserRole, SecureToolCallRequest, LoginRequest, 
    RefreshTokenRequest, sanitize_dict, validate_account_number,
    validate_amount, RateLimiter, AuditLogger, check_tool_permission
)
from auth import token_manager, TokenData

# Import our Azure service dependencies
from services.azure_cosmos_db import (
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
from services.azure_open_ai import generate_embedding

load_dotenv(override=False)

# FastAPI app setup
app = FastAPI(
    title="Banking MCP Server",
    description="HTTP-based MCP server for banking operations with OAuth2 security",
    version="1.0.0"
)

# Enhanced CORS middleware with security
app.add_middleware(
    CORSMiddleware,
    allow_origins=SecurityConfig.ALLOWED_ORIGINS,  # Specific allowed origins
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Only allow necessary methods
    allow_headers=["Authorization", "Content-Type"],  # Specific headers only
)

# Security and rate limiting
security = HTTPBearer()
rate_limiter = RateLimiter()

# Enhanced Pydantic models with security validation
class ToolCallResponse(BaseModel):
    success: bool = Field(..., description="Whether the tool call was successful")
    result: Any = Field(..., description="Result of the tool call")
    error: Optional[str] = Field(None, description="Error message if the call failed")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")

class ToolInfo(BaseModel):
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    parameters: Dict[str, Any] = Field(..., description="Tool parameter schema")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Health status")
    timestamp: str = Field(..., description="Current timestamp")
    version: str = Field(..., description="Server version")

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token for token renewal")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")

# Enhanced security dependencies
async def verify_token_and_permissions(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> TokenData:
    """
    Verify JWT token and return token data with user information
    """
    token = credentials.credentials
    return token_manager.verify_token(token)

async def check_rate_limit(request: Request):
    """
    Check rate limiting for the client
    """
    client_ip = request.client.host
    if not rate_limiter.is_allowed(client_ip):
        AuditLogger.log_security_event("rate_limit_exceeded", {"ip": client_ip}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

# Tool implementations
async def call_bank_balance(arguments: dict) -> str:
    """Get bank account balance"""
    account_number = arguments.get("account_number", "")
    tenant_id = arguments.get("tenantId", "")
    user_id = arguments.get("userId", "")
    
    print(f"🏦 MCP HTTP: Getting balance for account {account_number}")
    
    if not all([account_number, tenant_id, user_id]):
        return "Error: Missing required parameters (account_number, tenantId, userId)"
    
    try:
        account = fetch_account_by_number(account_number, tenant_id, user_id)
        if account:
            balance = account.get('balance', 0)
            return f"The balance for account number {account_number} is ${balance:.2f}"
        else:
            return f"Account {account_number} not found for the specified user"
    except Exception as e:
        return f"Error retrieving balance: {str(e)}"

async def call_bank_transfer(arguments: dict) -> str:
    """Transfer money between accounts"""
    print(f"🚨🚨🚨 MCP HTTP SERVER: call_bank_transfer ENTRY POINT 🚨🚨🚨")
    print(f"🚨 Arguments received: {arguments}")
    
    from_account = arguments.get("fromAccount", "")
    to_account = arguments.get("toAccount", "")
    amount = arguments.get("amount", 0)
    tenant_id = arguments.get("tenantId", "")
    user_id = arguments.get("userId", "")
    thread_id = arguments.get("thread_id", "")
    
    print(f"🏦 MCP HTTP: Transfer ${amount} from {from_account} to {to_account}")
    print(f"🔧 DEBUG: bank_transfer arguments: {arguments}")
    print(f"🔧 DEBUG: Extracted values - from_account='{from_account}', to_account='{to_account}', amount={amount} (type: {type(amount)}), tenant_id='{tenant_id}', user_id='{user_id}', thread_id='{thread_id}'")
    
    # Check each parameter individually for debugging
    missing_params = []
    if not from_account:
        missing_params.append("fromAccount")
    if not to_account:
        missing_params.append("toAccount") 
    if not tenant_id:
        missing_params.append("tenantId")
    if not user_id:
        missing_params.append("userId")
    if not thread_id:
        missing_params.append("thread_id")
    if amount <= 0:
        missing_params.append(f"amount (got {amount}, type {type(amount)})")
        
    if missing_params:
        error_msg = f"Error: Missing or invalid parameters: {', '.join(missing_params)}"
        print(f"🔧 DEBUG: {error_msg}")
        return error_msg
    
    if not all([from_account, to_account, tenant_id, user_id, thread_id]) or amount <= 0:
        return "Error: Missing required parameters or invalid amount"
    
    try:
        print(f"🔧 DEBUG: Starting bank transfer process...")
        
        # Get source account
        print(f"🔧 DEBUG: Fetching source account {from_account}...")
        source_account = fetch_account_by_number(from_account, tenant_id, user_id)
        if not source_account:
            print(f"🔧 DEBUG: Source account {from_account} not found")
            return f"Source account {from_account} not found"
        
        print(f"🔧 DEBUG: Source account found: {source_account.get('id', 'NO_ID')}")
        print(f"🔧 DEBUG: Source account accountId: {source_account.get('accountId', 'NO_ACCOUNT_ID')}")
        print(f"🔧 DEBUG: from_account parameter: {from_account}")
        
        # Check balance
        current_balance = source_account.get('balance', 0)
        print(f"🔧 DEBUG: Current balance: {current_balance}, transfer amount: {amount}")
        if current_balance < amount:
            return f"Insufficient funds. Current balance: ${current_balance:.2f}"
        
        # Update balances - USE ACCOUNT ID FROM DATABASE, NOT THE PARAMETER!
        source_account_id = source_account.get('accountId', source_account.get('id'))
        new_source_balance = current_balance - amount
        print(f"🔧 DEBUG: Updating source account balance using accountId={source_account_id} (not {from_account})...")
        patch_account_record(tenant_id, source_account_id, new_source_balance)
        print(f"🔧 DEBUG: Source account balance updated successfully")
        
        # Get and update destination account (if exists)
        print(f"🔧 DEBUG: Fetching destination account {to_account}...")
        dest_account = fetch_account_by_number(to_account, tenant_id, user_id)
        if dest_account:
            print(f"🔧 DEBUG: Destination account accountId: {dest_account.get('accountId', 'NO_ACCOUNT_ID')}")
            dest_balance = dest_account.get('balance', 0)
            new_dest_balance = dest_balance + amount
            # USE ACCOUNT ID FROM DATABASE, NOT THE PARAMETER!
            dest_account_id = dest_account.get('accountId', dest_account.get('id'))
            print(f"🔧 DEBUG: Updating destination account balance using accountId={dest_account_id} (not {to_account})...")
            patch_account_record(tenant_id, dest_account_id, new_dest_balance)
            print(f"🔧 DEBUG: Destination account balance updated successfully")
        
        # Create transaction record
        print(f"🔧 DEBUG: Creating transaction record...")
        transaction_number = fetch_latest_transaction_number(from_account) + 1
        transaction_data = {
            "id": f"T{transaction_number:06d}",
            "type": "BankTransaction",
            "accountId": from_account,
            "amount": -amount,
            "balance": new_source_balance,
            "description": f"Transfer to {to_account}",
            "transactionDateTime": datetime.utcnow().isoformat() + "Z",
            "tenantId": tenant_id,
            "userId": user_id,
            "threadId": thread_id
        }
        print(f"🔧 DEBUG: Transaction data: {transaction_data}")
        create_transaction_record(transaction_data)
        print(f"🔧 DEBUG: Transaction record created successfully")
        
        return f"Successfully transferred ${amount:.2f} from {from_account} to {to_account}. New balance: ${new_source_balance:.2f}"
    
    except Exception as e:
        return f"Error processing transfer: {str(e)}"

async def call_get_transaction_history(arguments: dict) -> str:
    """Get transaction history for an account"""
    account_number = arguments.get("account_number", "")
    start_date = arguments.get("start_date", "")
    end_date = arguments.get("end_date", "")
    tenant_id = arguments.get("tenantId", "")
    user_id = arguments.get("userId", "")
    
    print(f"🏦 MCP HTTP: Getting transaction history for {account_number}")
    
    if not all([account_number, start_date, end_date, tenant_id, user_id]):
        return "Error: Missing required parameters"
    
    try:
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        transactions = fetch_transactions_by_date_range(account_number, start_dt, end_dt)
        
        if not transactions:
            return f"No transactions found for account {account_number} between {start_date} and {end_date}"
        
        history = []
        for transaction in transactions:
            history.append(f"Date: {transaction.get('transactionDateTime', 'N/A')}, "
                         f"Amount: ${transaction.get('amount', 0):.2f}, "
                         f"Description: {transaction.get('description', 'N/A')}, "
                         f"Balance: ${transaction.get('balance', 0):.2f}")
        
        return f"Transaction history for account {account_number}:\n" + "\n".join(history)
    
    except Exception as e:
        return f"Error retrieving transaction history: {str(e)}"

async def call_get_offer_information(arguments: dict) -> str:
    """Get banking offer information"""
    prompt = arguments.get("prompt", "")
    offer_type = arguments.get("type", "savings")
    
    print(f"🏦 MCP HTTP: Getting offer information for '{prompt}'")
    
    if not prompt:
        return "Error: Missing prompt parameter"
    
    try:
        embedding = generate_embedding(prompt)
        results = vector_search(embedding, offer_type)
        
        if not results:
            return f"No offers found for '{prompt}'"
        
        offer_info = []
        for result in results:
            offer_info.append(f"Offer: {result.get('name', 'N/A')} - {result.get('text', 'N/A')}")
        
        return "Available offers:\n" + "\n".join(offer_info)
    
    except Exception as e:
        return f"Error retrieving offer information: {str(e)}"

async def call_create_account(arguments: dict) -> str:
    """Create a new bank account"""
    account_holder = arguments.get("account_holder", "")
    balance = arguments.get("balance", 0)
    tenant_id = arguments.get("tenantId", "")
    user_id = arguments.get("userId", "")
    
    print(f"🏦 MCP HTTP: Creating account for {account_holder}")
    
    if not all([account_holder, tenant_id, user_id]):
        return "Error: Missing required parameters"
    
    try:
        account_number = fetch_latest_account_number() + 1
        account_id = f"A{account_number:06d}"
        
        account_data = {
            "id": account_id,
            "type": "BankAccount",
            "accountId": account_id,
            "accountHolder": account_holder,
            "balance": balance,
            "tenantId": tenant_id,
            "userId": user_id,
            "createdDateTime": datetime.utcnow().isoformat() + "Z"
        }
        
        create_account_record(account_data)
        return f"Successfully created account {account_id} for {account_holder} with initial balance ${balance:.2f}"
    
    except Exception as e:
        return f"Error creating account: {str(e)}"

async def call_service_request(arguments: dict) -> str:
    """Create a service request"""
    recipient_phone = arguments.get("recipientPhone", "")
    recipient_email = arguments.get("recipientEmail", "")
    request_summary = arguments.get("requestSummary", "")
    tenant_id = arguments.get("tenantId", "")
    user_id = arguments.get("userId", "")
    
    print(f"🏦 MCP HTTP: Creating service request")
    
    if not all([recipient_phone, recipient_email, request_summary, tenant_id, user_id]):
        return "Error: Missing required parameters"
    
    try:
        request_id = str(uuid.uuid4())
        request_data = {
            "id": request_id,
            "type": "ServiceRequest",
            "recipientPhone": recipient_phone,
            "recipientEmail": recipient_email,
            "requestSummary": request_summary,
            "tenantId": tenant_id,
            "userId": user_id,
            "createdDateTime": datetime.utcnow().isoformat() + "Z",
            "status": "pending"
        }
        
        create_service_request_record(request_data)
        return f"Service request created successfully with ID: {request_id}"
    
    except Exception as e:
        return f"Error creating service request: {str(e)}"

async def call_get_branch_location(arguments: dict) -> str:
    """Get branch locations by state"""
    state = arguments.get("state", "")
    
    print(f"🏦 MCP HTTP: Getting branch locations for {state}")
    
    if not state:
        return "Error: Missing state parameter"
    
    # Mock branch location data (in production, this would come from a database)
    branch_locations = {
        "california": ["Los Angeles - 123 Main St", "San Francisco - 456 Market St", "San Diego - 789 Beach Ave"],
        "texas": ["Dallas - 321 Elm St", "Houston - 654 Oak Ave", "Austin - 987 Congress St"],
        "new york": ["New York City - 555 Broadway", "Albany - 222 State St", "Buffalo - 111 Main St"]
    }
    
    state_lower = state.lower()
    locations = branch_locations.get(state_lower, [])
    
    if not locations:
        return f"No branch locations found for {state}"
    
    return f"Branch locations in {state}:\n" + "\n".join(locations)

async def call_calculate_monthly_payment(arguments: dict) -> str:
    """Calculate monthly loan payment"""
    try:
        # Convert parameters to proper types (they come as strings from HTTP)
        loan_amount = float(arguments.get("loan_amount", 0))
        years = int(arguments.get("years", 0))
        
        print(f"🏦 MCP HTTP: Calculating monthly payment for ${loan_amount} over {years} years")
        
        if loan_amount <= 0 or years <= 0:
            return "Error: Invalid loan amount or years"
        
        # Use same calculation as local MCP server
        interest_rate = 3.5  # 3.5% annual interest rate (matching local MCP)
        monthly_rate = interest_rate / 100 / 12
        num_payments = years * 12
        
        if monthly_rate == 0:
            monthly_payment = loan_amount / num_payments
        else:
            monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
        
        return f"Monthly payment for ${loan_amount:,.2f} loan over {years} years at {interest_rate}% APR: ${monthly_payment:.2f}"
    
    except (ValueError, TypeError) as e:
        return f"Error: Invalid parameter format - {str(e)}"
    except Exception as e:
        return f"Error calculating monthly payment: {str(e)}"

# Agent transfer functions
async def call_transfer_to_sales_agent(arguments: dict) -> str:
    """Transfer to sales agent"""
    import json
    return json.dumps({"goto": "sales_agent"})

async def call_transfer_to_customer_support_agent(arguments: dict) -> str:
    """Transfer to customer support agent"""
    import json
    return json.dumps({"goto": "customer_support_agent"})

async def call_transfer_to_transactions_agent(arguments: dict) -> str:
    """Transfer to transactions agent"""
    import json
    return json.dumps({"goto": "transactions_agent"})

# Tool registry
TOOL_REGISTRY = {
    "bank_balance": call_bank_balance,
    "bank_transfer": call_bank_transfer,
    "get_transaction_history": call_get_transaction_history,
    "get_offer_information": call_get_offer_information,
    "create_account": call_create_account,
    "service_request": call_service_request,
    "get_branch_location": call_get_branch_location,
    "calculate_monthly_payment": call_calculate_monthly_payment,
    "transfer_to_sales_agent": call_transfer_to_sales_agent,
    "transfer_to_customer_support_agent": call_transfer_to_customer_support_agent,
    "transfer_to_transactions_agent": call_transfer_to_transactions_agent,
}

# Tool definitions for listing
TOOL_DEFINITIONS = [
    {
        "name": "bank_balance",
        "description": "Get the current balance of a user's bank account",
        "parameters": {
            "account_number": {"type": "string", "description": "Account number", "required": True},
            "tenantId": {"type": "string", "description": "Tenant ID", "required": True},
            "userId": {"type": "string", "description": "User ID", "required": True}
        }
    },
    {
        "name": "bank_transfer",
        "description": "Transfer money between bank accounts",
        "parameters": {
            "fromAccount": {"type": "string", "description": "Source account", "required": True},
            "toAccount": {"type": "string", "description": "Destination account", "required": True},
            "amount": {"type": "number", "description": "Transfer amount", "required": True},
            "tenantId": {"type": "string", "description": "Tenant ID", "required": True},
            "userId": {"type": "string", "description": "User ID", "required": True},
            "thread_id": {"type": "string", "description": "Thread ID", "required": True}
        }
    },
    {
        "name": "get_transaction_history",
        "description": "Get transaction history for an account",
        "parameters": {
            "account_number": {"type": "string", "description": "Account number", "required": True},
            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)", "required": True},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)", "required": True},
            "tenantId": {"type": "string", "description": "Tenant ID", "required": True},
            "userId": {"type": "string", "description": "User ID", "required": True}
        }
    },
    {
        "name": "get_offer_information",
        "description": "Get banking offer information",
        "parameters": {
            "prompt": {"type": "string", "description": "Search query", "required": True},
            "type": {"type": "string", "description": "Offer type", "required": False}
        }
    },
    {
        "name": "create_account",
        "description": "Create a new bank account",
        "parameters": {
            "account_holder": {"type": "string", "description": "Account holder name", "required": True},
            "balance": {"type": "number", "description": "Initial balance", "required": True},
            "tenantId": {"type": "string", "description": "Tenant ID", "required": True},
            "userId": {"type": "string", "description": "User ID", "required": True}
        }
    },
    {
        "name": "service_request",
        "description": "Create a customer service request",
        "parameters": {
            "recipientPhone": {"type": "string", "description": "Phone number", "required": True},
            "recipientEmail": {"type": "string", "description": "Email address", "required": True},
            "requestSummary": {"type": "string", "description": "Request summary", "required": True},
            "tenantId": {"type": "string", "description": "Tenant ID", "required": True},
            "userId": {"type": "string", "description": "User ID", "required": True}
        }
    },
    {
        "name": "get_branch_location",
        "description": "Get bank branch locations by state",
        "parameters": {
            "state": {"type": "string", "description": "State name", "required": True}
        }
    },
    {
        "name": "calculate_monthly_payment",
        "description": "Calculate monthly loan payment",
        "parameters": {
            "loan_amount": {"type": "number", "description": "Loan amount", "required": True},
            "years": {"type": "integer", "description": "Loan term in years", "required": True}
        }
    },
    {
        "name": "transfer_to_sales_agent",
        "description": "Transfer to sales agent",
        "parameters": {}
    },
    {
        "name": "transfer_to_customer_support_agent",
        "description": "Transfer to customer support agent",
        "parameters": {}
    },
    {
        "name": "transfer_to_transactions_agent",
        "description": "Transfer to transactions agent",
        "parameters": {}
    }
]

# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0"
    )

@app.get("/tools", response_model=List[ToolInfo])
async def list_tools(
    request: Request,
    token_data: TokenData = Depends(verify_token_and_permissions)
):
    """List available tools based on user permissions"""
    await check_rate_limit(request)
    
    # Filter tools based on user roles
    available_tools = []
    for tool in TOOL_DEFINITIONS:
        tool_name = tool["name"]
        if check_tool_permission(tool_name, token_data.roles):
            available_tools.append(ToolInfo(**tool))
    
    return available_tools

@app.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(
    request: SecureToolCallRequest,
    http_request: Request,
    token_data: TokenData = Depends(verify_token_and_permissions)
):
    """Call a specific tool with enhanced security validation"""
    await check_rate_limit(http_request)
    start_time = time.time()
    
    tool_name = request.tool_name
    client_ip = http_request.client.host
    
    # Check if tool exists
    if tool_name not in TOOL_REGISTRY:
        AuditLogger.log_security_event("invalid_tool_call", {
            "tool_name": tool_name,
            "user_id": token_data.user_id
        }, client_ip)
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found"
        )
    
    # Check if user has permission to call this tool
    if not check_tool_permission(tool_name, token_data.roles):
        AuditLogger.log_security_event("unauthorized_tool_call", {
            "tool_name": tool_name,
            "user_id": token_data.user_id,
            "user_roles": [role.value for role in token_data.roles]
        }, client_ip)
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions to call tool '{tool_name}'"
        )
    
    try:
        # Sanitize and validate arguments
        sanitized_arguments = sanitize_dict(request.arguments)
        
        # Add secure context information - use request values if provided, otherwise fall back to token data
        sanitized_arguments["tenantId"] = request.tenant_id or token_data.tenant_id
        sanitized_arguments["userId"] = request.user_id or token_data.user_id
        if request.thread_id:
            sanitized_arguments["thread_id"] = request.thread_id
        
        # Additional validation for banking-specific fields
        if "account_number" in sanitized_arguments:
            if not validate_account_number(str(sanitized_arguments["account_number"])):
                raise ValueError("Invalid account number format")
        
        if "amount" in sanitized_arguments:
            if not validate_amount(str(sanitized_arguments["amount"])):
                raise ValueError("Invalid amount format")
        
        # Call the tool
        print(f"🚨🚨🚨 HTTP MCP SERVER: About to call tool '{tool_name}' 🚨🚨🚨")
        print(f"🚨 Sanitized arguments: {sanitized_arguments}")
        
        # Also log to file for debugging
        with open("/tmp/mcp_debug.log", "a") as f:
            f.write(f"[{datetime.utcnow()}] HTTP MCP SERVER: About to call tool '{tool_name}'\n")
            f.write(f"[{datetime.utcnow()}] Sanitized arguments: {sanitized_arguments}\n")
        
        tool_function = TOOL_REGISTRY[tool_name]
        print(f"🚨 Tool function: {tool_function}")
        
        result = await tool_function(sanitized_arguments)
        print(f"🚨 Tool result: {result}")
        
        with open("/tmp/mcp_debug.log", "a") as f:
            f.write(f"[{datetime.utcnow()}] Tool result: {result}\n")
        
        execution_time = (time.time() - start_time) * 1000
        
        # Log successful tool call
        AuditLogger.log_tool_call(
            token_data.user_id, 
            token_data.tenant_id, 
            tool_name, 
            True, 
            client_ip
        )
        
        return ToolCallResponse(
            success=True,
            result=result,
            execution_time_ms=execution_time
        )
    
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        
        # Log failed tool call
        AuditLogger.log_tool_call(
            token_data.user_id, 
            token_data.tenant_id, 
            tool_name, 
            False, 
            client_ip
        )
        
        AuditLogger.log_security_event("tool_call_error", {
            "tool_name": tool_name,
            "user_id": token_data.user_id,
            "error": str(e)
        }, client_ip)
        
        return ToolCallResponse(
            success=False,
            result=None,
            error=str(e),
            execution_time_ms=execution_time
        )

# Enhanced authentication endpoints
@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, http_request: Request):
    """
    Authenticate user and return JWT tokens
    In production, integrate with Azure AD or your identity provider
    """
    await check_rate_limit(http_request)
    
    # For development, accept any credentials
    # In production, validate against user database or Azure AD
    user_id = request.username
    tenant_id = request.tenant_id
    client_ip = http_request.client.host
    
    # Simulate authentication (replace with real authentication)
    # In production, verify credentials against user store
    if len(request.password) < 8:
        AuditLogger.log_authentication(user_id, tenant_id, False, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Assign default role (in production, fetch from user service)
    user_roles = [UserRole.CUSTOMER]
    
    # Create tokens
    access_token = token_manager.create_access_token(user_id, tenant_id, user_roles)
    refresh_token = token_manager.create_refresh_token(user_id, tenant_id)
    
    AuditLogger.log_authentication(user_id, tenant_id, True, client_ip)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=SecurityConfig.JWT_EXPIRATION_HOURS * 3600
    )

@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, http_request: Request):
    """
    Refresh access token using refresh token
    """
    await check_rate_limit(http_request)
    
    try:
        new_access_token, new_refresh_token = token_manager.refresh_access_token(request.refresh_token)
        
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=SecurityConfig.JWT_EXPIRATION_HOURS * 3600
        )
    except Exception as e:
        client_ip = http_request.client.host
        AuditLogger.log_security_event("refresh_token_failed", {"error": str(e)}, client_ip)
        raise

@app.post("/auth/logout")
async def logout(token_data: TokenData = Depends(verify_token_and_permissions)):
    """
    Logout user by revoking their token
    """
    token_manager.revoke_token(token_data.jti)
    AuditLogger.log_security_event("user_logout", {"user_id": token_data.user_id})
    return {"message": "Successfully logged out"}

# Development token endpoint (for backward compatibility)
@app.post("/auth/token")
async def get_development_token():
    """
    Development endpoint to get a JWT token
    In production, remove this endpoint and use /auth/login
    """
    # Create development user with customer and agent privileges for testing
    user_roles = [UserRole.CUSTOMER, UserRole.AGENT]
    access_token = token_manager.create_access_token("dev-user", "dev-tenant", user_roles)
    refresh_token = token_manager.create_refresh_token("dev-user", "dev-tenant")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=SecurityConfig.JWT_EXPIRATION_HOURS * 3600
    )

print(f"🚨🚨🚨 MCP HTTP SERVER STARTUP - VERSION WITH DEBUG LOGGING 🚨🚨🚨")
print(f"🚨 Current time: {datetime.utcnow()}")
print(f"🚨 Server loaded successfully with enhanced debug logging")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Starting Banking MCP HTTP Server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)