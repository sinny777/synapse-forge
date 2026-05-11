"""
Agent Orchestration Service for Neural Tool Router - Refactored

This module provides agent execution using the executor pattern with support
for multiple frameworks (BeeAI, LangGraph) and execution modes (mock, real).
"""

import os
import time
import logging
from dataclasses import asdict
from typing import List, Dict, Any, AsyncGenerator, Optional
from pathlib import Path

# Import from new modular structure
from .common.events import AgentEvent, EventType
from .common.models import AgentInfo, AgentScenario, AgentFramework
from .executors import MockExecutor, LangGraphExecutor, BeeAIExecutor

logger = logging.getLogger(__name__)

# Examples directory for executor initialization
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


class AgentOrchestrator:
    """
    Orchestrates execution of multi-agent scenarios using the executor pattern.
    
    Supports both mock and real execution modes via AGENT_EXECUTION_MODE env var.
    """
    
    def __init__(self):
        """Initialize the orchestrator"""
        self.scenarios = self._load_scenarios()
        self.execution_mode = os.getenv("AGENT_EXECUTION_MODE", "mock").lower()
        logger.info(f"AgentOrchestrator initialized in {self.execution_mode} mode")
        
    def _load_scenarios(self) -> Dict[str, AgentScenario]:
        """Load available agent scenarios"""
        scenarios = {}
        
        # BeeAI Mediclaim Processing Scenario
        scenarios["mediclaim_processing"] = AgentScenario(
            id="mediclaim_processing",
            name="Post-Hospitalization Mediclaim Processing",
            description="Multi-agent system for processing medical insurance claims with policy verification, billing analysis, and claim submission",
            framework=AgentFramework.BEEAI,
            agents=[
                AgentInfo(
                    name="Policy Agent",
                    role="Insurance Policy Specialist",
                    description="Verifies policy details and coverage limits",
                    tools_count=2
                ),
                AgentInfo(
                    name="Billing Agent",
                    role="Medical Billing Analyst",
                    description="Analyzes hospital bills and discharge summaries",
                    tools_count=2
                ),
                AgentInfo(
                    name="Claim Processing Agent",
                    role="Claims Processor",
                    description="Calculates and submits final claim amount",
                    tools_count=2
                )
            ],
            example_query="Process mediclaim for patient 1024 with policy POL-999 for knee replacement surgery",
            estimated_duration=15,
            total_tools=6,
            use_case="Healthcare Insurance",
            benefits=[
                "Automated claim processing",
                "Policy verification",
                "Billing validation",
                "Faster claim approval"
            ]
        )
        
        # LangGraph UHNW Banking Scenario
        scenarios["langgraph_banking"] = AgentScenario(
            id="langgraph_banking",
            name="UHNW Private Banking Concierge",
            description="Multi-agent system for ultra-high-net-worth banking with portfolio management, trading, and tax optimization",
            framework=AgentFramework.LANGGRAPH,
            agents=[
                AgentInfo(
                    name="Portfolio Manager",
                    role="Investment Portfolio Specialist",
                    description="Analyzes portfolio performance and holdings",
                    tools_count=2
                ),
                AgentInfo(
                    name="Trading Analyst",
                    role="Market & Trading Specialist",
                    description="Executes trades and provides market insights",
                    tools_count=3
                ),
                AgentInfo(
                    name="Tax & Compliance Officer",
                    role="Tax Optimization Specialist",
                    description="Handles tax simulations and compliance checks",
                    tools_count=3
                )
            ],
            example_query="Analyze my tech portfolio, sell 1000 NVDA shares, and optimize for tax efficiency",
            estimated_duration=20,
            total_tools=8,
            use_case="Wealth Management",
            benefits=[
                "Portfolio optimization",
                "Tax-efficient trading",
                "Compliance monitoring",
                "Personalized wealth management"
            ]
        )
        
        return scenarios
    
    def list_scenarios(self) -> List[Dict[str, Any]]:
        """List all available scenarios"""
        return [
            {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "framework": scenario.framework.value,
                "agents_count": len(scenario.agents),
                "total_tools": scenario.total_tools,
                "estimated_duration": scenario.estimated_duration,
                "use_case": scenario.use_case,
                "execution_mode": self.execution_mode
            }
            for scenario in self.scenarios.values()
        ]
    
    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific scenario"""
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
            "benefits": scenario.benefits,
            "execution_mode": self.execution_mode
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
            llm_config: LLM configuration (model name, temperature, etc.)
            runtime_config: Runtime configuration options
        
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
        
        # Emit start event
        yield AgentEvent(
            type=EventType.SCENARIO_START,
            timestamp=time.time(),
            data={
                "scenario": self.get_scenario(scenario_id),
                "llm_config": llm_config or {},
                "runtime_config": runtime_config or {},
                "execution_mode": self.execution_mode,
                "user_query": scenario.example_query
            }
        )
        
        # Create appropriate executor
        executor = None
        try:
            logger.info(f"Creating executor for {scenario_id} in {self.execution_mode} mode")
            
            if self.execution_mode == "mock":
                executor = MockExecutor(scenario, EXAMPLES_DIR)
            elif scenario.framework == AgentFramework.BEEAI:
                executor = BeeAIExecutor(scenario, EXAMPLES_DIR)
            elif scenario.framework == AgentFramework.LANGGRAPH:
                executor = LangGraphExecutor(scenario, EXAMPLES_DIR)
            else:
                raise ValueError(f"Unknown framework: {scenario.framework}")
            
            # Initialize executor
            await executor.initialize()
            
            # Track metrics
            start_time = time.time()
            tools_retrieved = 0
            tools_executed = 0
            agents_executed = 0
            
            # Execute and stream events
            async for event in executor.execute(
                scenario.example_query,
                llm_config,
                runtime_config
            ):
                # Track metrics from events
                if event.type == EventType.TOOL_RETRIEVAL:
                    tools_retrieved += len(event.data.get("tools", []))
                elif event.type == EventType.TOOL_EXECUTION:
                    tools_executed += 1
                elif event.type == EventType.AGENT_ACTIVATED:
                    agents_executed += 1
                
                yield event
            
            # Emit completion event
            execution_time = time.time() - start_time
            yield AgentEvent(
                type=EventType.SCENARIO_COMPLETE,
                timestamp=time.time(),
                data={
                    "execution_time": execution_time,
                    "agents_executed": agents_executed,
                    "tools_retrieved": tools_retrieved,
                    "tools_executed": tools_executed,
                    "context_reduction": self._calculate_context_reduction(scenario)
                }
            )
            
        except Exception as e:
            logger.error(f"Execution error: {e}", exc_info=True)
            yield AgentEvent(
                type=EventType.ERROR,
                timestamp=time.time(),
                data={
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
        
        finally:
            # Cleanup executor
            if executor:
                try:
                    await executor.cleanup()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
    
    def _calculate_context_reduction(self, scenario: AgentScenario) -> int:
        """Calculate context reduction percentage"""
        if scenario.framework == AgentFramework.BEEAI:
            return 66
        else:
            return 70


# Create singleton instance
agent_orchestrator = AgentOrchestrator()

# Made with Bob
