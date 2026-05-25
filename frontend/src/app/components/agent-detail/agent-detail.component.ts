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
  AccordionModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import { Agent, AgentCreate, Tool, Workspace } from '../../models/platform.model';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';

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

@Component({
  selector: 'app-agent-detail',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    ButtonModule, NotificationModule, IconModule,
    TagModule, InputModule, DropdownModule, TabsModule,
    LoadingModule, ToggleModule, SliderModule,
    AccordionModule,
    PageHeaderComponent, PageWrapperComponent,
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

  // Form data
  formData: AgentCreate = {
    name: '',
    system_prompt: 'You are a helpful AI assistant.',
    llm_provider: 'openai',
    llm_model: 'gpt-4o',
    attached_tool_ids: [],
  };

  // Extended form fields
  description = '';
  temperature = 0.7;
  maxTokens: number | undefined;
  useNeuralRouter = false;
  routerTopK = 5;
  memoryType: 'buffer' | 'summary' | 'vector' = 'buffer';
  memoryWindow = 10;
  maxIterations = 10;
  timeoutSeconds = 300;

  // Tool selection
  tools: Tool[] = [];
  selectedToolIds: Set<string> = new Set();

  // Templates
  templates = [
    {
      id: 'research',
      name: 'Research Assistant',
      description: 'Conducts web research and synthesizes information',
      systemPrompt: 'You are a research assistant specialized in finding and synthesizing information from multiple sources. Always cite your sources and provide comprehensive answers.',
      icon: '🔍',
    },
    {
      id: 'rag',
      name: 'RAG Agent',
      description: 'Retrieval-Augmented Generation for document Q&A',
      systemPrompt: 'You are a RAG agent that answers questions based on retrieved documents. Always ground your answers in the provided context and indicate when information is not available.',
      icon: '📚',
    },
    {
      id: 'coding',
      name: 'Coding Assistant',
      description: 'Helps with code generation and debugging',
      systemPrompt: 'You are an expert coding assistant. Provide clean, well-documented code with explanations. Follow best practices and consider edge cases.',
      icon: '💻',
    },
    {
      id: 'customer_service',
      name: 'Customer Service',
      description: 'Handles customer inquiries professionally',
      systemPrompt: 'You are a professional customer service agent. Be empathetic, clear, and solution-oriented. Always maintain a friendly and helpful tone.',
      icon: '🎧',
    },
  ];

  // LLM Configuration
  llmProviders = [
    { content: 'OpenAI', id: 'openai' },
    { content: 'Anthropic', id: 'anthropic' },
    { content: 'Google', id: 'google' },
    { content: 'Ollama (Local)', id: 'ollama' },
    { content: 'Groq', id: 'groq' },
  ];

  llmModels: Record<string, string[]> = {
    openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    anthropic: ['claude-3.5-sonnet', 'claude-3-haiku', 'claude-3-opus'],
    google: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-2.0-flash'],
    ollama: ['granite4.1:8b', 'llama3.2:latest', 'mistral:latest', 'qwen2.5-coder:7b'],
    groq: ['llama-3.1-70b-versatile', 'mixtral-8x7b-32768'],
  };

  // A2A Import
  showA2AImport = false;
  a2aJson = '';

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Save16, Play16, Copy16, Export16, Upload16, TrashCan16,
      Bot16, Link16, Settings16, Template16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) {
          this.loadTools();
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
          system_prompt: agent.system_prompt || '',
          llm_provider: agent.llm_provider || 'openai',
          llm_model: agent.llm_model || 'gpt-4o',
          attached_tool_ids: agent.attached_tool_ids || [],
        };
        this.selectedToolIds = new Set(agent.attached_tool_ids || []);
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
      next: (tools) => this.tools = tools,
      error: () => {},
    });
  }

  // ─── Template Selection ────────────────────────────────────────

  applyTemplate(template: any): void {
    this.formData.system_prompt = template.systemPrompt;
    if (!this.formData.name) {
      this.formData.name = template.name;
    }
    this.notification = {
      type: 'success',
      title: 'Template Applied',
      message: `${template.name} template has been applied.`,
    };
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

  // ─── LLM Configuration ─────────────────────────────────────────

  getAvailableModels(): string[] {
    return this.llmModels[this.formData.llm_provider || 'openai'] || [];
  }

  onProviderChange(event: any): void {
    const providerId = event?.item?.id || event;
    this.formData.llm_provider = providerId;
    const models = this.getAvailableModels();
    if (models.length > 0) {
      this.formData.llm_model = models[0];
    }
  }

  estimateCost(): string {
    // Simple cost estimation based on provider and model
    const costs: Record<string, Record<string, number>> = {
      openai: {
        'gpt-4o': 0.005,
        'gpt-4o-mini': 0.0015,
        'gpt-4-turbo': 0.01,
        'gpt-3.5-turbo': 0.0005,
      },
      anthropic: {
        'claude-3.5-sonnet': 0.003,
        'claude-3-haiku': 0.00025,
        'claude-3-opus': 0.015,
      },
    };

    const provider = this.formData.llm_provider || 'openai';
    const model = this.formData.llm_model || 'gpt-4o';
    const costPer1k = costs[provider]?.[model] || 0.001;

    return `~$${costPer1k.toFixed(4)}/1K tokens`;
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

  testAgent(): void {
    this.notification = {
      type: 'info',
      title: 'Test Agent',
      message: 'Agent testing functionality coming soon.',
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
      system_prompt: this.formData.system_prompt,
      llm_provider: this.formData.llm_provider,
      llm_model: this.formData.llm_model,
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
}

// Made with Bob
