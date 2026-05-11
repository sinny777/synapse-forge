"""
Mock executor for testing and demonstration purposes.
"""

import asyncio
import time
from typing import AsyncGenerator, Dict, Any, Optional
from pathlib import Path

from .base_executor import BaseAgentExecutor
from ..common.events import AgentEvent, EventType
from ..common.models import AgentScenario, AgentFramework


class MockExecutor(BaseAgentExecutor):
    """
    Mock executor that simulates agent execution with realistic data.
    
    Provides complete execution flow without requiring real LLM or MCP servers.
    Useful for testing, demos, and development.
    """
    
    def __init__(self, scenario: AgentScenario, examples_dir: Path):
        """Initialize mock executor"""
        super().__init__(scenario, examples_dir)
        self.tools_retrieved = 0
        self.tools_executed = 0
        self.agents_executed = 0
    
    async def initialize(self):
        """Initialize mock executor (no-op for mock)"""
        self.initialized = True
    
    async def execute(
        self,
        user_query: str,
        llm_config: Optional[Dict[str, Any]] = None,
        runtime_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Execute mock scenario with realistic timing and data.
        
        Args:
            user_query: The user's query
            llm_config: LLM configuration (ignored in mock)
            runtime_config: Runtime configuration (ignored in mock)
        
        Yields:
            AgentEvent objects simulating real execution
        """
        if self.scenario.framework == AgentFramework.BEEAI:
            async for event in self._execute_beeai_mock(user_query):
                yield event
        elif self.scenario.framework == AgentFramework.LANGGRAPH:
            async for event in self._execute_langgraph_mock(user_query):
                yield event
    
    async def cleanup(self):
        """Cleanup mock executor (no-op for mock)"""
        self.initialized = False
    
    async def _execute_beeai_mock(self, user_query: str) -> AsyncGenerator[AgentEvent, None]:
        """Execute BeeAI scenario with mock data"""
        
        # Agent 1: Policy Agent
        self.agents_executed += 1
        yield AgentEvent(
            type=EventType.AGENT_ACTIVATED,
            timestamp=time.time(),
            data={
                "agent_name": "Policy Agent",
                "agent_role": "Insurance Policy Specialist",
                "framework": self.scenario.framework.value
            }
        )
        
        await asyncio.sleep(0.5)
        
        # Tool retrieval
        tools = [
            {
                "name": "get_policy_details",
                "description": "Fetch insurance policy information",
                "score": 0.95
            },
            {
                "name": "check_coverage_limits",
                "description": "Verify coverage limits for procedures",
                "score": 0.89
            }
        ]
        self.tools_retrieved += len(tools)
        
        yield AgentEvent(
            type=EventType.TOOL_RETRIEVAL,
            timestamp=time.time(),
            data={
                "agent_name": "Policy Agent",
                "query": "Fetch policy details and check coverage",
                "tools": tools
            }
        )
        
        await asyncio.sleep(1.0)
        
        # Tool executions
        for idx, tool in enumerate(tools):
            self.tools_executed += 1
            tool_result = self._get_mock_tool_result(tool["name"])
            exec_time = 0.25 + (idx * 0.15)
            
            yield AgentEvent(
                type=EventType.TOOL_EXECUTION,
                timestamp=time.time(),
                data={
                    "agent_name": "Policy Agent",
                    "tool_name": tool["name"],
                    "tool_args": {"policy_id": "POL-999"} if "policy" in tool["name"] else {"procedure": "knee_replacement"},
                    "result": tool_result,
                    "success": True,
                    "execution_time": exec_time
                }
            )
            await asyncio.sleep(0.8)
        
        # Agent response
        yield AgentEvent(
            type=EventType.AGENT_RESPONSE,
            timestamp=time.time(),
            data={
                "agent_name": "Policy Agent",
                "response": "Policy POL-999 verified. Coverage limit: $50,000. Knee replacement is covered."
            }
        )
        
        # Agent 2: Billing Agent
        self.agents_executed += 1
        yield AgentEvent(
            type=EventType.AGENT_ACTIVATED,
            timestamp=time.time(),
            data={
                "agent_name": "Billing Agent",
                "agent_role": "Medical Billing Analyst",
                "framework": self.scenario.framework.value
            }
        )
        
        await asyncio.sleep(0.5)
        
        tools = [
            {
                "name": "get_discharge_summary",
                "description": "Retrieve patient discharge summary",
                "score": 0.93
            },
            {
                "name": "verify_hospital_bills",
                "description": "Validate hospital billing details",
                "score": 0.87
            }
        ]
        self.tools_retrieved += len(tools)
        
        yield AgentEvent(
            type=EventType.TOOL_RETRIEVAL,
            timestamp=time.time(),
            data={
                "agent_name": "Billing Agent",
                "query": "Get discharge summary and verify bills",
                "tools": tools
            }
        )
        
        await asyncio.sleep(1.0)
        
        for idx, tool in enumerate(tools):
            self.tools_executed += 1
            tool_result = self._get_mock_tool_result(tool["name"])
            exec_time = 0.35 + (idx * 0.15)
            
            yield AgentEvent(
                type=EventType.TOOL_EXECUTION,
                timestamp=time.time(),
                data={
                    "agent_name": "Billing Agent",
                    "tool_name": tool["name"],
                    "tool_args": {"patient_id": "1024"} if "discharge" in tool["name"] else {"bill_id": "BILL-2024-1024"},
                    "result": tool_result,
                    "success": True,
                    "execution_time": exec_time
                }
            )
            await asyncio.sleep(0.8)
        
        yield AgentEvent(
            type=EventType.AGENT_RESPONSE,
            timestamp=time.time(),
            data={
                "agent_name": "Billing Agent",
                "response": "Hospital bills verified. Total: $42,000. All charges are valid."
            }
        )
        
        # Agent 3: Claim Processing Agent
        self.agents_executed += 1
        yield AgentEvent(
            type=EventType.AGENT_ACTIVATED,
            timestamp=time.time(),
            data={
                "agent_name": "Claim Processing Agent",
                "agent_role": "Claims Processor",
                "framework": self.scenario.framework.value
            }
        )
        
        await asyncio.sleep(0.5)
        
        tools = [
            {
                "name": "calculate_claim_amount",
                "description": "Calculate final claimable amount",
                "score": 0.96
            },
            {
                "name": "submit_claim",
                "description": "Submit insurance claim",
                "score": 0.91
            }
        ]
        self.tools_retrieved += len(tools)
        
        yield AgentEvent(
            type=EventType.TOOL_RETRIEVAL,
            timestamp=time.time(),
            data={
                "agent_name": "Claim Processing Agent",
                "query": "Calculate and submit claim",
                "tools": tools
            }
        )
        
        await asyncio.sleep(1.0)
        
        for idx, tool in enumerate(tools):
            self.tools_executed += 1
            tool_result = self._get_mock_tool_result(tool["name"])
            exec_time = 0.4 + (idx * 0.15)
            
            yield AgentEvent(
                type=EventType.TOOL_EXECUTION,
                timestamp=time.time(),
                data={
                    "agent_name": "Claim Processing Agent",
                    "tool_name": tool["name"],
                    "tool_args": {"policy_id": "POL-999", "total_cost": 42000} if "calculate" in tool["name"] else {"claim_id": "CLM-2024-1024"},
                    "result": tool_result,
                    "success": True,
                    "execution_time": exec_time
                }
            )
            await asyncio.sleep(0.8)
        
        yield AgentEvent(
            type=EventType.AGENT_RESPONSE,
            timestamp=time.time(),
            data={
                "agent_name": "Claim Processing Agent",
                "response": "Claim submitted successfully. Claim ID: CLM-2024-1024. Approved amount: $42,000."
            }
        )
    
    async def _execute_langgraph_mock(self, user_query: str) -> AsyncGenerator[AgentEvent, None]:
        """Execute LangGraph scenario with mock data"""
        
        agents_data = [
            (
                "Portfolio Manager",
                "Investment Portfolio Specialist",
                [
                    {"name": "get_portfolio_summary", "description": "Retrieve portfolio overview", "score": 0.94},
                    {"name": "get_unrealized_gains", "description": "Calculate unrealized gains/losses", "score": 0.90}
                ]
            ),
            (
                "Trading Analyst",
                "Market & Trading Specialist",
                [
                    {"name": "get_market_data", "description": "Fetch live market data", "score": 0.92},
                    {"name": "get_stock_news", "description": "Retrieve stock market news", "score": 0.88},
                    {"name": "execute_trade", "description": "Execute buy/sell trade", "score": 0.85}
                ]
            ),
            (
                "Tax & Compliance Officer",
                "Tax Optimization Specialist",
                [
                    {"name": "simulate_capital_gains", "description": "Simulate capital gains tax", "score": 0.93},
                    {"name": "check_tax_loss_harvesting", "description": "Identify tax loss harvesting opportunities", "score": 0.89},
                    {"name": "run_aml_check", "description": "Run AML transaction check", "score": 0.91}
                ]
            )
        ]
        
        for agent_name, role, tools in agents_data:
            self.agents_executed += 1
            
            yield AgentEvent(
                type=EventType.AGENT_ACTIVATED,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "agent_role": role,
                    "framework": self.scenario.framework.value
                }
            )
            
            await asyncio.sleep(0.5)
            
            self.tools_retrieved += len(tools)
            
            yield AgentEvent(
                type=EventType.TOOL_RETRIEVAL,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "query": f"Tools for {agent_name}",
                    "tools": tools
                }
            )
            
            await asyncio.sleep(1.0)
            
            for idx, tool in enumerate(tools):
                self.tools_executed += 1
                tool_result = self._get_mock_tool_result(tool["name"])
                exec_time = 0.3 + (idx * 0.18)
                
                # Generate realistic tool arguments based on tool name
                tool_args = self._get_mock_tool_args(tool["name"])
                
                yield AgentEvent(
                    type=EventType.TOOL_EXECUTION,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_name,
                        "tool_name": tool["name"],
                        "tool_args": tool_args,
                        "result": tool_result,
                        "success": True,
                        "execution_time": exec_time
                    }
                )
                await asyncio.sleep(0.8)
            
            yield AgentEvent(
                type=EventType.AGENT_RESPONSE,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "response": f"{agent_name} completed analysis successfully."
                }
            )
    
    def _get_mock_tool_result(self, tool_name: str) -> Dict[str, Any]:
        """Generate mock tool results for demonstration"""
        results = {
            "get_policy_details": {
                "policy_id": "POL-999",
                "coverage_limit": 50000,
                "status": "active",
                "holder": "John Doe"
            },
            "check_coverage_limits": {
                "procedure": "knee_replacement",
                "covered": True,
                "limit": 50000,
                "copay": 0
            },
            "get_discharge_summary": {
                "patient_id": "1024",
                "procedure": "knee_replacement",
                "total_cost": 42000,
                "discharge_date": "2024-01-15"
            },
            "verify_hospital_bills": {
                "verified": True,
                "total": 42000,
                "valid_charges": True,
                "itemized_count": 15
            },
            "calculate_claim_amount": {
                "claimable_amount": 42000,
                "deductible": 0,
                "copay": 0,
                "final_amount": 42000
            },
            "submit_claim": {
                "claim_id": "CLM-2024-1024",
                "status": "approved",
                "amount": 42000,
                "processing_time": "2-3 business days"
            },
            "get_portfolio_summary": {
                "total_value": 5000000,
                "ytd_return": 12.5,
                "holdings_count": 25,
                "cash_balance": 250000
            },
            "get_unrealized_gains": {
                "gains": 250000,
                "losses": -50000,
                "net": 200000,
                "percentage": 4.2
            },
            "get_market_data": {
                "sp500": 4500,
                "nasdaq": 14000,
                "dow": 35000,
                "vix": 15.5
            },
            "get_stock_news": {
                "sentiment": "positive",
                "articles": 15,
                "trending_topics": ["earnings", "AI", "tech"]
            },
            "execute_trade": {
                "order_id": "ORD-123",
                "status": "executed",
                "shares": 1000,
                "price": 450.25
            },
            "simulate_capital_gains": {
                "tax_liability": 75000,
                "rate": 0.15,
                "short_term": 25000,
                "long_term": 50000
            },
            "check_tax_loss_harvesting": {
                "opportunities": 3,
                "potential_savings": 15000,
                "recommended_actions": ["Sell STOCK-A", "Buy STOCK-B"]
            },
            "run_aml_check": {
                "status": "clear",
                "risk_score": 0.05,
                "flags": 0,
                "compliance": "passed"
            }
        }
        return results.get(tool_name, {"status": "success", "data": "Tool executed successfully"})
    
    def _get_mock_tool_args(self, tool_name: str) -> Dict[str, Any]:
        """Generate realistic tool arguments based on tool name"""
        args_map = {
            "get_portfolio_summary": {"client_id": "UHNW-123"},
            "get_unrealized_gains": {"client_id": "UHNW-123", "as_of_date": "2024-01-15"},
            "get_market_data": {"symbols": ["SPY", "QQQ", "DIA"]},
            "get_stock_news": {"symbol": "NVDA", "days": 7},
            "execute_trade": {"symbol": "NVDA", "action": "sell", "shares": 1000},
            "simulate_capital_gains": {"client_id": "UHNW-123", "trade_details": {"symbol": "NVDA", "shares": 1000}},
            "check_tax_loss_harvesting": {"client_id": "UHNW-123", "portfolio_id": "PORT-001"},
            "run_aml_check": {"client_id": "UHNW-123", "transaction_amount": 450000}
        }
        return args_map.get(tool_name, {})

# Made with Bob
