/**
 * Orchestrator Builder Component
 *
 * Phase 6 — Framework/architecture selector, dynamic config form,
 * and data table of existing orchestrations.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule, NotificationModule, IconModule,
  TagModule, ModalModule, InputModule, DropdownModule,
  LoadingModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import {
  Orchestration, OrchestrationCreate, Agent, Workspace,
  FrameworkType, ArchitectureType,
} from '../../models/platform.model';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';

import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Edit16 from '@carbon/icons/es/edit/16';
import Renew16 from '@carbon/icons/es/renew/16';
import FlowData16 from '@carbon/icons/es/flow--data/16';
import Play16 from '@carbon/icons/es/play/16';

@Component({
  selector: 'app-orchestrator-builder',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    ButtonModule, NotificationModule, IconModule,
    TagModule, ModalModule, InputModule, DropdownModule,
    LoadingModule,
    PageHeaderComponent, PageWrapperComponent,
  ],
  templateUrl: './orchestrator-builder.component.html',
  styleUrls: ['./orchestrator-builder.component.scss'],
})
export class OrchestratorBuilderComponent implements OnInit, OnDestroy {
  orchestrations: Orchestration[] = [];
  agents: Agent[] = [];
  loading = false;
  notification: any = null;

  // Modal
  showModal = false;
  editingOrch: Orchestration | null = null;
  formData: OrchestrationCreate = {
    name: '',
    framework: 'LANGGRAPH',
    architecture_type: 'REACT',
    config: {},
  };
  configJson = '{}';

  // Framework/Architecture options
  frameworks: { label: string; value: FrameworkType; icon: string; description: string }[] = [
    { label: 'LangGraph', value: 'LANGGRAPH', icon: '🔗', description: 'Stateful graph-based orchestration with checkpointing' },
    { label: 'CrewAI', value: 'CREWAI', icon: '👥', description: 'Role-based agent crews with delegation' },
    { label: 'AutoGen', value: 'AUTOGEN', icon: '🤖', description: 'Microsoft AutoGen multi-agent conversations' },
  ];

  architectures: { label: string; value: ArchitectureType; description: string }[] = [
    { label: 'ReAct', value: 'REACT', description: 'Reasoning + Acting loop — single agent with tool use' },
    { label: 'Supervisor', value: 'SUPERVISOR', description: 'Central supervisor delegates to worker agents' },
    { label: 'Planner', value: 'PLANNER', description: 'Plan-then-execute with dynamic task decomposition' },
  ];

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  constructor(
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Add16, TrashCan16, Edit16, Renew16, FlowData16, Play16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) {
          this.loadOrchestrations();
          this.loadAgents();
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  // ─── Data Loading ──────────────────────────────────────────────

  loadOrchestrations(): void {
    if (!this.activeWorkspace) return;
    this.loading = true;
    this.platformApi.listOrchestrations(this.activeWorkspace.id).subscribe({
      next: (orchs) => {
        this.orchestrations = orchs;
        this.loading = false;
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Load Failed', message: err.message };
        this.loading = false;
      },
    });
  }

  loadAgents(): void {
    if (!this.activeWorkspace) return;
    this.platformApi.listAgents(this.activeWorkspace.id).subscribe({
      next: (agents) => this.agents = agents,
      error: () => {},
    });
  }

  // ─── Modal ─────────────────────────────────────────────────────

  openCreateModal(): void {
    this.editingOrch = null;
    this.formData = {
      name: '',
      framework: 'LANGGRAPH',
      architecture_type: 'REACT',
      config: {},
    };
    this.configJson = '{}';
    this.showModal = true;
  }

  openEditModal(orch: Orchestration): void {
    this.editingOrch = orch;
    this.formData = {
      name: orch.name,
      framework: orch.framework,
      architecture_type: orch.architecture_type,
      config: orch.config || {},
    };
    this.configJson = JSON.stringify(orch.config || {}, null, 2);
    this.showModal = true;
  }

  closeModal(): void {
    this.showModal = false;
    this.editingOrch = null;
  }

  // ─── Save ──────────────────────────────────────────────────────

  saveOrchestration(): void {
    if (!this.activeWorkspace) return;

    try {
      this.formData.config = JSON.parse(this.configJson);
    } catch {
      this.notification = { type: 'error', title: 'Invalid JSON', message: 'Config JSON is invalid.' };
      return;
    }

    if (this.editingOrch) {
      this.platformApi
        .updateOrchestration(this.activeWorkspace.id, this.editingOrch.id, this.formData)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Updated', message: `Orchestration "${this.formData.name}" updated.` };
            this.closeModal();
            this.loadOrchestrations();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Update Failed', message: err.error?.detail || err.message };
          },
        });
    } else {
      this.platformApi
        .createOrchestration(this.activeWorkspace.id, this.formData)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Created', message: `Orchestration "${this.formData.name}" created.` };
            this.closeModal();
            this.loadOrchestrations();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Create Failed', message: err.error?.detail || err.message };
          },
        });
    }
  }

  deleteOrchestration(orch: Orchestration): void {
    if (!this.activeWorkspace) return;
    if (!confirm(`Delete orchestration "${orch.name}"?`)) return;

    this.platformApi.deleteOrchestration(this.activeWorkspace.id, orch.id).subscribe({
      next: () => {
        this.notification = { type: 'success', title: 'Deleted', message: `Orchestration "${orch.name}" removed.` };
        this.loadOrchestrations();
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Delete Failed', message: err.error?.detail || err.message };
      },
    });
  }

  getFrameworkLabel(value: string): string {
    return this.frameworks.find((f) => f.value === value)?.label || value;
  }

  getArchLabel(value: string): string {
    return this.architectures.find((a) => a.value === value)?.label || value;
  }

  getFrameworkIcon(value: string): string {
    return this.frameworks.find((f) => f.value === value)?.icon || '🔗';
  }

  getArchDescription(): string {
    return this.architectures.find((a) => a.value === this.formData.architecture_type)?.description || '';
  }

  getAgentNames(): string {
    return this.agents.map((a) => a.name).join(', ');
  }

  dismissNotification(): void {
    this.notification = null;
  }
}
