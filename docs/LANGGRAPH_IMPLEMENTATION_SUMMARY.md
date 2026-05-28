# LangGraph Agent Execution Implementation Summary

## Overview

This document summarizes the implementation of LangGraph-based agent execution in SynapseForge, replacing the previous sequential tool execution approach with a proper ReAct (Reasoning and Acting) pattern.

## Problem Statement

The original agent execution implementation had several critical issues:

1. **No LLM Reasoning Loop**: Tools were executed sequentially without LLM decision-making
2. **NeuralToolRouter Misuse**: Selected tools semantically but executed all of them instead of letting the LLM choose
3. **No Proper Thinking/Reasoning Output**: UI showed configuration data instead of agent reasoning
4. **Collaborator Issues**: Passed the same prompt to all collaborators instead of contextual delegation
5. **Not Using LangGraph**: Despite being in requirements, LangGraph ReAct pattern was not implemented

## Solution Architecture

### Core Components

#### 1. LangGraphAgentExecutor Service
**File**: `backend/services/langgraph_agent_executor.py`

A new service that implements proper LangGraph-based agent execution with:
- ReAct pattern using `create_react_agent()` from `langgraph.prebuilt`
- Custom event streaming for frontend compatibility
- NeuralToolRouter integration for semantic tool selection
- Proper collaborator delegation with contextual prompts
- MCP and REST tool execution support

#### 2. Integration Point
**File**: `backend/api/agents.py` (Line 1148-1200)

The `/agents/{agent_id}/execute` endpoint now uses `LangGraphAgentExecutor`:

```python
from services.langgraph_agent_executor import LangGraphAgentExecutor

executor = LangGraphAgentExecutor(session)
async for event in executor.execute_agent(
    agent=agent,
    user_prompt=body.user_prompt,
    depth=0,
):
    yield event
```

## Key Features Implemented

### 1. LangGraph ReAct Pattern

The agent now follows the proper ReAct cycle:
1. **Think**: LLM analyzes the task and decides what to do
2. **Act**: LLM selects and calls appropriate tools
3. **Observe**: Tool results are fed back to the LLM
4. **Repeat**: Process continues until task completion

### 2. NeuralToolRouter Integration

- Tools are semantically selected using pgvector similarity search
- Only top-k relevant tools are provided to the LLM
- LLM then decides which of these tools to actually use
- Router selection is visible in execution traces

### 3. Proper Event Streaming

Events are emitted in the format the frontend expects:

```typescript
{
  type: "router" | "thought" | "tool_call" | "tool_result" | "assistant" | "error",
  label: string,
  detail: string,  // Human-readable text, not JSON
  timestamp: string,
  status: "running" | "success" | "error",
  latency_ms?: number,
  metadata?: object
}
```

### 4. Collaborator Delegation

Collaborators are converted to LangChain tools:
- Each collaborator becomes a callable tool
- LLM decides when to delegate and what task to assign
- Contextual prompts are passed to sub-agents
- Results are streamed back through the parent agent

### 5. Tool Execution

Supports multiple tool types:
- **MCP Tools**: Via MCP protocol with stdio/SSE transport
- **REST Tools**: Direct HTTP calls with configurable methods
- **Collaborator Tools**: Recursive agent invocation

## Event Flow Example

For query: "Process mediclaim for patient 1024 with policy POL-999 for knee replacement surgery"

```
1. [reasoning] Initializing Agent: Claim Processing Agent
   → Setting up agent with 8 tools and 2 collaborators

2. [router] Neural Tool Router Selection
   → Selected 5 tools: get_customer_info, get_policy_info, calculate_preauth_amount, validate_claim, create_incident

3. [thought] Agent Thinking
   → Analyzing the request and planning actions...

4. [thought] Agent Reasoning
   → I need to first retrieve customer and policy information for patient 1024 with policy POL-999

5. [tool_call] Tool Call: get_customer_info
   → Calling get_customer_info with arguments: patient_id=1024

6. [tool_result] Tool Result: get_customer_info
   → {"name": "John Doe", "age": 45, "policy_id": "POL-999"}

7. [tool_call] Tool Call: get_policy_info
   → Calling get_policy_info with arguments: policy_id=POL-999

8. [tool_result] Tool Result: get_policy_info
   → {"coverage": "comprehensive", "sum_insured": 500000, "knee_surgery_covered": true}

9. [thought] Agent Reasoning
   → Policy covers knee replacement. Now calculating pre-authorization amount...

10. [tool_call] Tool Call: calculate_preauth_amount
    → Calling calculate_preauth_amount with arguments: procedure=knee_replacement, policy_id=POL-999

11. [tool_result] Tool Result: calculate_preauth_amount
    → {"approved_amount": 250000, "copay": 10000}

12. [assistant] Claim Processing Agent Response
    → Pre-authorization approved for patient 1024 (John Doe) under policy POL-999. 
       Approved amount: ₹250,000 for knee replacement surgery with ₹10,000 copay.
```

## Technical Implementation Details

### LLM Model Configuration

```python
from tool_router.executors.langgraph_executor import LiteLLMChatOpenAI

llm = LiteLLMChatOpenAI(
    model="gpt-4o",  # OpenAI-compatible interface
    litellm_model=f"{provider}/{model_name}",  # Actual model (e.g., watsonx/granite-3.1-8b-instruct)
    openai_api_key="litellm-dummy-key",
    temperature=llm_config.temperature or 0.7,
    max_tokens=llm_config.max_tokens,
)
```

### Tool Conversion

Tools are converted from SynapseForge format to LangChain `StructuredTool`:

```python
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

# Create Pydantic model from tool schema
InputModel = create_model(f"{tool.name}Input", **fields)

# Create LangChain tool
lc_tool = StructuredTool.from_function(
    func=tool_func,
    name=tool.name,
    description=tool.description,
    args_schema=InputModel,
    coroutine=tool_func,
)
```

### Collaborator Tools

```python
class CollaboratorInput(BaseModel):
    task: str = Field(description="The specific task to delegate")

async def delegate_to_collaborator(task: str) -> str:
    """Delegate a task to a collaborator agent"""
    async for event in self.execute_agent(
        agent=collaborator,
        user_prompt=task,  # Contextual prompt, not original
        depth=parent_depth + 1,
    ):
        # Process events...
    return result

tool = StructuredTool.from_function(
    func=delegate_to_collaborator,
    name=f"delegate_to_{collaborator.name}",
    description=collaborator.description,
    args_schema=CollaboratorInput,
)
```

## Configuration Requirements

### Backend Dependencies

All required packages are in `backend/requirements.txt`:
- `langgraph>=0.0.20` - ReAct agent framework
- `langchain>=0.1.0` - Tool abstractions
- `langchain-core>=0.1.0` - Core interfaces
- `langchain-openai>=0.0.5` - OpenAI-compatible LLM
- `litellm>=1.0.0` - Multi-provider LLM support

### Agent Configuration

Agents must have:
- `llm_config_id`: Reference to LLM configuration
- `use_neural_router`: Enable/disable NeuralToolRouter
- `router_model_id`: Embedding model for router (if enabled)
- `router_top_k`: Number of tools to select (default: 5)
- `max_iterations`: Maximum ReAct cycles (default: 10)
- `attached_tool_ids`: Available tools
- `collaborator_agent_ids`: Sub-agents for delegation

## Testing

### Test Query
```
Process mediclaim for patient 1024 with policy POL-999 for knee replacement surgery.
```

### Expected Behavior
1. Agent initializes with proper configuration
2. NeuralToolRouter selects relevant tools
3. LLM reasons about the task
4. LLM calls tools based on reasoning
5. Tool results inform next actions
6. Process repeats until completion
7. Final response is generated

### Verification Points
- ✅ Agent thinking/reasoning visible in UI
- ✅ NeuralToolRouter selection shown
- ✅ Tool calls are LLM-driven, not sequential
- ✅ Tool results feed back into reasoning
- ✅ Collaborators receive contextual prompts
- ✅ Final response is coherent and complete

## Troubleshooting

### Issue: No reasoning output visible
**Cause**: Events not properly formatted for frontend
**Solution**: Ensure `detail` field contains human-readable text, not JSON

### Issue: All tools executed regardless of relevance
**Cause**: Using old sequential execution
**Solution**: Verify `LangGraphAgentExecutor` is being used in `agents.py`

### Issue: Collaborators receive wrong prompts
**Cause**: Passing original user prompt instead of delegation task
**Solution**: LLM now generates contextual task description for each collaborator

### Issue: LangGraph import errors
**Cause**: Missing dependencies
**Solution**: Run `pip install -r backend/requirements.txt`

## Performance Considerations

### Latency
- NeuralToolRouter adds ~50-200ms for tool selection
- LLM reasoning adds ~1-3s per iteration
- Tool execution varies by tool type
- Total execution: 5-30s depending on complexity

### Optimization Strategies
1. **Router Caching**: Cache embeddings for frequently used tools
2. **Parallel Tool Calls**: LangGraph supports parallel execution
3. **Streaming**: Events stream as they occur, improving perceived performance
4. **Early Stopping**: Agent stops when task is complete

## Future Enhancements

1. **Memory Integration**: Add conversation history support
2. **Checkpointing**: Save/resume agent state
3. **Human-in-the-Loop**: Request user input during execution
4. **Multi-Agent Orchestration**: Coordinate multiple agents in parallel
5. **Tool Learning**: Improve router based on execution feedback

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [ReAct Pattern Paper](https://arxiv.org/abs/2210.03629)
- SynapseForge Platform Requirements: `docs/platform/PLATFORM_REQUIREMENTS_V3.md`
- Implementation Tasks: `docs/platform/IMPLEMENTATION_TASKS.md`

## Conclusion

The LangGraph implementation transforms SynapseForge agents from simple tool executors into intelligent reasoning agents that:
- Think before acting
- Select tools based on context
- Learn from tool results
- Delegate tasks appropriately
- Provide transparent reasoning

This aligns with the platform's vision of building enterprise-grade agentic AI systems with proper observability and control.