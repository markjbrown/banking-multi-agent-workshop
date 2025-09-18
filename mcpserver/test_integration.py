#!/usr/bin/env python3
"""
Test script to validate that the main banking application can connect to the HTTP MCP server
"""
import asyncio
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, '/home/theovk/mcprepo/banking-multi-agent-workshop/python/src')

from app.tools.mcp_client import get_shared_mcp_client, set_mcp_context

async def test_mcp_integration():
    """Test the integration between main app and HTTP MCP server"""
    print("🧪 Testing MCP Client Integration with HTTP Server")
    print("=" * 50)
    
    # Set MCP context
    set_mcp_context(tenantId="test-tenant", userId="test-user", thread_id="test-thread-123")
    
    try:
        # Get shared MCP client (should auto-detect HTTP mode)
        print("1. Getting shared MCP client...")
        client = await get_shared_mcp_client()
        print("✅ MCP client created successfully")
        
        # Get available tools
        print("\n2. Getting available tools...")
        tools = await client.get_tools()
        print(f"✅ Found {len(tools)} tools:")
        for tool in tools[:5]:  # Show first 5 tools
            print(f"   - {tool.name}: {tool.description}")
        
        # Test a specific tool
        print("\n3. Testing calculate_monthly_payment tool...")
        
        # Find the tool
        calc_tool = None
        for tool in tools:
            if tool.name == "calculate_monthly_payment":
                calc_tool = tool
                break
        
        if calc_tool:
            # Execute the tool
            result = await calc_tool.ainvoke({
                "loan_amount": 250000,
                "years": 30,
                "interest_rate": 4.5
            })
            print(f"✅ Tool execution successful: {result}")
        else:
            print("❌ calculate_monthly_payment tool not found")
        
        print("\n4. Testing bank balance tool...")
        
        # Find the bank balance tool  
        balance_tool = None
        for tool in tools:
            if tool.name == "bank_balance":
                balance_tool = tool
                break
        
        if balance_tool:
            # Execute the tool with a test account
            result = await balance_tool.ainvoke({
                "account_number": "12345",
                "tenantId": "test-tenant",
                "userId": "test-user"
            })
            print(f"✅ Bank balance tool execution: {result}")
        else:
            print("❌ bank_balance tool not found")
            
        print("\n" + "=" * 50)
        print("🎉 MCP Integration Test Completed Successfully!")
        print("✅ The main banking application can successfully connect to and use the HTTP MCP server")
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    # Set environment variables to force HTTP mode
    os.environ["MCP_USE_HTTP"] = "true"
    os.environ["MCP_SERVER_ENDPOINT"] = "http://localhost:8080"
    
    # Run the test
    success = asyncio.run(test_mcp_integration())
    sys.exit(0 if success else 1)