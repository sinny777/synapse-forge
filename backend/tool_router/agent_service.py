"""
Agent Orchestration Service for Neural Tool Router

This module provides the infrastructure to execute multi-agent scenarios
using BeeAI and LangGraph frameworks, demonstrating how AI agents leverage
NeuralToolRouter for intelligent tool selection and orchestration.
"""

import asyncio
import json
import time
import sys
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, AsyncGenerator, Literal, Optional
from pathlib import Path
from enum import Enum

# Add examples to path for imports
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES_DIR))


class AgentFramework(str, Enum):
    """Supported agent frameworks"""
    BEEAI = "beeai"
    LANGGRAPH = "langgraph"


class EventType(str, Enum):
    """Agent execution event types"""
    SCENARIO_START = "scenario_start"
    AGENT_ACTIVATED = "agent_activated"
    TOOL_RETRIEVAL = "tool_retrieval"
    TOOL_EXECUTION = "tool_execution"
    AGENT_REASONING = "agent_reasoning"
    AGENT_RESPONSE = "agent_response"
    SUPERVISOR_ROUTING = "supervisor_routing"
    SCENARIO_COMPLETE = "scenario_complete"
    ERROR = "error"


@dataclass
class AgentInfo:
    """Information about an agent in the scenario"""
    name: str
    role: str
    description: str
    tools_count: int


@dataclass
class AgentScenario:
    """Defines an agent scenario configuration"""
    id: str
    name: str
    description: str
    framework: AgentFramework
    agents: List[AgentInfo]
    example_query: str
    estimated_duration: int  # seconds
    total_tools: int
    use_case: str
    benefits: List[str]


@dataclass
class AgentEvent:
    """Event emitted during agent execution"""
    type: EventType
    timestamp: float
    data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "data": self.data
        }


class AgentOrchestrator:
    """
    Orchestrates execution of multi-agent scenarios.
    
    This class manages the lifecycle of agent scenarios, streaming
    execution events in real-time for frontend visualization.
    """
    
    def __init__(self):
        """Initialize the orchestrator"""
        self.scenarios = self._load_scenarios()
        self.current_execution: Optional[Dict[str, Any]] = None
    
    def _load_scenarios(self) -> Dict[str, AgentScenario]:
        """Load available agent scenarios"""
        scenarios = {}
        
        # BeeAI Mediclaim Processing Scenario
        scenarios["mediclaim_processing"] = AgentScenario(
            id="mediclaim_processing",
            name="Medical Insurance Claim Processing",
            description="Multi-agent workflow for processing post-hospitalization medical insurance claims using IBM BeeAI framework",
            framework=AgentFramework.BEEAI,
            agents=[
                AgentInfo(
                    name="Policy Agent",
                    role="Insurance Policy Verification",
                    description="Verifies policy details and coverage limits",
                    tools_count=2
                ),
                AgentInfo(
                    name="Billing Agent",
                    role="Hospital Bill Verification",
                    description="Fetches discharge summary and verifies hospital bills",
                    tools_count=2
                ),
                AgentInfo(
                    name="Claim Processing Agent",
                    role="Claim Calculation & Submission",
                    description="Calculates claimable amount and submits the claim",
                    tools_count=2
                )
            ],
            example_query="Process mediclaim for Patient ID 1024 (Policy #POL-999) who had knee replacement surgery",
            estimated_duration=45,
            total_tools=6,
            use_case="Healthcare Insurance",
            benefits=[
                "66% context reduction (6 tools → 2 per agent)",
                "Specialized agents for each workflow step",
                "Context passing between agents",
                "95%+ tool selection accuracy"
            ]
        )
        
        # LangGraph UHNW Banking Scenario
        scenarios["uhnw_banking"] = AgentScenario(
            id="uhnw_banking",
            name="UHNW Private Banking Concierge",
            description="Supervisor-based multi-agent orchestration for Ultra-High-Net-Worth private banking using LangGraph",
            framework=AgentFramework.LANGGRAPH,
            agents=[
                AgentInfo(
                    name="Portfolio Manager",
                    role="Portfolio Analysis",
                    description="Analyzes holdings and performance",
                    tools_count=2
                ),
                AgentInfo(
                    name="Trading Analyst",
                    role="Market Intelligence & Trading",
                    description="Fetches market data and executes trades",
                    tools_count=3
                ),
                AgentInfo(
                    name="Tax & Compliance Officer",
                    role="Tax Optimization & AML",
                    description="Handles tax simulations and compliance checks",
                    tools_count=3
                ),
                AgentInfo(
                    name="Premium Concierge",
                    role="Lifestyle Banking",
                    description="Manages card limits and wire transfers",
                    tools_count=2
                )
            ],
            example_query="Nvidia earnings just came out. How is my tech portfolio? Sell 1000 NVDA shares but check tax impact and harvesting options first. Client UHNW-123.",
            estimated_duration=60,
            total_tools=10,
            use_case="Wealth Management",
            benefits=[
                "70% context reduction (10 tools → 2-3 per agent)",
                "Supervisor-based intelligent routing",
                "Dynamic agent collaboration",
                "Tax-optimized trading workflow"
            ]
        )
        
        return scenarios
    
    def get_scenarios(self) -> List[Dict[str, Any]]:
        """Get list of available scenarios"""
        return [
            {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "framework": scenario.framework.value,
                "agents": [asdict(agent) for agent in scenario.agents],
                "example_query": scenario.example_query,
                "estimated_duration": scenario.estimated_duration,
                "total_tools": scenario.total_tools,
                "use_case": scenario.use_case,
                "benefits": scenario.benefits
            }
            for scenario in self.scenarios.values()
        ]
    
    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific scenario"""
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            return None
        
        return {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "framework": scenario.framework.value,
            "agents": [asdict(agent) for agent in scenario.agents],
            "example_query": scenario.example_query,
            "estimated_duration": scenario.estimated_duration,
            "total_tools": scenario.total_tools,
            "use_case": scenario.use_case,
            "benefits": scenario.benefits
        }
    
    async def execute_scenario(
        self,
        scenario_id: str,
        llm_config: Optional[Dict[str, Any]] = None,
        runtime_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Execute an agent scenario and stream events.
        
        Args:
            scenario_id: ID of the scenario to execute
            llm_config: LLM configuration (model, temperature, etc.)
            runtime_config: Runtime configuration
            
        Yields:
            AgentEvent objects representing execution progress
        """
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            yield AgentEvent(
                type=EventType.ERROR,
                timestamp=time.time(),
                data={"error": f"Scenario '{scenario_id}' not found"}
            )
            return
        
        # Initialize execution tracking
        self.current_execution = {
            "scenario_id": scenario_id,
            "start_time": time.time(),
            "agents_executed": 0,
            "tools_retrieved": 0,
            "tools_executed": 0
        }
        
        # Emit start event
        yield AgentEvent(
            type=EventType.SCENARIO_START,
            timestamp=time.time(),
            data={
                "scenario": self.get_scenario(scenario_id),
                "llm_config": llm_config or {},
                "runtime_config": runtime_config or {}
            }
        )
        
        try:
            # Execute based on framework
            if scenario.framework == AgentFramework.BEEAI:
                async for event in self._execute_beeai_scenario(scenario, llm_config, runtime_config):
                    yield event
            elif scenario.framework == AgentFramework.LANGGRAPH:
                async for event in self._execute_langgraph_scenario(scenario, llm_config, runtime_config):
                    yield event
            
            # Emit completion event
            execution_time = time.time() - self.current_execution["start_time"]
            yield AgentEvent(
                type=EventType.SCENARIO_COMPLETE,
                timestamp=time.time(),
                data={
                    "execution_time": execution_time,
                    "agents_executed": self.current_execution["agents_executed"],
                    "tools_retrieved": self.current_execution["tools_retrieved"],
                    "tools_executed": self.current_execution["tools_executed"],
                    "context_reduction": self._calculate_context_reduction(scenario)
                }
            )
            
        except Exception as e:
            yield AgentEvent(
                type=EventType.ERROR,
                timestamp=time.time(),
                data={
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
        finally:
            self.current_execution = None
    
    async def _execute_beeai_scenario(
        self,
        scenario: AgentScenario,
        llm_config: Optional[Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]]
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute BeeAI-based scenario"""
        # Import BeeAI example module (optional - using mock execution for now)
        # try:
        #     from beeai_mediclaim_processing import multi_agent_orchestrator as beeai_module
        # except ImportError as e:
        #     yield AgentEvent(
        #         type=EventType.ERROR,
        #         timestamp=time.time(),
        #         data={"error": f"Failed to import BeeAI module: {str(e)}"}
        #     )
        #     return
        
        # Emit simulated events for demonstration
        # TODO: Integrate with actual BeeAI module when available
        agents = ["Policy Agent", "Billing Agent", "Claim Processing Agent"]
        
        for i, agent_name in enumerate(agents):
            self.current_execution["agents_executed"] += 1
            
            # Agent activation
            yield AgentEvent(
                type=EventType.AGENT_ACTIVATED,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "agent_role": scenario.agents[i].role,
                    "framework": "beeai"
                }
            )
            
            await asyncio.sleep(0.5)
            
            # Tool retrieval
            tools = self._get_mock_tools_for_agent(agent_name, scenario.id)
            self.current_execution["tools_retrieved"] += len(tools)
            
            yield AgentEvent(
                type=EventType.TOOL_RETRIEVAL,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "tools": tools,
                    "retrieval_method": "hybrid",
                    "top_k": 2
                }
            )
            
            await asyncio.sleep(1.0)
            
            # Tool executions
            for idx, tool in enumerate(tools):
                self.current_execution["tools_executed"] += 1
                
                # Generate mock result based on tool
                tool_result = self._get_mock_tool_result(tool["name"], tool.get("args", {}))
                # Vary execution time slightly
                exec_time = 0.25 + (idx * 0.15)
                
                yield AgentEvent(
                    type=EventType.TOOL_EXECUTION,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_name,
                        "tool_name": tool["name"],
                        "tool_args": tool.get("args", {}),
                        "result": tool_result,
                        "success": True,
                        "execution_time": exec_time
                    }
                )
                
                await asyncio.sleep(0.8)
            
            # Agent response
            response = self._get_mock_agent_response(agent_name, scenario.id)
            yield AgentEvent(
                type=EventType.AGENT_RESPONSE,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "response": response
                }
            )
            
            await asyncio.sleep(0.5)
    
    async def _execute_langgraph_scenario(
        self,
        scenario: AgentScenario,
        llm_config: Optional[Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]]
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute LangGraph-based scenario"""
        # Import LangGraph example module (optional - using mock execution for now)
        # try:
        #     from langgraph_UHNW_banking import multi_agent_orchestrator as langgraph_module
        # except ImportError as e:
        #     yield AgentEvent(
        #         type=EventType.ERROR,
        #         timestamp=time.time(),
        #         data={"error": f"Failed to import LangGraph module: {str(e)}"}
        #     )
        #     return
        
        # Simulated supervisor-based execution for demonstration
        # TODO: Integrate with actual LangGraph module when available
        agents = ["Portfolio Manager", "Tax & Compliance Officer", "Trading Analyst"]
        
        for i, agent_name in enumerate(agents):
            # Supervisor routing
            yield AgentEvent(
                type=EventType.SUPERVISOR_ROUTING,
                timestamp=time.time(),
                data={
                    "from_agent": "Supervisor" if i > 0 else "User",
                    "to_agent": agent_name,
                    "reasoning": f"User query requires {scenario.agents[i].role.lower()}"
                }
            )
            
            await asyncio.sleep(0.5)
            
            self.current_execution["agents_executed"] += 1
            
            # Agent activation
            yield AgentEvent(
                type=EventType.AGENT_ACTIVATED,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "agent_role": scenario.agents[i].role,
                    "framework": "langgraph"
                }
            )
            
            await asyncio.sleep(0.5)
            
            # Tool retrieval
            tools = self._get_mock_tools_for_agent(agent_name, scenario.id)
            self.current_execution["tools_retrieved"] += len(tools)
            
            yield AgentEvent(
                type=EventType.TOOL_RETRIEVAL,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "tools": tools,
                    "retrieval_method": "hybrid",
                    "top_k": len(tools)
                }
            )
            
            await asyncio.sleep(1.0)
            
            # Tool executions
            for idx, tool in enumerate(tools):
                self.current_execution["tools_executed"] += 1
                
                # Generate mock result based on tool
                tool_result = self._get_mock_tool_result(tool["name"], tool.get("args", {}))
                # Vary execution time slightly
                exec_time = 0.3 + (idx * 0.18)
                
                yield AgentEvent(
                    type=EventType.TOOL_EXECUTION,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_name,
                        "tool_name": tool["name"],
                        "tool_args": tool.get("args", {}),
                        "result": tool_result,
                        "success": True,
                        "execution_time": exec_time
                    }
                )
                
                await asyncio.sleep(0.8)
            
            # Agent response
            response = self._get_mock_agent_response(agent_name, scenario.id)
            yield AgentEvent(
                type=EventType.AGENT_RESPONSE,
                timestamp=time.time(),
                data={
                    "agent_name": agent_name,
                    "response": response
                }
            )
            
            await asyncio.sleep(0.5)
    
    def _get_mock_tools_for_agent(self, agent_name: str, scenario_id: str) -> List[Dict[str, Any]]:
        """Get mock tools for demonstration"""
        tools_map = {
            "mediclaim_processing": {
                "Policy Agent": [
                    {"name": "get_policy_details", "score": 0.892, "args": {"policy_id": "POL-999"}},
                    {"name": "check_coverage_limits", "score": 0.854, "args": {"policy_id": "POL-999", "procedure": "knee_replacement"}}
                ],
                "Billing Agent": [
                    {"name": "fetch_discharge_summary", "score": 0.876, "args": {"patient_id": "1024"}},
                    {"name": "verify_hospital_bills", "score": 0.843, "args": {"patient_id": "1024"}}
                ],
                "Claim Processing Agent": [
                    {"name": "calculate_claimable_amount", "score": 0.901, "args": {"policy_id": "POL-999", "total_bill": 285000}},
                    {"name": "submit_mediclaim", "score": 0.867, "args": {"policy_id": "POL-999", "amount": 256500}}
                ]
            },
            "uhnw_banking": {
                "Portfolio Manager": [
                    {"name": "get_portfolio_summary", "score": 0.910, "args": {"client_id": "UHNW-123"}},
                    {"name": "get_unrealized_gains_losses", "score": 0.885, "args": {"client_id": "UHNW-123", "ticker": "NVDA"}}
                ],
                "Tax & Compliance Officer": [
                    {"name": "simulate_capital_gains_tax", "score": 0.923, "args": {"client_id": "UHNW-123", "ticker": "NVDA", "quantity": 1000}},
                    {"name": "get_tax_loss_harvesting_options", "score": 0.897, "args": {"client_id": "UHNW-123"}},
                    {"name": "run_aml_transaction_check", "score": 0.845, "args": {"client_id": "UHNW-123", "amount": 500000}}
                ],
                "Trading Analyst": [
                    {"name": "get_live_market_data", "score": 0.915, "args": {"ticker": "NVDA"}},
                    {"name": "execute_trade", "score": 0.889, "args": {"client_id": "UHNW-123", "ticker": "NVDA", "action": "sell", "quantity": 1000}}
                ]
            }
        }
        
        return tools_map.get(scenario_id, {}).get(agent_name, [])
    
    def _get_mock_agent_response(self, agent_name: str, scenario_id: str) -> str:
        """Get mock agent response for demonstration"""
        responses = {
            "mediclaim_processing": {
                "Policy Agent": "Policy POL-999 is active with comprehensive health coverage. Knee replacement is covered with a limit of ₹300,000. Co-pay: 10%",
                "Billing Agent": "Patient 1024 (John Doe) was hospitalized from Jan 15-22, 2024. Total verified bill: ₹285,000. Breakdown: Surgery ₹200k, Room ₹50k, Medicines ₹25k, Diagnostics ₹10k",
                "Claim Processing Agent": "Calculation: Total Bill ₹285,000 - Co-pay 10% (₹28,500) = Final Claimable ₹256,500. Claim submitted successfully! Reference: CLM-482916. Status: Submitted. Estimated processing: 7 days"
            },
            "uhnw_banking": {
                "Portfolio Manager": "Your tech portfolio is up 18.5% YTD. You currently hold 5,000 shares of NVDA with an average cost basis of $450/share. Current price: $533. Unrealized gain: $415,000",
                "Tax & Compliance Officer": "Selling 1,000 NVDA shares will trigger $83,000 in capital gains. Estimated tax: $19,880 (24% bracket). I found 3 tax loss harvesting opportunities in your portfolio that could offset $45,000 of gains, reducing your tax to $9,120. AML check passed.",
                "Trading Analyst": "NVDA is trading at $533 (+2.3% today) following strong earnings. Market sentiment is positive. Executed sell order for 1,000 shares at market price. Order filled at avg $532.85. Proceeds: $532,850"
            }
        }
        
        return responses.get(scenario_id, {}).get(agent_name, "Agent completed successfully")
    
    def _calculate_context_reduction(self, scenario: AgentScenario) -> float:
        """Calculate context reduction percentage"""
        if scenario.id == "mediclaim_processing":
            return 66.0  # 6 tools -> 2 per agent
        elif scenario.id == "uhnw_banking":
            return 70.0  # 10 tools -> 2-3 per agent
        return 0.0
    
    def _get_mock_tool_result(self, tool_name: str, tool_args: dict) -> dict:
        """Generate mock tool results for demonstration"""
        results_map = {
            "get_policy_details": {
                "policy_id": tool_args.get("policy_id", "POL-999"),
                "status": "active",
                "coverage_type": "comprehensive_health",
                "premium": 45000,
                "sum_insured": 1000000,
                "co_pay": 10,
                "coverage_details": {
                    "hospitalization": True,
                    "surgery": True,
                    "room_rent_limit": 5000
                }
            },
            "check_coverage_limits": {
                "procedure": tool_args.get("procedure", "knee_replacement"),
                "covered": True,
                "limit": 300000,
                "co_pay_percentage": 10
            },
            "fetch_discharge_summary": {
                "patient_id": tool_args.get("patient_id", "1024"),
                "patient_name": "John Doe",
                "admission_date": "2024-01-15",
                "discharge_date": "2024-01-22",
                "diagnosis": "Knee Replacement Surgery",
                "total_bill": 285000
            },
            "verify_hospital_bills": {
                "verified": True,
                "total_amount": 285000,
                "breakdown": {
                    "surgery": 200000,
                    "room_charges": 50000,
                    "medicines": 25000,
                    "diagnostics": 10000
                }
            },
            "calculate_claimable_amount": {
                "total_bill": tool_args.get("total_bill", 285000),
                "co_pay_deduction": 28500,
                "claimable_amount": 256500,
                "calculation": "Total - (Total * 10% co-pay)"
            },
            "submit_mediclaim": {
                "claim_id": "CLM-482916",
                "status": "submitted",
                "amount": tool_args.get("amount", 256500),
                "estimated_processing_days": 7
            },
            "get_portfolio_summary": {
                "client_id": tool_args.get("client_id", "UHNW-123"),
                "total_value": 12500000,
                "ytd_return": 18.5,
                "holdings": [
                    {"ticker": "NVDA", "shares": 5000, "value": 2665000},
                    {"ticker": "AAPL", "shares": 3000, "value": 540000},
                    {"ticker": "MSFT", "shares": 2000, "value": 740000}
                ]
            },
            "get_unrealized_gains_losses": {
                "ticker": tool_args.get("ticker", "NVDA"),
                "shares": 5000,
                "avg_cost": 450,
                "current_price": 533,
                "unrealized_gain": 415000,
                "gain_percentage": 18.4
            },
            "simulate_capital_gains_tax": {
                "ticker": tool_args.get("ticker", "NVDA"),
                "quantity": tool_args.get("quantity", 1000),
                "capital_gain": 83000,
                "tax_rate": 0.24,
                "estimated_tax": 19880
            },
            "get_tax_loss_harvesting_options": {
                "opportunities": [
                    {"ticker": "XYZ", "loss": 25000},
                    {"ticker": "ABC", "loss": 15000},
                    {"ticker": "DEF", "loss": 5000}
                ],
                "total_harvestable_loss": 45000,
                "potential_tax_savings": 10800
            },
            "run_aml_transaction_check": {
                "client_id": tool_args.get("client_id", "UHNW-123"),
                "amount": tool_args.get("amount", 500000),
                "status": "passed",
                "risk_score": 12,
                "flags": []
            },
            "get_live_market_data": {
                "ticker": tool_args.get("ticker", "NVDA"),
                "price": 533,
                "change": 12.3,
                "change_percent": 2.3,
                "volume": 45000000,
                "market_cap": "1.3T"
            },
            "execute_trade": {
                "order_id": "ORD-" + str(int(time.time())),
                "ticker": tool_args.get("ticker", "NVDA"),
                "action": tool_args.get("action", "sell"),
                "quantity": tool_args.get("quantity", 1000),
                "avg_fill_price": 532.85,
                "total_proceeds": 532850,
                "status": "filled"
            }
        }
        
        return results_map.get(tool_name, {"status": "success", "message": f"Tool {tool_name} executed successfully"})

# Made with Bob
