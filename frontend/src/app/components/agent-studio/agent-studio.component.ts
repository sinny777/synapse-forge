/**
 * Agent Studio Component
 *
 * Phase 6 — Agent management UI with reactive forms.
 * Multi-select for attaching tools, LLM provider/model configuration.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import {
  ButtonModule, NotificationModule, IconModule,
  TagModule, ModalModule, InputModule, DropdownModule, TabsModule,
  LoadingModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import { Agent, AgentCreate, Tool, Workspace } from '../../models/platform.model';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';

import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Edit16 from '@carbon/icons/es/edit/16';
import Bot16 from '@carbon/icons/es/bot/16';
import Renew16 from '@carbon/icons/es/renew/16';
import Link16 from '@carbon/icons/es/link/16';
import View16 from '@carbon/icons/es/view/16';
import Copy16 from '@carbon/icons/es/copy/16';

@Component({
  selector: 'app-agent-studio',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    ButtonModule, NotificationModule, IconModule,
    TagModule, ModalModule, InputModule, DropdownModule, TabsModule,
    LoadingModule,
    PageHeaderComponent, PageWrapperComponent,
  ],
  templateUrl: './agent-studio.component.html',
  styleUrls: ['./agent-studio.component.scss'],
})
export class AgentStudioComponent implements OnInit, OnDestroy {
  agents: Agent[] = [];
  tools: Tool[] = [];
  loading = false;
  notification: any = null;

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  constructor(
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
    private router: Router,
  ) {
    this.iconService.registerAll([
      Add16, TrashCan16, Edit16, Bot16, Renew16, Link16, View16, Copy16,
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

  get isDefaultWorkspace(): boolean {
    return this.activeWorkspace?.is_default === true;
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
    // Navigate to agent detail page in create mode
    this.router.navigate(['/agents', 'new']);
  }

  openEditModal(agent: Agent): void {
    // Navigate to agent detail page in edit mode
    this.router.navigate(['/agents', agent.id]);
  }

  // ─── Helper Methods ────────────────────────────────────────────

  getToolName(toolId: string): string {
    return this.tools.find((t) => t.id === toolId)?.name || toolId.substring(0, 8);
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
