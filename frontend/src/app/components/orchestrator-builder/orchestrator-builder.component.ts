/**
 * Orchestrator Builder Component
 *
 * Phase 6 — Framework/architecture selector, dynamic config form,
 * and data table of existing orchestrations.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
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

  // Removed framework selection - backend always uses LangGraph
  // Users select capabilities, not frameworks

  // Workflow types - capability-based, framework-agnostic
  workflowTypes = [
    {
      id: 'sequential',
      name: 'Sequential',
      description: 'Execute agents one after another in order',
      icon: '➡️',
      features: ['Error handling', 'Output chaining', 'Progress tracking'],
      useCases: ['Data processing pipelines', 'Step-by-step analysis']
    },
    {
      id: 'parallel',
      name: 'Parallel',
      description: 'Run multiple agents at the same time',
      icon: '⚡',
      features: ['Concurrent execution', 'Result aggregation', 'Timeout handling'],
      useCases: ['Parallel research', 'Multi-source data gathering']
    },
    {
      id: 'conditional',
      name: 'Conditional',
      description: 'Route to different agents based on conditions',
      icon: '🔀',
      features: ['Dynamic routing', 'Multiple branches', 'Fallback paths'],
      useCases: ['Decision trees', 'Adaptive workflows']
    },
    {
      id: 'hitl',
      name: 'Human-in-the-Loop',
      description: 'Require human approval at key stages',
      icon: '👤',
      features: ['Approval gates', 'Notifications', 'Timeout escalation'],
      useCases: ['Compliance workflows', 'Quality control']
    },
    {
      id: 'long_running',
      name: 'Long-Running',
      description: 'Workflows that can pause and resume',
      icon: '⏱️',
      features: ['Checkpointing', 'Resume capability', 'Progress tracking'],
      useCases: ['Multi-day processes', 'Scheduled tasks']
    },
    {
      id: 'event_driven',
      name: 'Event-Driven',
      description: 'React to events and triggers',
      icon: '📡',
      features: ['Event subscriptions', 'Async execution', 'Event replay'],
      useCases: ['Real-time monitoring', 'Reactive systems']
    },
  ];

  // Capability toggles (replaces framework/architecture selection)
  capabilities = {
    enableCheckpointing: true,
    enableApprovalGates: false,
    enableParallelExecution: false,
    enableConditionalRouting: false,
    checkpointBackend: 'redis' as 'redis' | 'postgres',
  };

  selectedWorkflowType: string | null = null;

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  constructor(
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
    private router: Router,
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

  // ─── Navigation ────────────────────────────────────────────────

  openCreateModal(): void {
    this.router.navigate(['/orchestrator', 'new']);
  }

  openEditModal(orch: Orchestration): void {
    this.router.navigate(['/orchestrator', orch.id]);
  }

  closeModal(): void {
    // No longer needed - kept for compatibility
    this.showModal = false;
    this.editingOrch = null;
  }

  // ─── Save ──────────────────────────────────────────────────────

  saveOrchestration(): void {
    // No longer needed - saving is handled in orchestrator-detail component
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

  getWorkflowTypeLabel(type: string): string {
    return this.workflowTypes.find((wf) => wf.id === type)?.name || type;
  }

  getWorkflowTypeIcon(type: string): string {
    return this.workflowTypes.find((wf) => wf.id === type)?.icon || '🔗';
  }

  getAgentNames(): string {
    return this.agents.map((a) => a.name).join(', ');
  }

  dismissNotification(): void {
    this.notification = null;
  }
}
