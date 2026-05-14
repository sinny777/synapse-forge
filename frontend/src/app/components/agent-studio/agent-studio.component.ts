/**
 * Agent Studio Component
 *
 * Phase 6 — Agent management UI with reactive forms.
 * Multi-select for attaching tools, LLM provider/model configuration.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule, NotificationModule, IconModule,
  TagModule, ModalModule, InputModule, DropdownModule, TabsModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import { Agent, AgentCreate, Tool, Workspace } from '../../models/platform.model';

import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Edit16 from '@carbon/icons/es/edit/16';
import Bot16 from '@carbon/icons/es/bot/16';
import Renew16 from '@carbon/icons/es/renew/16';
import Link16 from '@carbon/icons/es/link/16';

@Component({
  selector: 'app-agent-studio',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    ButtonModule, NotificationModule, IconModule,
    TagModule, ModalModule, InputModule, DropdownModule, TabsModule,
  ],
  templateUrl: './agent-studio.component.html',
  styleUrls: ['./agent-studio.component.scss'],
})
export class AgentStudioComponent implements OnInit, OnDestroy {
  agents: Agent[] = [];
  tools: Tool[] = [];
  loading = false;
  notification: any = null;

  // Modal state
  showModal = false;
  editingAgent: Agent | null = null;
  formData: AgentCreate = {
    name: '',
    system_prompt: '',
    llm_provider: 'openai',
    llm_model: 'gpt-4o',
    attached_tool_ids: [],
  };
  selectedToolIds: Set<string> = new Set();

  // LLM Provider options
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

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  constructor(
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Add16, TrashCan16, Edit16, Bot16, Renew16, Link16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) {
          this.loadAgents();
          this.loadTools();
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  // ─── Data Loading ──────────────────────────────────────────────

  loadAgents(): void {
    if (!this.activeWorkspace) return;
    this.loading = true;
    this.platformApi.listAgents(this.activeWorkspace.id).subscribe({
      next: (agents) => {
        this.agents = agents;
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

  // ─── Modal ─────────────────────────────────────────────────────

  openCreateModal(): void {
    this.editingAgent = null;
    this.formData = {
      name: '',
      system_prompt: 'You are a helpful AI assistant.',
      llm_provider: 'openai',
      llm_model: 'gpt-4o',
      attached_tool_ids: [],
    };
    this.selectedToolIds = new Set();
    this.showModal = true;
  }

  openEditModal(agent: Agent): void {
    this.editingAgent = agent;
    this.formData = {
      name: agent.name,
      system_prompt: agent.system_prompt || '',
      llm_provider: agent.llm_provider || 'openai',
      llm_model: agent.llm_model || 'gpt-4o',
      attached_tool_ids: agent.attached_tool_ids || [],
    };
    this.selectedToolIds = new Set(agent.attached_tool_ids || []);
    this.showModal = true;
  }

  closeModal(): void {
    this.showModal = false;
    this.editingAgent = null;
  }

  // ─── Tool Selection ────────────────────────────────────────────

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

  // ─── Save ──────────────────────────────────────────────────────

  saveAgent(): void {
    if (!this.activeWorkspace) return;

    this.formData.attached_tool_ids = Array.from(this.selectedToolIds);

    if (this.editingAgent) {
      this.platformApi
        .updateAgent(this.activeWorkspace.id, this.editingAgent.id, this.formData)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Updated', message: `Agent "${this.formData.name}" updated.` };
            this.closeModal();
            this.loadAgents();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Update Failed', message: err.error?.detail || err.message };
          },
        });
    } else {
      this.platformApi
        .createAgent(this.activeWorkspace.id, this.formData)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Created', message: `Agent "${this.formData.name}" created.` };
            this.closeModal();
            this.loadAgents();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Create Failed', message: err.error?.detail || err.message };
          },
        });
    }
  }

  deleteAgent(agent: Agent): void {
    if (!this.activeWorkspace) return;
    if (!confirm(`Delete agent "${agent.name}"?`)) return;

    this.platformApi.deleteAgent(this.activeWorkspace.id, agent.id).subscribe({
      next: () => {
        this.notification = { type: 'success', title: 'Deleted', message: `Agent "${agent.name}" removed.` };
        this.loadAgents();
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Delete Failed', message: err.error?.detail || err.message };
      },
    });
  }

  dismissNotification(): void {
    this.notification = null;
  }
}
