#!/usr/bin/env python3
"""
Simple HTTP MCP Server for Local Testing
Provides basic banking tools without Azure dependencies for testing
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
import time
import uuid
import jwt
from jwt import PyJWTError
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv(override=False)

# FastAPI app setup
app = FastAPI(
    title="Banking MCP HTTP Server (Test)",
    description="HTTP-based Model Context Protocol server for banking operations - Test Version",
    version="1.0.0"
)

# Security
security = HTTPBearer()
SECRET_KEY = os.getenv("MCP_AUTH_SECRET_KEY", "test-secret-key-for-local-development-only")

# Pydantic models
class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    tenant_id: Optional[str] = "test-tenant"
    user_id: Optional[str] = "test-user"

class ToolCallResponse(BaseModel):  
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None

class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]

class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Mock data for testing
MOCK_ACCOUNTS = {
    "12345": {
        "account_number": "12345",
        "balance": 5000.00,
        "account_type": "checking",
        "owner": "John Doe"
    },
    "67890": {
        "account_number": "67890", 
        "balance": 12500.50,
        "account_type": "savings",
        "owner": "Jane Smith"
    }
}

MOCK_TRANSACTIONS = [
    {"id": "tx1", "account": "12345", "amount": -50.00, "description": "Coffee Shop", "date": "2024-01-15"},
    {"id": "tx2", "account": "12345", "amount": 1000.00, "description": "Salary Deposit", "date": "2024-01-14"},
    {"id": "tx3", "account": "67890", "amount": -200.00, "description": "Grocery Store", "date": "2024-01-13"}
]

# Authentication functions
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify JWT token - simplified for testing"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Tool implementations (simplified for testing)
def health_check(**kwargs) -> str:
    """Health check tool"""
    return "Banking MCP HTTP Server is healthy and running!"

def bank_balance(account_number: str, **kwargs) -> str:
    """Get account balance"""
    account = MOCK_ACCOUNTS.get(account_number)
    if not account:
        return f"Account {account_number} not found"
    return f"Account {account_number} balance: ${account['balance']:.2f}"

def bank_transfer(from_account: str, to_account: str, amount: float, **kwargs) -> str:
    """Transfer money between accounts"""
    from_acc = MOCK_ACCOUNTS.get(from_account)
    to_acc = MOCK_ACCOUNTS.get(to_account)
    
    if not from_acc:
        return f"Source account {from_account} not found"
    if not to_acc:
        return f"Destination account {to_account} not found"
    if from_acc['balance'] < amount:
        return f"Insufficient funds in account {from_account}"
    
    # Simulate transfer
    from_acc['balance'] -= amount
    to_acc['balance'] += amount
    
    return f"Successfully transferred ${amount:.2f} from {from_account} to {to_account}"

def get_transaction_history(account_number: str, days: int = 30, **kwargs) -> str:
    """Get transaction history"""
    account = MOCK_ACCOUNTS.get(account_number)
    if not account:
        return f"Account {account_number} not found"
    
    transactions = [tx for tx in MOCK_TRANSACTIONS if tx['account'] == account_number]
    if not transactions:
        return f"No transactions found for account {account_number}"
    
    result = f"Transaction history for account {account_number}:\n"
    for tx in transactions:
        result += f"- {tx['date']}: ${tx['amount']:.2f} - {tx['description']}\n"
    
    return result

def calculate_monthly_payment(loan_amount: float, years: int, interest_rate: float = 3.5, **kwargs) -> str:
    """Calculate monthly loan payment"""
    monthly_rate = interest_rate / 100 / 12
    num_payments = years * 12
    
    if monthly_rate == 0:
        monthly_payment = loan_amount / num_payments
    else:
        monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
    
    return f"Monthly payment for ${loan_amount:,.2f} loan over {years} years at {interest_rate}% APR: ${monthly_payment:.2f}"

def get_branch_location(state: str, **kwargs) -> str:
    """Get branch locations by state"""
    branches = {
        "California": ["San Francisco - 123 Market St", "Los Angeles - 456 Sunset Blvd", "San Diego - 789 Harbor Dr"],
        "New York": ["New York City - 321 Broadway", "Buffalo - 654 Main St", "Albany - 987 State St"],
        "Texas": ["Houston - 111 Main St", "Dallas - 222 Commerce St", "Austin - 333 Congress Ave"]
    }
    
    state_branches = branches.get(state, [])
    if not state_branches:
        return f"No branches found in {state}"
    
    result = f"Branch locations in {state}:\n"
    for branch in state_branches:
        result += f"- {branch}\n"
    
    return result

def transfer_to_sales_agent(**kwargs) -> str:
    """Transfer to sales agent"""
    return "Transferring you to our sales agent. Please hold while we connect you with a specialist who can help with loan applications and investment products."

def transfer_to_support_agent(**kwargs) -> str:
    """Transfer to support agent"""
    return "Transferring you to our support agent. Please hold while we connect you with a technical support specialist."

# Tool registry
TOOLS = {
    "health_check": {
        "function": health_check,
        "description": "Check if the MCP server is healthy",
        "input_schema": {
            "type": "object", 
            "properties": {},
            "required": []
        }
    },
    "bank_balance": {
        "function": bank_balance,
        "description": "Get the current balance of a bank account",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_number": {"type": "string", "description": "The account number to check"}
            },
            "required": ["account_number"]
        }
    },
    "bank_transfer": {
        "function": bank_transfer,
        "description": "Transfer money between bank accounts",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_account": {"type": "string", "description": "Source account number"},
                "to_account": {"type": "string", "description": "Destination account number"},
                "amount": {"type": "number", "description": "Amount to transfer"}
            },
            "required": ["from_account", "to_account", "amount"]
        }
    },
    "get_transaction_history": {
        "function": get_transaction_history,
        "description": "Get transaction history for an account",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_number": {"type": "string", "description": "The account number"},
                "days": {"type": "integer", "description": "Number of days to look back", "default": 30}
            },
            "required": ["account_number"]
        }
    },
    "calculate_monthly_payment": {
        "function": calculate_monthly_payment,
        "description": "Calculate monthly payment for a loan",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_amount": {"type": "number", "description": "Loan amount in dollars"},
                "years": {"type": "integer", "description": "Loan term in years"},
                "interest_rate": {"type": "number", "description": "Annual interest rate percentage", "default": 3.5}
            },
            "required": ["loan_amount", "years"]
        }
    },
    "get_branch_location": {
        "function": get_branch_location,
        "description": "Get bank branch locations by state",
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "State name to search for branches"}
            },
            "required": ["state"]
        }
    },
    "transfer_to_sales_agent": {
        "function": transfer_to_sales_agent,
        "description": "Transfer customer to sales agent",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "transfer_to_support_agent": {
        "function": transfer_to_support_agent,
        "description": "Transfer customer to support agent",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

# API Endpoints
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "Banking MCP HTTP Server", "timestamp": datetime.utcnow().isoformat()}

@app.post("/auth/token", response_model=AuthTokenResponse)
async def get_auth_token():
    """Get authentication token for testing"""
    # Create a simple JWT token for testing
    payload = {
        "sub": "test-user",
        "tenant": "test-tenant", 
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return AuthTokenResponse(access_token=token)

@app.get("/tools", response_model=List[ToolInfo])
async def list_tools(user_id: str = Depends(verify_token)):
    """List available tools"""
    return [
        ToolInfo(
            name=name,
            description=tool["description"],
            input_schema=tool["input_schema"]
        )
        for name, tool in TOOLS.items()
    ]

@app.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest, user_id: str = Depends(verify_token)):
    """Execute a tool"""
    try:
        if request.tool_name not in TOOLS:
            raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found")
        
        tool = TOOLS[request.tool_name]
        
        # Add context to arguments
        kwargs = request.arguments.copy()
        kwargs.update({
            "tenant_id": request.tenant_id,
            "user_id": request.user_id or user_id
        })
        
        # Execute tool
        start_time = time.time()
        result = tool["function"](**kwargs)
        execution_time = time.time() - start_time
        
        print(f"[INFO] MCP Server: Executed tool '{request.tool_name}' in {execution_time:.3f}s")
        
        return ToolCallResponse(success=True, result=result)
        
    except Exception as e:
        print(f"[ERROR] MCP Server: Tool execution failed: {str(e)}")
        return ToolCallResponse(success=False, error=str(e))

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Banking MCP HTTP Server",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "authentication": "/auth/token",
            "tools": "/tools",
            "execute": "/tools/call"
        },
        "documentation": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)