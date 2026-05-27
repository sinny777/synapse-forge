/**
 * SynapseForge — Platform API Service
 *
 * Typed HTTP service wrapping all platform CRUD endpoints for
 * Tools, Agents, Orchestrations, and Router predictions.
 * Every method that requires workspace context takes a workspaceId parameter.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  Tool,
  ToolCreate,
  ToolUpdate,
  Agent,
  AgentCreate,
  AgentUpdate,
  Orchestration,
  OrchestrationCreate,
  OrchestrationUpdate,
  RouterPredictRequest,
  RouterPredictResponse,
} from '../models/platform.model';

const API_BASE = 'http://localhost:8000/api';

@Injectable({
  providedIn: 'root',
})
export class PlatformApiService {
  constructor(private http: HttpClient) {}

  // ========================== TOOLS =======================================

  listTools(workspaceId: string): Observable<Tool[]> {
    return this.http.get<Tool[]>(
      `${API_BASE}/workspaces/${workspaceId}/tools`
    );
  }

  createTool(workspaceId: string, body: ToolCreate): Observable<Tool> {
    return this.http.post<Tool>(
      `${API_BASE}/workspaces/${workspaceId}/tools`,
      body
    );
  }

  getTool(workspaceId: string, toolId: string): Observable<Tool> {
    return this.http.get<Tool>(
      `${API_BASE}/workspaces/${workspaceId}/tools/${toolId}`
    );
  }

  updateTool(
    workspaceId: string,
    toolId: string,
    body: ToolUpdate
  ): Observable<Tool> {
    return this.http.put<Tool>(
      `${API_BASE}/workspaces/${workspaceId}/tools/${toolId}`,
      body
    );
  }

  deleteTool(workspaceId: string, toolId: string): Observable<void> {
    return this.http.delete<void>(
      `${API_BASE}/workspaces/${workspaceId}/tools/${toolId}`
    );
  }

  testToolConnection(
    workspaceId: string,
    toolId: string
  ): Observable<any> {
    return this.http.post<any>(
      `${API_BASE}/workspaces/${workspaceId}/tools/${toolId}/test`,
      {}
    );
  }


  // ========================== AGENTS ======================================

  listAgents(workspaceId: string): Observable<Agent[]> {
    return this.http.get<Agent[]>(
      `${API_BASE}/workspaces/${workspaceId}/agents`
    );
  }

  createAgent(workspaceId: string, body: AgentCreate): Observable<Agent> {
    return this.http.post<Agent>(
      `${API_BASE}/workspaces/${workspaceId}/agents`,
      body
    );
  }

  getAgent(workspaceId: string, agentId: string): Observable<Agent> {
    return this.http.get<Agent>(
      `${API_BASE}/workspaces/${workspaceId}/agents/${agentId}`
    );
  }

  updateAgent(
    workspaceId: string,
    agentId: string,
    body: AgentUpdate
  ): Observable<Agent> {
    return this.http.put<Agent>(
      `${API_BASE}/workspaces/${workspaceId}/agents/${agentId}`,
      body
    );
  }

  deleteAgent(workspaceId: string, agentId: string): Observable<void> {
    return this.http.delete<void>(
      `${API_BASE}/workspaces/${workspaceId}/agents/${agentId}`
    );
  }

  // ========================== ORCHESTRATIONS ==============================

  listOrchestrations(workspaceId: string): Observable<Orchestration[]> {
    return this.http.get<Orchestration[]>(
      `${API_BASE}/workspaces/${workspaceId}/orchestrations`
    );
  }

  createOrchestration(
    workspaceId: string,
    body: OrchestrationCreate
  ): Observable<Orchestration> {
    return this.http.post<Orchestration>(
      `${API_BASE}/workspaces/${workspaceId}/orchestrations`,
      body
    );
  }

  getOrchestration(
    workspaceId: string,
    orchestrationId: string
  ): Observable<Orchestration> {
    return this.http.get<Orchestration>(
      `${API_BASE}/workspaces/${workspaceId}/orchestrations/${orchestrationId}`
    );
  }

  updateOrchestration(
    workspaceId: string,
    orchestrationId: string,
    body: OrchestrationUpdate
  ): Observable<Orchestration> {
    return this.http.put<Orchestration>(
      `${API_BASE}/workspaces/${workspaceId}/orchestrations/${orchestrationId}`,
      body
    );
  }

  deleteOrchestration(
    workspaceId: string,
    orchestrationId: string
  ): Observable<void> {
    return this.http.delete<void>(
      `${API_BASE}/workspaces/${workspaceId}/orchestrations/${orchestrationId}`
    );
  }

  /**
   * Import tools from the Default Workspace.
   * Uses the new /api/clone/tools endpoint with proper batch request body.
   */
  importMasterTools(
    destinationWorkspaceId: string,
    toolIds: string[],
    sourceWorkspaceId?: string
  ): Observable<{cloned: number; skipped: number; errors: string[]}> {
    return this.http.post<{cloned: number; skipped: number; errors: string[]}>(
      `${API_BASE}/clone/tools`,
      {
        source_workspace_id: sourceWorkspaceId || null,
        destination_workspace_id: destinationWorkspaceId,
        resource_ids: toolIds,
      }
    );
  }

  /**
   * Import agents from the Default Workspace.
   */
  importMasterAgents(
    destinationWorkspaceId: string,
    agentIds: string[],
    sourceWorkspaceId?: string
  ): Observable<{cloned: number; skipped: number; errors: string[]}> {
    return this.http.post<{cloned: number; skipped: number; errors: string[]}>(
      `${API_BASE}/clone/agents`,
      {
        source_workspace_id: sourceWorkspaceId || null,
        destination_workspace_id: destinationWorkspaceId,
        resource_ids: agentIds,
      }
    );
  }

  // ========================== ROUTER PREDICT ==============================

  routerPredict(body: RouterPredictRequest): Observable<RouterPredictResponse> {
    return this.http.post<RouterPredictResponse>(
      `${API_BASE}/router/predict`,
      body
    );
  }

  // ========================== NEURAL TOOL ROUTER MODELS ====================

  listRouterModels(workspaceId: string): Observable<any> {
    return this.http.get<any>(
      `${API_BASE}/models?workspace_id=${workspaceId}`
    );
  }

  // ========================== PLAYGROUND EXECUTE ===========================

  /**
   * Execute an orchestration via SSE streaming.
   * Returns parsed trace events in real time.
   */
  async executeOrchestration(
    orchestrationId: string,
    userPrompt: string,
    onEvent: (event: any) => void
  ): Promise<void> {
    const response = await fetch(
      `${API_BASE}/orchestrator/${orchestrationId}/execute`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_prompt: userPrompt }),
        credentials: 'include',
      }
    );

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || 'Orchestration execution failed');
    }

    if (!response.body) {
      throw new Error('ReadableStream not supported');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE format: "data: {...}\n\n"
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const jsonStr = line.substring(6);
          if (jsonStr.trim()) {
            try {
              const event = JSON.parse(jsonStr);
              onEvent(event);
            } catch (e) {
              console.error('Failed to parse SSE event:', e, jsonStr);
            }
          }
        }
      }
    }
  }
}
