/**
 * Tool Registry Component
 *
 * Phase 6 — Tool management UI with cds-tabs for "Custom Tools" and "MCP Servers".
 * Supports CRUD operations, auto-embedding on create, and real-time updates.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  TabsModule, ButtonModule, NotificationModule, IconModule,
  TagModule, ModalModule, InputModule, DropdownModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import { Tool, ToolCreate, Workspace } from '../../models/platform.model';

import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Edit16 from '@carbon/icons/es/edit/16';
import Search16 from '@carbon/icons/es/search/16';
import Api16 from '@carbon/icons/es/api/16';
import Renew16 from '@carbon/icons/es/renew/16';

@Component({
  selector: 'app-tool-registry',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    TabsModule, ButtonModule, NotificationModule, IconModule,
    TagModule, ModalModule, InputModule, DropdownModule,
  ],
  templateUrl: './tool-registry.component.html',
  styleUrls: ['./tool-registry.component.scss'],
})
export class ToolRegistryComponent implements OnInit, OnDestroy {
  tools: Tool[] = [];
  filteredTools: Tool[] = [];
  loading = false;
  searchQuery = '';
  activeTab = 0;
  notification: any = null;

  // Modal state
  showModal = false;
  editingTool: Tool | null = null;
  formData: ToolCreate = {
    name: '',
    description: '',
    type: 'REST',
    connection_config: {},
    schema_def: {},
  };
  connectionConfigJson = '{}';
  schemaDefJson = '{}';

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  constructor(
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Add16, TrashCan16, Edit16, Search16, Api16, Renew16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) this.loadTools();
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  // ─── Data Loading ───────────────────────────────────────────────

  loadTools(): void {
    if (!this.activeWorkspace) return;
    this.loading = true;
    this.platformApi.listTools(this.activeWorkspace.id).subscribe({
      next: (tools) => {
        this.tools = tools;
        this.filterTools();
        this.loading = false;
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Load Failed', message: err.message || 'Failed to load tools' };
        this.loading = false;
      },
    });
  }

  filterTools(): void {
    const type = this.activeTab === 0 ? 'REST' : 'MCP_SERVER';
    let list = this.tools.filter((t) => t.type === type);
    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase();
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          (t.description || '').toLowerCase().includes(q)
      );
    }
    this.filteredTools = list;
  }

  onTabSelected(index: number | any): void {
    this.activeTab = typeof index === 'number' ? index : index?.index ?? 0;
    this.filterTools();
  }

  onSearch(): void {
    this.filterTools();
  }

  // ─── CRUD Operations ───────────────────────────────────────────

  openCreateModal(): void {
    this.editingTool = null;
    this.formData = {
      name: '',
      description: '',
      type: this.activeTab === 0 ? 'REST' : 'MCP_SERVER',
      connection_config: {},
      schema_def: {},
    };
    this.connectionConfigJson = '{}';
    this.schemaDefJson = '{}';
    this.showModal = true;
  }

  openEditModal(tool: Tool): void {
    this.editingTool = tool;
    this.formData = {
      name: tool.name,
      description: tool.description || '',
      type: tool.type,
      connection_config: tool.connection_config || {},
      schema_def: tool.schema_def || {},
    };
    this.connectionConfigJson = JSON.stringify(tool.connection_config || {}, null, 2);
    this.schemaDefJson = JSON.stringify(tool.schema_def || {}, null, 2);
    this.showModal = true;
  }

  closeModal(): void {
    this.showModal = false;
    this.editingTool = null;
  }

  saveTool(): void {
    if (!this.activeWorkspace) return;

    // Parse JSON fields
    try {
      this.formData.connection_config = JSON.parse(this.connectionConfigJson);
    } catch {
      this.notification = { type: 'error', title: 'Invalid JSON', message: 'Connection config is not valid JSON' };
      return;
    }
    try {
      this.formData.schema_def = JSON.parse(this.schemaDefJson);
    } catch {
      this.notification = { type: 'error', title: 'Invalid JSON', message: 'Schema definition is not valid JSON' };
      return;
    }

    if (this.editingTool) {
      // Update
      this.platformApi
        .updateTool(this.activeWorkspace.id, this.editingTool.id, this.formData)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Updated', message: `Tool "${this.formData.name}" updated successfully.` };
            this.closeModal();
            this.loadTools();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Update Failed', message: err.error?.detail || err.message };
          },
        });
    } else {
      // Create
      this.platformApi
        .createTool(this.activeWorkspace.id, this.formData)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Created', message: `Tool "${this.formData.name}" registered and embedded.` };
            this.closeModal();
            this.loadTools();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Create Failed', message: err.error?.detail || err.message };
          },
        });
    }
  }

  deleteTool(tool: Tool): void {
    if (!this.activeWorkspace) return;
    if (!confirm(`Delete tool "${tool.name}"? This cannot be undone.`)) return;

    this.platformApi.deleteTool(this.activeWorkspace.id, tool.id).subscribe({
      next: () => {
        this.notification = { type: 'success', title: 'Deleted', message: `Tool "${tool.name}" removed.` };
        this.loadTools();
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Delete Failed', message: err.error?.detail || err.message };
      },
    });
  }

  getToolTypeLabel(type: string): string {
    return type === 'MCP_SERVER' ? 'MCP' : 'REST';
  }

  dismissNotification(): void {
    this.notification = null;
  }
}
