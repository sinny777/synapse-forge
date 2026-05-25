/**
 * NeuralToolRouter — Platform TypeScript Interfaces
 *
 * Mirrors the backend Pydantic schemas for type-safe API communication.
 */

// ========================== WORKSPACE ======================================

export type WorkspaceStatus = 'STOPPED' | 'RUNNING' | 'FAILED';

export interface Workspace {
  id: string;
  name: string;
  description?: string;
  embedding_model: string;
  embedding_dim: number;
  is_default: boolean;
  status: WorkspaceStatus;
  shared_with?: string[];
  created_at: string;
  updated_at: string;
  created_by?: string;
  updated_by?: string;
}

export interface WorkspaceCreate {
  name: string;
  description?: string;
  embedding_model?: string;
  embedding_dim?: number;
}

export interface WorkspaceUpdate {
  name?: string;
  description?: string;
  embedding_model?: string;
  embedding_dim?: number;
}

// ========================== TOOL ===========================================

export type ToolType = 'REST' | 'MCP_SERVER' | 'MCP_TOOL';
export type MCPTransport = 'stdio' | 'sse';
export type MCPServerStatus = 'active' | 'disabled' | 'error';

export interface Tool {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  type: ToolType;
  is_enabled: boolean;
  
  // REST / MCP Tool config
  connection_config?: Record<string, any>;
  schema_def?: Record<string, any>;
  
  // MCP Server specific
  transport?: MCPTransport;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  
  // Status and Hierarchy
  status: MCPServerStatus;
  last_error?: string;
  parent_id?: string;
  
  created_at: string;
  updated_at: string;
}

export interface ToolCreate {
  name: string;
  description?: string;
  type: ToolType;
  is_enabled?: boolean;
  connection_config?: Record<string, any>;
  schema_def?: Record<string, any>;
  transport?: MCPTransport;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  status?: MCPServerStatus;
  parent_id?: string;
}

export interface ToolUpdate {
  name?: string;
  description?: string;
  type?: ToolType;
  is_enabled?: boolean;
  connection_config?: Record<string, any>;
  schema_def?: Record<string, any>;
  transport?: MCPTransport;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  status?: MCPServerStatus;
  last_error?: string;
  parent_id?: string;
}


// ========================== AGENT ==========================================

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  system_prompt?: string;
  llm_provider?: string;
  llm_model?: string;
  attached_tool_ids?: string[];
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  name: string;
  system_prompt?: string;
  llm_provider?: string;
  llm_model?: string;
  attached_tool_ids?: string[];
}

export interface AgentUpdate {
  name?: string;
  system_prompt?: string;
  llm_provider?: string;
  llm_model?: string;
  attached_tool_ids?: string[];
}

// ========================== ORCHESTRATION ==================================

export type FrameworkType = 'LANGGRAPH' | 'CREWAI' | 'AUTOGEN';
export type ArchitectureType = 'REACT' | 'SUPERVISOR' | 'PLANNER';

export interface Orchestration {
  id: string;
  workspace_id: string;
  name: string;
  framework: FrameworkType;
  architecture_type: ArchitectureType;
  workflow_type?: string; // sequential, parallel, conditional, hitl, long_running, event_driven
  config?: Record<string, any>;
  enable_checkpointing?: boolean;
  requires_approval?: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrchestrationCreate {
  name: string;
  framework?: FrameworkType;
  architecture_type?: ArchitectureType;
  config?: Record<string, any>;
}

export interface OrchestrationUpdate {
  name?: string;
  framework?: FrameworkType;
  architecture_type?: ArchitectureType;
  config?: Record<string, any>;
}

// ========================== ROUTER PREDICT =================================

export interface RouterPredictRequest {
  user_prompt: string;
  workspace_id: string;
  top_k?: number;
}

export interface RouterPredictResponse {
  tools: Tool[];
  cached: boolean;
  latency_ms: number;
}

// ========================== PLAYGROUND / TRACE =============================

export interface PlaygroundMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp?: Date;
  toolName?: string;
  traceId?: string;
}

export interface TraceEvent {
  type: 'router' | 'llm_call' | 'tool_call' | 'tool_result' | 'error' | 'complete';
  label: string;
  detail?: string;
  timestamp: string;
  latency_ms?: number;
  status?: 'running' | 'success' | 'error';
}
