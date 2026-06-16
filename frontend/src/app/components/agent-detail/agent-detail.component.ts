/**
 * Agent Detail Component
 *
 * Comprehensive agent configuration page with:
 * - Basic information
 * - System prompt engineering
 * - LLM configuration
 * - Tool management (individual or NeuralToolRouter)
 * - Memory configuration
 * - Behavior settings
 * - Template selection
 * - A2A import/export
 * - Testing & validation
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import {
  ButtonModule, NotificationModule, IconModule,
  TagModule, InputModule, DropdownModule, TabsModule,
  LoadingModule, ToggleModule, SliderModule,
  AccordionModule, ToggletipModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import { LLMConfigService } from '../../services/llm-config.service';
import { Agent, AgentCreate, ChatExecutionContext, CollaboratorAgent, PlaygroundMessage, Tool, TraceEvent, Workspace } from '../../models/platform.model';
import { LLMModelConfig } from '../../models/llm-config.model';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';
import { ExecutionChatComponent } from '../shared/execution-chat/execution-chat.component';

import Save16 from '@carbon/icons/es/save/16';
import Play16 from '@carbon/icons/es/play/16';
import Copy16 from '@carbon/icons/es/copy/16';
import Export16 from '@carbon/icons/es/export/16';
import Upload16 from '@carbon/icons/es/upload/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Bot16 from '@carbon/icons/es/bot/16';
import Link16 from '@carbon/icons/es/link/16';
import Settings16 from '@carbon/icons/es/settings/16';
import Template16 from '@carbon/icons/es/template/16';
import Information16 from '@carbon/icons/es/information/16';
import Chip16 from '@carbon/icons/es/chip/16';
import DataBase16 from '@carbon/icons/es/data--base/16';
import TestTool16 from '@carbon/icons/es/test-tool/16';
import ChevronDown16 from '@carbon/icons/es/chevron--down/16';
import Help16 from '@carbon/icons/es/help/16';

@Component({
  selector: 'app-agent-detail',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    ButtonModule, NotificationModule, IconModule,
    TagModule, InputModule, DropdownModule, TabsModule,
    LoadingModule, ToggleModule, SliderModule,
    AccordionModule, ToggletipModule,
    PageHeaderComponent, PageWrapperComponent, ExecutionChatComponent,
  ],
  templateUrl: './agent-detail.component.html',
  styleUrls: ['./agent-detail.component.scss'],
})
export class AgentDetailComponent implements OnInit, OnDestroy {
  agentId: string | null = null;
  isEditMode = false;
  loading = false;
  saving = false;
  notification: any = null;

  // Vertical tabs
  activeTabIndex = 0;
  tabs = [
    { label: 'Profile', icon: 'information' },
    { label: 'Tools', icon: 'link' },
    { label: 'Collaborators', icon: 'bot' },
    { label: 'Memory & Behaviour', icon: 'data--base' },
    { label: 'Test Agent', icon: 'test-tool' },
  ];

  // Form data
  formData: AgentCreate = {
    name: '',
    description: '',
    system_prompt: 'You are a helpful AI assistant.',
    llm_config_id: '',
    use_neural_router: false,
    router_model_id: '',
    router_top_k: 2,
    memory_type: 'buffer',
    memory_window: 10,
    max_iterations: 10,
    timeout_seconds: 300,
    attached_tool_ids: [],
    collaborator_agent_ids: [],
  };

  // Extended form fields
  temperature = 0.7;
  maxTokens: number | undefined;

  // Tool selection
  tools: Tool[] = [];
  selectedToolIds: Set<string> = new Set();

  // LLM Configuration
  llmConfigurations: LLMModelConfig[] = [];
  selectedLLMConfigId: string = '';
  llmConfigDropdownItems: any[] = [];

  // Neural Tool Router Models
  availableRouterModels: any[] = [];
  selectedRouterModelId: string = '';
  routerModelDropdownItems: any[] = [];

  // Memory Type
  memoryTypeDropdownItems: any[] = [
    { content: 'Buffer (Recent messages)', id: 'buffer', selected: false },
    { content: 'Summary (Condensed history)', id: 'summary', selected: false },
    { content: 'Vector (Semantic search)', id: 'vector', selected: false }
  ];

  // Collaborators
  availableCollaborators: Agent[] = [];
  selectedCollaboratorIds: Set<string> = new Set();
  collaboratorSearchTerm = '';

  // A2A Import
  showA2AImport = false;
  a2aJson = '';

  testMessages: PlaygroundMessage[] = [];
  testTraceEvents: TraceEvent[] = [];
  testUserInput = '';
  testIsExecuting = false;
  testShowTrace = true;
  testSessionId: string | null = null;

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];
  private testAbortController: AbortController | null = null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private llmConfigService: LLMConfigService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Save16, Play16, Copy16, Export16, Upload16, TrashCan16,
      Bot16, Link16, Settings16, Template16, Information16,
      Chip16, DataBase16, TestTool16, ChevronDown16, Help16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) {
          this.loadTools();
          this.loadLLMConfigurations();
          this.loadAvailableCollaborators();
          this.loadRouterModels();
        }
      })
    );

    this.subs.push(
      this.route.params.subscribe((params) => {
        this.agentId = params['id'];
        if (this.agentId && this.agentId !== 'new') {
          this.isEditMode = true;
          this.loadAgent();
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.testAbortController?.abort();
    this.subs.forEach((s) => s.unsubscribe());
  }

  // ─── Data Loading ──────────────────────────────────────────────

  loadAgent(): void {
    if (!this.activeWorkspace || !this.agentId) return;
    this.loading = true;
    this.platformApi.getAgent(this.activeWorkspace.id, this.agentId).subscribe({
      next: (agent: Agent) => {
        this.formData = {
          name: agent.name,
          description: agent.description || '',
          system_prompt: agent.system_prompt || '',
          llm_config_id: agent.llm_config_id || '',
          use_neural_router: agent.use_neural_router ?? false,
          router_model_id: agent.router_model_id || '',
          router_top_k: agent.router_top_k || 2,
          memory_type: agent.memory_type || 'buffer',
          memory_window: agent.memory_window || 10,
          max_iterations: agent.max_iterations || 10,
          timeout_seconds: agent.timeout_seconds || 300,
          attached_tool_ids: agent.attached_tool_ids || [],
          collaborator_agent_ids: agent.collaborator_agent_ids || [],
        };
        this.selectedLLMConfigId = agent.llm_config_id || '';
        this.selectedRouterModelId = agent.router_model_id || '';
        this.selectedToolIds = new Set(agent.attached_tool_ids || []);
        this.selectedCollaboratorIds = new Set(agent.collaborator_agent_ids || []);
        this.updateMemoryTypeSelection();
        this.updateLLMConfigDropdownItems();
        this.updateRouterModelDropdownItems();
        this.loading = false;
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Load Failed', message: err.message };
        this.loading = false;
      },
    });
  }

  loadTools(): void {
    if (!this.activeWorkspace) return;
    this.platformApi.listTools(this.activeWorkspace.id).subscribe({
      next: (tools) => {
        // Filter tools to show only workspace-specific tools (not from default workspace)
        this.tools = tools.filter(tool => tool.workspace_id === this.activeWorkspace?.id);
      },
      error: () => { },
    });
  }

  loadAvailableCollaborators(): void {
    if (!this.activeWorkspace) return;
    this.platformApi.listAgents(this.activeWorkspace.id).subscribe({
      next: (agents) => {
        this.availableCollaborators = agents.filter((agent) => agent.id !== this.agentId);
      },
      error: () => { },
    });
  }

  loadLLMConfigurations(): void {
    if (!this.activeWorkspace) return;
    this.llmConfigService.loadConfigurations(this.activeWorkspace.id);
    this.subs.push(
      this.llmConfigService.configurations$.subscribe((configs) => {
        this.llmConfigurations = configs;
        this.updateLLMConfigDropdownItems();
      })
    );
  }

  updateLLMConfigDropdownItems(): void {
    this.llmConfigDropdownItems = this.llmConfigurations.map(config => ({
      content: `${config.name} (${config.provider} - ${config.model_name})`,
      id: config.id,
      selected: config.id === this.selectedLLMConfigId
    }));
  }

  onLLMConfigSelect(event: any): void {
    this.selectedLLMConfigId = event.item.id;
    this.formData.llm_config_id = event.item.id;
  }

  onMemoryTypeSelect(event: any): void {
    this.formData.memory_type = event.item.id;
  }

  onRouterModelSelect(event: any): void {
    this.selectedRouterModelId = event.item.id;
    this.formData.router_model_id = event.item.id;
  }

  toggleCollaborator(agentId: string): void {
    if (this.selectedCollaboratorIds.has(agentId)) {
      this.selectedCollaboratorIds.delete(agentId);
    } else {
      this.selectedCollaboratorIds.add(agentId);
    }
    this.formData.collaborator_agent_ids = Array.from(this.selectedCollaboratorIds);
  }

  isCollaboratorSelected(agentId: string): boolean {
    return this.selectedCollaboratorIds.has(agentId);
  }

  get filteredCollaborators(): Agent[] {
    const search = this.collaboratorSearchTerm.trim().toLowerCase();
    const filtered = this.availableCollaborators.filter((agent) => {
      if (this.agentId && agent.id === this.agentId) {
        return false;
      }

      if (!search) {
        return true;
      }

      return (
        agent.name.toLowerCase().includes(search) ||
        (agent.description || '').toLowerCase().includes(search)
      );
    });

    return filtered.sort((a, b) => {
      const aSelected = this.selectedCollaboratorIds.has(a.id) ? 0 : 1;
      const bSelected = this.selectedCollaboratorIds.has(b.id) ? 0 : 1;
      if (aSelected !== bSelected) {
        return aSelected - bSelected;
      }
      return a.name.localeCompare(b.name);
    });
  }

  get selectedCollaborators(): CollaboratorAgent[] {
    const selectedIds = Array.from(this.selectedCollaboratorIds);
    return selectedIds
      .map((id) => this.availableCollaborators.find((agent) => agent.id === id))
      .filter((agent): agent is Agent => !!agent)
      .map((agent) => ({
        id: agent.id,
        workspace_id: agent.workspace_id,
        name: agent.name,
        description: agent.description,
        system_prompt: agent.system_prompt,
      }));
  }

  onLLMConfigChange(): void {
    const selectedConfig = this.llmConfigurations.find(c => c.id === this.selectedLLMConfigId);
    if (selectedConfig) {
      this.formData.llm_config_id = selectedConfig.id;
      this.temperature = selectedConfig.temperature;
      this.maxTokens = selectedConfig.max_tokens;
    }
  }

  // ─── Tool Management ───────────────────────────────────────────

  toggleTool(toolId: string): void {
    if (this.selectedToolIds.has(toolId)) {
      this.selectedToolIds.delete(toolId);
    } else {
      this.selectedToolIds.add(toolId);
    }
    this.formData.attached_tool_ids = Array.from(this.selectedToolIds);
  }

  isToolSelected(toolId: string): boolean {
    return this.selectedToolIds.has(toolId);
  }

  getToolName(toolId: string): string {
    return this.tools.find((t) => t.id === toolId)?.name || toolId.substring(0, 8);
  }

  // ─── A2A Import ────────────────────────────────────────────────

  toggleA2AImport(): void {
    this.showA2AImport = !this.showA2AImport;
  }

  importA2A(): void {
    try {
      const a2aSpec = JSON.parse(this.a2aJson);
      this.formData.name = a2aSpec.name || this.formData.name;
      this.formData.system_prompt = a2aSpec.system_prompt || this.formData.system_prompt;
      // Map other fields as needed
      this.notification = {
        type: 'success',
        title: 'Import Successful',
        message: 'Agent imported from A2A specification.',
      };
      this.showA2AImport = false;
    } catch (err) {
      this.notification = {
        type: 'error',
        title: 'Import Failed',
        message: 'Invalid A2A JSON format.',
      };
    }
  }

  // ─── Save & Actions ────────────────────────────────────────────

  saveAgent(): void {
    if (!this.activeWorkspace) return;
    if (!this.formData.name) {
      this.notification = {
        type: 'error',
        title: 'Validation Error',
        message: 'Agent name is required.',
      };
      return;
    }

    this.saving = true;
    this.formData.attached_tool_ids = Array.from(this.selectedToolIds);
    this.formData.collaborator_agent_ids = Array.from(this.selectedCollaboratorIds);
    this.formData.use_neural_router = this.formData.use_neural_router ?? false;
    this.formData.router_model_id = this.formData.use_neural_router ? this.selectedRouterModelId : null as any;
    this.formData.router_top_k = this.formData.use_neural_router ? (this.formData.router_top_k || 2) : null as any;
    this.formData.memory_type = this.formData.memory_type || 'buffer';
    this.formData.memory_window = this.formData.memory_window || 10;
    this.formData.max_iterations = this.formData.max_iterations || 10;
    this.formData.timeout_seconds = this.formData.timeout_seconds || 300;
    if (!this.formData.llm_config_id) {
      delete this.formData.llm_config_id;
    }

    const apiCall = this.isEditMode && this.agentId
      ? this.platformApi.updateAgent(this.activeWorkspace.id, this.agentId, this.formData)
      : this.platformApi.createAgent(this.activeWorkspace.id, this.formData);

    apiCall.subscribe({
      next: (agent) => {
        this.notification = {
          type: 'success',
          title: this.isEditMode ? 'Updated' : 'Created',
          message: `Agent "${this.formData.name}" ${this.isEditMode ? 'updated' : 'created'} successfully.`,
        };
        this.saving = false;
        // Navigate back to agent studio after a delay
        setTimeout(() => {
          this.router.navigate(['/agents']);
        }, 1500);
      },
      error: (err) => {
        this.notification = {
          type: 'error',
          title: this.isEditMode ? 'Update Failed' : 'Create Failed',
          message: err.error?.detail || err.message,
        };
        this.saving = false;
      },
    });
  }

  discoverAgents(): void {
    this.notification = {
      type: 'info',
      title: 'Discover Agents',
      message: 'Discover Agents functionality coming soon.',
    };
  }

  cloneAgent(): void {
    this.isEditMode = false;
    this.agentId = null;
    this.formData.name = `${this.formData.name} (Copy)`;
    this.notification = {
      type: 'info',
      title: 'Clone Mode',
      message: 'Agent cloned. Modify and save as new agent.',
    };
  }

  exportA2A(): void {
    const a2aSpec = {
      name: this.formData.name,
      description: this.formData.description,
      system_prompt: this.formData.system_prompt,
      llm_config_id: this.formData.llm_config_id,
      attached_tool_ids: this.formData.attached_tool_ids,
    };
    const blob = new Blob([JSON.stringify(a2aSpec, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${this.formData.name.replace(/\s+/g, '_')}_a2a.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  deleteAgent(): void {
    if (!this.activeWorkspace || !this.agentId) return;
    if (!confirm(`Delete agent "${this.formData.name}"?`)) return;

    this.platformApi.deleteAgent(this.activeWorkspace.id, this.agentId).subscribe({
      next: () => {
        this.notification = {
          type: 'success',
          title: 'Deleted',
          message: `Agent "${this.formData.name}" deleted.`,
        };
        setTimeout(() => {
          this.router.navigate(['/agents']);
        }, 1000);
      },
      error: (err) => {
        this.notification = {
          type: 'error',
          title: 'Delete Failed',
          message: err.error?.detail || err.message,
        };
      },
    });
  }

  cancel(): void {
    this.router.navigate(['/agents']);
  }

  dismissNotification(): void {
    this.notification = null;
  }

  getPageTitle(): string {
    // If agent name is not empty, show it instead of "Create Agent" or "Edit Agent"
    if (this.formData.name && this.formData.name.trim()) {
      return this.formData.name;
    }
    return this.isEditMode ? 'Edit Agent' : 'Create Agent';
  }

  loadRouterModels(): void {
    if (!this.activeWorkspace) return;
    // Fetch available fine-tuned models from the backend
    this.platformApi.listRouterModels(this.activeWorkspace.id).subscribe({
      next: (response: any) => {
        this.availableRouterModels = response.models || [];
        this.updateRouterModelDropdownItems();
      },
      error: () => {
        this.availableRouterModels = [];
        this.updateRouterModelDropdownItems();
      },
    });
  }

  updateRouterModelDropdownItems(): void {
    this.routerModelDropdownItems = this.availableRouterModels.map(model => ({
      content: model.name,
      id: model.name,
      selected: model.name === this.selectedRouterModelId
    }));
  }

  updateMemoryTypeSelection(): void {
    this.memoryTypeDropdownItems = this.memoryTypeDropdownItems.map(item => ({
      ...item,
      selected: item.id === this.formData.memory_type
    }));
  }
  async runAgentTest(): Promise<void> {
    if (!this.activeWorkspace || !this.agentId || !this.testUserInput.trim() || this.testIsExecuting) {
      return;
    }

    const prompt = this.testUserInput.trim();
    this.testUserInput = '';
    this.testMessages.push({
      role: 'user',
      content: prompt,
      timestamp: new Date(),
    });
    this.testIsExecuting = true;
    this.testAbortController = new AbortController();

    try {
      // Use the new session-based executeAgent method
      const returnedSessionId = await this.platformApi.executeAgent(
        this.activeWorkspace.id,
        this.agentId,
        prompt,
        this.testSessionId, // Pass existing session ID for multi-turn
        null, // No top_k override
        (event: any) => {
          // Create new array reference to trigger Angular change detection
          this.testTraceEvents = [...this.testTraceEvents, {
            type: event.type,
            label: event.label || event.type,
            detail: event.detail || event.message || '',
            timestamp: event.timestamp || new Date().toISOString(),
            latency_ms: event.latency_ms,
            status: event.status || 'success',
            metadata: event.metadata || event.data,
            format: event.type === 'assistant' ? 'markdown' : 'json',
          }];

          if (event.type === 'assistant') {
            this.testMessages.push({
              role: 'assistant',
              content: event.detail || event.message || event.label,
              timestamp: new Date(),
              metadata: event.metadata || event.data,
              format: 'markdown',
            });
          }

          if (event.type === 'tool_call' || event.type === 'tool_result') {
            this.testMessages.push({
              role: 'tool',
              content: event.detail || event.message || event.label,
              toolName: event.metadata?.tool_name || event.label,
              timestamp: new Date(),
              metadata: event.metadata || event.data,
              format: 'json',
            });
          }

          if (event.type === 'llm_call' || event.type === 'reasoning' || event.type === 'router') {
            this.testMessages.push({
              role: 'system',
              content: event.label,
              timestamp: new Date(),
              metadata: event.metadata || event.data || (event.detail ? { detail: event.detail } : undefined),
              format: 'json',
            });
          }

          if (event.type === 'error' || event.type === 'complete') {
            this.testIsExecuting = false;
          }
        },
        this.testAbortController.signal
      );

      // Store session ID for multi-turn conversations
      this.testSessionId = returnedSessionId;
    } catch (err: any) {
      const aborted = err?.name === 'AbortError';
      this.testMessages.push({
        role: 'system',
        content: aborted ? 'Execution stopped by user.' : `Error: ${err.message}`,
        timestamp: new Date(),
      });
      // Create new array reference to trigger Angular change detection
      this.testTraceEvents = [...this.testTraceEvents, {
        type: aborted ? 'complete' : 'error',
        label: aborted ? 'Execution Stopped' : 'Execution Error',
        detail: aborted ? 'The current agent execution was stopped by the user.' : (err.message || 'Execution failed'),
        timestamp: new Date().toISOString(),
        status: aborted ? 'success' : 'error',
      }];
      this.testIsExecuting = false;
    } finally {
      this.testAbortController = null;
      this.testIsExecuting = false;
    }
  }

  stopAgentTest(): void {
    if (!this.testIsExecuting) {
      return;
    }

    this.testAbortController?.abort();
  }

  clearAgentTest(): void {
    this.testMessages = [];
    this.testTraceEvents = [];
    this.testSessionId = null; // Clear session for fresh start
  }

  toggleAgentTestTrace(): void {
    this.testShowTrace = !this.testShowTrace;
  }

  get agentExecutionContext(): ChatExecutionContext | null {
    if (!this.agentId || !this.formData.name) {
      return null;
    }

    // Get LLM config details
    const llmConfig = this.llmConfigurations.find(c => c.id === this.selectedLLMConfigId);
    const llmModel = llmConfig ? `${llmConfig.provider}/${llmConfig.model_name}` : undefined;

    return {
      id: this.agentId,
      label: this.formData.name,
      type: 'agent',
      config: {
        use_neural_router: this.formData.use_neural_router,
        router_top_k: this.formData.router_top_k,
        tool_count: this.selectedToolIds.size,
        collaborator_count: this.selectedCollaboratorIds.size,
        memory_type: this.formData.memory_type,
        memory_window: this.formData.memory_window,
        llm_model: llmModel,
        max_iterations: this.formData.max_iterations,
        timeout_seconds: this.formData.timeout_seconds,
      },
    };
  }
}

// Made with Bob
