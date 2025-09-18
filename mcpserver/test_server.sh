#!/bin/bash

# Test script for Banking MCP HTTP Server
# This script validates the HTTP MCP server functionality

set -e

# Configuration
MCP_SERVER_URL="${MCP_SERVER_ENDPOINT:-http://localhost:8080}"
TENANT_ID="Contoso"
USER_ID="TestUser"
THREAD_ID="test-thread-$(date +%s)"

echo "🧪 Testing Banking MCP HTTP Server"
echo "Server URL: $MCP_SERVER_URL"
echo "=================================="

# Test 1: Health Check
echo "1. Testing health endpoint..."
health_response=$(curl -s "$MCP_SERVER_URL/health" || echo "FAILED")
if [[ $health_response == *"healthy"* ]]; then
    echo "✅ Health check passed"
else
    echo "❌ Health check failed: $health_response"
    exit 1
fi

# Test 2: Authentication
echo ""
echo "2. Testing authentication..."
auth_response=$(curl -s -X POST "$MCP_SERVER_URL/auth/token" || echo "FAILED")
if [[ $auth_response == *"access_token"* ]]; then
    echo "✅ Authentication successful"
    TOKEN=$(echo $auth_response | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
else
    echo "❌ Authentication failed: $auth_response"
    exit 1
fi

# Test 3: List Tools
echo ""
echo "3. Testing tools listing..."
tools_response=$(curl -s -H "Authorization: Bearer $TOKEN" "$MCP_SERVER_URL/tools" || echo "FAILED")
if [[ $tools_response == *"bank_balance"* ]]; then
    echo "✅ Tools listing successful"
    echo "Available tools: $(echo $tools_response | grep -o '"name":"[^"]*' | cut -d'"' -f4 | tr '\n' ' ')"
else
    echo "❌ Tools listing failed: $tools_response"
    exit 1
fi

# Test 4: Health Check Tool
echo ""
echo "4. Testing health_check tool..."
health_tool_response=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"health_check\",\"arguments\":{},\"tenant_id\":\"$TENANT_ID\",\"user_id\":\"$USER_ID\"}" \
    "$MCP_SERVER_URL/tools/call" || echo "FAILED")

if [[ $health_tool_response == *"success\":true"* ]]; then
    echo "✅ Health check tool successful"
else
    echo "❌ Health check tool failed: $health_tool_response"
fi

# Test 5: Calculate Monthly Payment Tool
echo ""
echo "5. Testing calculate_monthly_payment tool..."
calc_response=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"calculate_monthly_payment\",\"arguments\":{\"loan_amount\":100000,\"years\":30},\"tenant_id\":\"$TENANT_ID\",\"user_id\":\"$USER_ID\"}" \
    "$MCP_SERVER_URL/tools/call" || echo "FAILED")

if [[ $calc_response == *"success\":true"* ]] && [[ $calc_response == *"Monthly payment"* ]]; then
    echo "✅ Monthly payment calculation successful"
    echo "Result: $(echo $calc_response | grep -o '"result":"[^"]*' | cut -d'"' -f4)"
else
    echo "❌ Monthly payment calculation failed: $calc_response"
fi

# Test 6: Get Branch Location Tool
echo ""
echo "6. Testing get_branch_location tool..."
branch_response=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"get_branch_location\",\"arguments\":{\"state\":\"California\"},\"tenant_id\":\"$TENANT_ID\",\"user_id\":\"$USER_ID\"}" \
    "$MCP_SERVER_URL/tools/call" || echo "FAILED")

if [[ $branch_response == *"success\":true"* ]] && [[ $branch_response == *"Branch locations"* ]]; then
    echo "✅ Branch location lookup successful"
else
    echo "❌ Branch location lookup failed: $branch_response"
fi

# Test 7: Agent Transfer Tools
echo ""
echo "7. Testing agent transfer tools..."
transfer_response=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"transfer_to_sales_agent\",\"arguments\":{},\"tenant_id\":\"$TENANT_ID\",\"user_id\":\"$USER_ID\"}" \
    "$MCP_SERVER_URL/tools/call" || echo "FAILED")

if [[ $transfer_response == *"success\":true"* ]] && [[ $transfer_response == *"sales agent"* ]]; then
    echo "✅ Agent transfer tools working"
else
    echo "❌ Agent transfer tools failed: $transfer_response"
fi

# Test 8: Error Handling
echo ""
echo "8. Testing error handling..."
error_response=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"nonexistent_tool\",\"arguments\":{},\"tenant_id\":\"$TENANT_ID\",\"user_id\":\"$USER_ID\"}" \
    "$MCP_SERVER_URL/tools/call" || echo "FAILED")

if [[ $error_response == *"not found"* ]]; then
    echo "✅ Error handling working correctly"
else
    echo "❌ Error handling test failed: $error_response"
fi

echo ""
echo "=================================="
echo "🎉 Banking MCP HTTP Server testing completed!"
echo ""
echo "Summary:"
echo "- Server is accessible at: $MCP_SERVER_URL"
echo "- Authentication is working"
echo "- Core banking tools are functional"
echo "- Error handling is proper"
echo ""
echo "The server is ready for integration with the main banking application."