# Dynamic LangGraph Agent Architecture with Neural Tool Routing

## Overview

This document describes the completely refactored LangGraph agent execution pipeline that implements **dynamic, pre-LLM tool routing** using the `NeuralToolRouter` (implemented as `RouterService`). This architecture replaces the static tool binding approach with a dynamic system where tools are selected per-query BEFORE the LLM is invoked.

## Architecture Components

### 1. Enhanced Agent State (`DynamicAgentState`)

```python
class DynamicAgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    suggested_tools: list[Any]  # NEW: Dynamically selected tools
    agent_config: dict[str, Any]
    depth: int
```

**Key Addition**: The `suggested_tools` field holds the tools returned by the neural router dynamically for each query.

### 2. Execution Flow

```
START
  ↓
neural_routing_node (Pre-LLM)
  ↓
dynamic_llm_node
  ↓
[Conditional Edge]
  ├─→ tool_execution_node → (loop back to dynamic_llm_node)
  └─→ END
```

### 3. Node Descriptions

#### Node 1: `neural_routing_node` (Pre-LLM Routing)

**Purpose**: Select the most relevant tools BEFORE the LLM is invoked.

**Process**:
1. Extract the latest user message from state
2. Call `RouterService.predict()` with the user query
3. Get top-k most relevant tools from the workspace's global registry
4. Filter and rank tools based on semantic similarity
5. Update `state["suggested_tools"]` with selected tools
6. Emit router event with selection metadata

**Key Features**:
- Supports both neural routing (when `agent.use_neural_router=True`) and fallback to attached tools
- Respects `router_top_k` configuration or override
- Caches results in Redis for performance
- Emits detailed router events for observability

#### Node 2: `dynamic_llm_node` (Dynamic Tool Binding)

**Purpose**: Invoke the LLM with ONLY the dynamically selected tools.

**Process**:
1. Retrieve `suggested_tools` from state
2. Convert tools to LangChain format
3. Add collaborator tools (sub-agents)
4. **Dynamically bind** tools to LLM using `llm.bind_tools(langchain_tools)`
5. Inject enhanced system prompt with "Think, Plan, Act" framework
6. Invoke LLM and return response

**Key Features**:
- NO static tool loading - tools are bound per-query
- Enhanced system prompt enforces tool usage
- Supports sub-agent delegation via collaborator tools
- Emits thinking and tool call events

#### Node 3: `dynamic_tool_execution_node`

**Purpose**: Execute tool calls requested by the LLM.

**Process**:
1. Extract tool calls from last AI message
2. Map tool names to the dynamically selected tools in `suggested_tools`
3. Execute each tool call
4. Return tool results as `ToolMessage` objects
5. Loop back to `dynamic_llm_node` for synthesis

**Key Features**:
- Resolves tool calls against the dynamic tool map
- Supports both MCP and REST tools
- Handles errors gracefully
- Emits tool result events

### 4. Conditional Edge Logic

```python
def should_continue(state: DynamicAgentState) -> Literal["continue", "end"]:
    """
    If last message has tool_calls → continue to tool execution
    Otherwise → end
    """
```

## Key Differences from Original Implementation

| Aspect | Original (Static) | New (Dynamic) |
|--------|------------------|---------------|
| Tool Selection | All tools loaded at initialization | Tools selected per-query via NeuralToolRouter |
| Tool Binding | `create_react_agent(llm, ALL_TOOLS)` | `llm.bind_tools(suggested_tools)` per query |
| Graph Structure | Prebuilt ReAct agent | Custom StateGraph with routing node |
| Routing Timing | N/A (static) | Pre-LLM routing node |
| State | Standard messages only | Enhanced with `suggested_tools` |
| Flexibility | Fixed tool set | Dynamic tool set per query |

## Usage Example

```python
from services.langgraph_dynamic_agent_executor import DynamicLangGraphAgentExecutor

# Initialize executor
executor = DynamicLangGraphAgentExecutor(session)

# Execute agent with dynamic routing
async for event in executor.execute_agent(
    agent=agent,
    user_prompt="What's my portfolio performance?",
    router_top_k_override=3,  # Override default top-k
):
    print(event)  # SSE events
```

## Event Stream

The executor emits the following SSE events:

1. **reasoning**: Agent initialization
2. **router**: Neural tool selection results
3. **thought**: Agent thinking with selected tools
4. **tool_call**: Tool invocation details
5. **tool_result**: Tool execution results
6. **assistant**: Final agent response

## Configuration

### Agent Configuration

```python
agent.use_neural_router = True  # Enable neural routing
agent.router_top_k = 5  # Default top-k tools
agent.max_iterations = 10  # Max reasoning loops
```

### Runtime Override

```python
# Override top-k at execution time
router_top_k_override=3
```

## Benefits

1. **Efficiency**: Only relevant tools are loaded and bound per query
2. **Scalability**: Handles large tool registries without performance degradation
3. **Accuracy**: Semantic routing ensures best tool selection
4. **Flexibility**: Easy to add/remove tools without code changes
5. **Observability**: Detailed events for debugging and monitoring
6. **Sub-Agent Support**: Collaborators treated as tools for delegation

## System Prompt Enhancement

The dynamic LLM node injects a "Think, Plan, Act" framework:

```
**Think, Plan, Act Framework:**
1. **Think**: Analyze the user's request and identify what information you need
2. **Plan**: Determine which tools to use and in what order
3. **Act**: Execute the tools to gather information

You MUST use these tools to gather information before providing your final answer.
For delegating to sub-agents (collaborators), use the delegate_to_* tools.
```

## Performance Considerations

- **Redis Caching**: Router predictions are cached for 5 minutes
- **Batch Tool Loading**: Tools are loaded in a single database query
- **Lazy Execution**: Tools are only converted to LangChain format when selected
- **Event Queuing**: Events are queued and flushed efficiently

## Migration Guide

To migrate from the original `LangGraphAgentExecutor` to `DynamicLangGraphAgentExecutor`:

1. Import the new executor:
   ```python
   from services.langgraph_dynamic_agent_executor import DynamicLangGraphAgentExecutor
   ```

2. Replace initialization:
   ```python
   # Old
   executor = LangGraphAgentExecutor(session)
   
   # New
   executor = DynamicLangGraphAgentExecutor(session)
   ```

3. The API remains the same - no changes to execution calls needed!

## Future Enhancements

- [ ] Support for multi-turn routing (re-route on each turn)
- [ ] Tool usage analytics and optimization
- [ ] A/B testing between static and dynamic routing
- [ ] Tool recommendation based on historical usage
- [ ] Parallel tool execution for independent tools

## Troubleshooting

### Issue: Tools not being selected

**Solution**: Ensure `agent.use_neural_router=True` and tools have embeddings in the database.

### Issue: Wrong tools selected

**Solution**: Check tool descriptions and embeddings. Consider fine-tuning the embedding model.

### Issue: Performance degradation

**Solution**: Verify Redis is configured for caching. Check `router_top_k` value.

## References

- Original Implementation: `backend/services/langgraph_agent_executor.py`
- Router Service: `backend/services/router_service.py`
- LangGraph Documentation: https://langchain-ai.github.io/langgraph/

---

**Author**: Bob  
**Date**: 2026-05-28  
**Version**: 1.0.0