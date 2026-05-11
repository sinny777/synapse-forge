# Agent Mode - Multi-Agent Orchestration

## Overview

Agent Mode is a feature in the Neural Tool Router that demonstrates how AI Agents (using IBM BeeAI and LangGraph frameworks) leverage NeuralToolRouter for intelligent multi-agent orchestration with dynamic tool selection.

## Features

### 🤖 Multi-Agent Orchestration
- **BeeAI Framework**: Sequential agent workflow for medical insurance claim processing
- **LangGraph Framework**: Supervisor-based agent coordination for UHNW private banking

### 🎯 Dynamic Tool Selection
- Hybrid retrieval (Dense + BM25) for optimal tool matching
- Context reduction of 66-70% through targeted tool injection
- Real-time tool scoring and selection visualization

### 📊 Real-Time Execution Visualization
- Live agent activation tracking
- Tool retrieval and execution monitoring
- Agent reasoning and response display
- Comprehensive execution metrics

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Angular)                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Run Component (Phase 3: Run Tab)                      │ │
│  │  ├─ Direct LLM Mode (existing)                         │ │
│  │  └─ Agent Mode (NEW)                                   │ │
│  │     ├─ Scenario Selector                               │ │
│  │     ├─ Agent Execution Panel                           │ │
│  │     └─ Metrics Dashboard                               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↕ SSE Streaming
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Agent Orchestration Service                           │ │
│  │  ├─ AgentOrchestrator                                  │ │
│  │  ├─ BeeAI Adapter                                      │ │
│  │  └─ LangGraph Adapter                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  API Endpoints                                         │ │
│  │  ├─ GET  /api/agents/scenarios                        │ │
│  │  ├─ GET  /api/agents/scenarios/{id}                   │ │
│  │  └─ POST /api/agents/execute (SSE)                    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Available Scenarios

### 1. Medical Insurance Claim Processing (BeeAI)

**Framework**: IBM BeeAI  
**Use Case**: Healthcare Insurance  
**Agents**: 3 specialized agents

#### Workflow
1. **Policy Agent**: Verifies insurance policy and coverage limits
2. **Billing Agent**: Fetches discharge summary and verifies hospital bills
3. **Claim Processing Agent**: Calculates claimable amount and submits claim

#### Benefits
- 66% context reduction (6 tools → 2 per agent)
- Specialized agents for each workflow step
- Context passing between agents
- 95%+ tool selection accuracy

#### Example Query
```
Process mediclaim for Patient ID 1024 (Policy #POL-999) 
who had knee replacement surgery
```

### 2. UHNW Private Banking Concierge (LangGraph)

**Framework**: LangGraph  
**Use Case**: Wealth Management  
**Agents**: 4 specialized agents + Supervisor

#### Workflow
1. **Supervisor**: Routes requests to appropriate specialist
2. **Portfolio Manager**: Analyzes holdings and performance
3. **Trading Analyst**: Fetches market data and executes trades
4. **Tax & Compliance Officer**: Handles tax simulations and AML checks
5. **Premium Concierge**: Manages card limits and wire transfers

#### Benefits
- 70% context reduction (10 tools → 2-3 per agent)
- Supervisor-based intelligent routing
- Dynamic agent collaboration
- Tax-optimized trading workflow

#### Example Query
```
Nvidia earnings just came out. How is my tech portfolio? 
Sell 1000 NVDA shares but check tax impact and harvesting 
options first. Client UHNW-123.
```

## Usage

### Accessing Agent Mode

1. Navigate to **Phase 3: Run** tab in the workflow page
2. Scroll down to the **Agent Mode** section
3. Toggle "Show Agent Mode" to enable

### Running a Scenario

1. **Select Scenario**: Choose from dropdown (Mediclaim or Banking)
2. **Review Details**: View scenario description, agents, and benefits
3. **Configure**: Ensure LLM models are configured in Runtime LLM Models section
4. **Execute**: Click "Run Agent Scenario"
5. **Monitor**: Watch real-time agent execution with live updates

### Understanding the Execution Trace

#### Agent Steps
Each agent step shows:
- **Agent Name & Role**: What the agent does
- **Framework Badge**: BeeAI or LangGraph
- **Tools Retrieved**: Top-K tools with relevance scores
- **Tool Executions**: Actual tool calls with timing
- **Agent Response**: Final output from the agent

#### Execution Metrics
- **Total Time**: End-to-end execution duration
- **Agents Used**: Number of agents activated
- **Tools Retrieved**: Total tools fetched by router
- **Tools Executed**: Actual tool invocations
- **Context Reduction**: Percentage of context saved

## API Reference

### Get Agent Scenarios

```http
GET /api/agents/scenarios
```

**Response**:
```json
{
  "status": "success",
  "scenarios": [
    {
      "id": "mediclaim_processing",
      "name": "Medical Insurance Claim Processing",
      "framework": "beeai",
      "agents": [...],
      "total_tools": 6,
      "benefits": [...]
    }
  ]
}
```

### Execute Agent Scenario

```http
POST /api/agents/execute
Content-Type: application/json

{
  "scenario_id": "mediclaim_processing",
  "llm_config": {
    "expansion_model": "ollama/granite4.1:8b",
    "heavy_model": "ollama/granite4.1:8b"
  },
  "runtime_config": {
    "enable_query_expansion": true,
    "max_tool_calls": 10
  }
}
```

**Response**: Server-Sent Events (SSE) stream

**Event Types**:
- `scenario_start`: Scenario initialization
- `agent_activated`: New agent begins work
- `supervisor_routing`: (LangGraph) Supervisor decision
- `tool_retrieval`: Tools fetched by router
- `tool_execution`: Tool invocation
- `agent_reasoning`: Agent thought process
- `agent_response`: Agent output
- `scenario_complete`: Execution finished
- `error`: Error occurred

## Implementation Details

### Backend Components

#### AgentOrchestrator (`tool_router/agent_service.py`)
- Manages scenario lifecycle
- Streams execution events via SSE
- Handles both BeeAI and LangGraph frameworks
- Provides mock execution for demonstration

#### API Endpoints (`main.py`)
- `/api/agents/scenarios`: List available scenarios
- `/api/agents/scenarios/{id}`: Get scenario details
- `/api/agents/execute`: Execute with SSE streaming

### Frontend Components

#### Service Layer (`neural-tool.service.ts`)
- `getAgentScenarios()`: Fetch scenarios
- `executeAgentScenario()`: Execute with SSE handling

#### Run Component (`run.component.ts`)
- Agent mode state management
- Event handling and UI updates
- Real-time execution tracking

#### UI Template (`run.component.html`)
- Scenario selector
- Agent execution timeline
- Metrics dashboard

#### Styling (`run.component.scss`)
- IBM Carbon Design System compliance
- Responsive layout
- Dark theme support

## Configuration

### LLM Models

Agent Mode uses the same LLM configuration as Direct LLM Mode:
- **Expansion Model**: Fast query decomposition
- **Heavy Model**: Agent reasoning and tool execution

Configure in the "Runtime LLM Models" section before running scenarios.

### Runtime Settings

Agent execution respects runtime configuration:
- Query expansion settings
- Tool call limits
- Timeout values
- Logging preferences

## Best Practices

### For Demonstration
1. Start with the Mediclaim scenario (simpler workflow)
2. Enable all trace sections to see full execution
3. Compare metrics with Direct LLM mode
4. Highlight context reduction benefits

### For Development
1. Use mock data for rapid iteration
2. Test SSE streaming with network throttling
3. Validate error handling for failed tool calls
4. Ensure proper cleanup on component destroy

### For Production
1. Replace mock execution with actual agent frameworks
2. Implement proper authentication
3. Add execution history persistence
4. Monitor performance metrics

## Troubleshooting

### Scenario Not Loading
- Check backend is running on port 8000
- Verify CORS configuration
- Check browser console for errors

### Execution Hangs
- Verify LLM models are configured
- Check backend logs for errors
- Ensure MCP servers are accessible

### SSE Connection Issues
- Check network tab for SSE stream
- Verify Content-Type: text/event-stream
- Check for proxy/firewall blocking

### Styling Issues
- Verify Carbon Design System imports
- Check theme variables in SCSS
- Clear browser cache

## Future Enhancements

### Planned Features
- [ ] Real agent framework integration (not mocked)
- [ ] Custom scenario creation
- [ ] Execution history and replay
- [ ] Performance comparison charts
- [ ] Export execution traces
- [ ] Agent collaboration visualization
- [ ] Cost analysis per agent

### Integration Opportunities
- Connect to actual BeeAI agents
- Integrate with LangGraph Cloud
- Add more agent frameworks (CrewAI, AutoGen)
- Support custom MCP servers
- Enable agent debugging mode

## Contributing

To add a new agent scenario:

1. **Define Scenario** in `agent_service.py`:
```python
scenarios["my_scenario"] = AgentScenario(
    id="my_scenario",
    name="My Custom Scenario",
    framework=AgentFramework.BEEAI,
    agents=[...],
    ...
)
```

2. **Implement Execution** in `_execute_*_scenario()` method

3. **Add Mock Data** in helper methods

4. **Test** via API and UI

## Resources

- [IBM BeeAI Framework](https://framework.beeai.dev/)
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Carbon Design System](https://carbondesignsystem.com/)

## License

Same as parent project (Neural Tool Router)

## Support

For issues or questions:
1. Check this documentation
2. Review example implementations in `/examples`
3. Check backend logs for errors
4. Open an issue on GitHub

---

**Last Updated**: 2026-05-11  
**Version**: 1.0.0