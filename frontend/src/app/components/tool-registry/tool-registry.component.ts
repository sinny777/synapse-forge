/**
 * Tool Registry Component
 *
 * Phase 6 — Tool management UI using Carbon Angular components.
 * Uses cds-tab-header-group for tabs, cds-search for search,
 * and proper Carbon form directives for the modal.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  TabsModule,
  ButtonModule,
  InputModule,
  DropdownModule,
  TagModule,
  IconModule,
  NotificationModule,
  LoadingModule,
  SelectModule,
  CheckboxModule,
  SearchModule,
  ToggleModule,
} from 'carbon-components-angular';
import { ModalModule } from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import { Tool, ToolCreate, Workspace, Category } from '../../models/platform.model';
import { MCPServerFormComponent } from './mcp-server-form.component';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';

import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Edit16 from '@carbon/icons/es/edit/16';
import Search16 from '@carbon/icons/es/search/16';
import Api16 from '@carbon/icons/es/api/16';
import LogoModelContextProtocol16 from '@carbon/icons/es/logo--model-context-protocol/16';
import Renew16 from '@carbon/icons/es/renew/16';
import Close16 from '@carbon/icons/es/close/16';
import View16 from '@carbon/icons/es/view/16';
import Copy16 from '@carbon/icons/es/copy/16';
import Filter16 from '@carbon/icons/es/filter/16';
import Tag16 from '@carbon/icons/es/tag/16';

@Component({
  selector: 'app-tool-registry',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    TabsModule, ButtonModule, NotificationModule, IconModule,
    TagModule, ModalModule, InputModule, DropdownModule, CheckboxModule,
    SearchModule, LoadingModule, SelectModule, ToggleModule, MCPServerFormComponent,
    PageHeaderComponent, PageWrapperComponent,
  ],
  templateUrl: './tool-registry.component.html',
  styleUrls: ['./tool-registry.component.scss'],
})
export class ToolRegistryComponent implements OnInit, OnDestroy {
  tools: Tool[] = [];
  filteredTools: Tool[] = [];
  loading = false;
  searchQuery = '';
  notification: any = null;

  // Category / tag filtering
  categories: Category[] = [];
  selectedCategory = '';
  selectedSubCategory = '';
  activeTagFilters: string[] = [];
  tagInputValue = '';

  // Dropdown items for filter bar
  categoryDropdownItems: any[] = [];
  subCategoryDropdownItems: any[] = [];

  // Dropdown items for modal classification
  formCategoryDropdownItems: any[] = [];
  formSubCategoryDropdownItems: any[] = [];

  // Tool type dropdown for modal
  toolTypeDropdownItems: any[] = [
    { content: 'REST API Tool', id: 'REST', selected: true },
    { content: 'MCP Server', id: 'MCP_SERVER', selected: false },
  ];

  get availableSubCategories(): { id: string; label: string }[] {
    const cat = this.categories.find(c => c.label === this.selectedCategory);
    return cat ? cat.sub_categories : [];
  }

  // Modal state
  showModal = false;
  editingTool: Tool | null = null;
  
  // Import Modal state
  showImportModal = false;
  masterTools: Tool[] = [];
  selectedMasterToolIds = new Set<string>();
  importing = false;
  
  // Registration Type
  toolTypeOptions = [
    { content: 'REST API Tool', value: 'REST' },
    { content: 'MCP Server', value: 'MCP_SERVER' }
  ];
  selectedType = 'REST';

  // Tool Filter
  filterState = {
    MCP_SERVER: true,
    MCP_TOOL: false,
    REST: false
  };

  // REST Form Data
  formData: ToolCreate = {
    name: '',
    description: '',
    type: 'REST',
    is_enabled: true,
    connection_config: {},
    schema_def: {},
    category: '',
    sub_category: '',
    tags: [],
  };
  connectionConfigJson = '{}';
  schemaDefJson = '{}';
  formTagInputValue = '';

  // MCP Form Data (handled via MCPServerFormComponent but using Tool model)
  mcpFormData: ToolCreate | null = null;
  mcpFormValid = false;

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  constructor(
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Add16, TrashCan16, Edit16, Search16, Api16, LogoModelContextProtocol16, Renew16, Close16, View16, Copy16, Filter16, Tag16,
    ]);
  }

  ngOnInit(): void {
    this.platformApi.listCategories().subscribe({
      next: (cats) => {
        this.categories = cats;
        this.categoryDropdownItems = [
          { content: 'All Categories', id: '', selected: true },
          ...cats.map(c => ({ content: c.label, id: c.label, selected: false })),
        ];
        this.formCategoryDropdownItems = [
          { content: 'None', id: '', selected: true },
          ...cats.map(c => ({ content: c.label, id: c.label, selected: false })),
        ];
      },
      error: () => {},
    });
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) {
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
    let list = this.tools;

    // Type filter
    list = list.filter((t) => {
      if (t.type === 'MCP_SERVER' && this.filterState.MCP_SERVER) return true;
      if (t.type === 'MCP_TOOL' && this.filterState.MCP_TOOL) return true;
      if (t.type === 'REST' && this.filterState.REST) return true;
      return false;
    });

    // Category filter
    if (this.selectedCategory) {
      list = list.filter(t => t.category === this.selectedCategory);
    }
    if (this.selectedSubCategory) {
      list = list.filter(t => t.sub_category === this.selectedSubCategory);
    }

    // Active tag filters
    if (this.activeTagFilters.length > 0) {
      list = list.filter(t =>
        this.activeTagFilters.every(tag => (t.tags || []).includes(tag))
      );
    }

    // Text search — covers name, description, category, sub_category, tags
    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase();
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          (t.description || '').toLowerCase().includes(q) ||
          t.type.toLowerCase().includes(q) ||
          (t.category || '').toLowerCase().includes(q) ||
          (t.sub_category || '').toLowerCase().includes(q) ||
          (t.tags || []).some(tag => tag.toLowerCase().includes(q))
      );
    }
    this.filteredTools = list;
  }

  onCategoryFilterChange(): void {
    this.selectedSubCategory = '';
    this.filterTools();
  }

  onSubCategoryFilterChange(): void {
    this.filterTools();
  }

  // Dropdown event handlers — filter bar
  onCategoryDropdownSelect(event: any): void {
    this.selectedCategory = event.item.id;
    this.selectedSubCategory = '';
    const subs = this.selectedCategory
      ? (this.categories.find(c => c.label === this.selectedCategory)?.sub_categories || [])
      : [];
    this.subCategoryDropdownItems = [
      { content: 'All Sub-categories', id: '', selected: true },
      ...subs.map(s => ({ content: s.label, id: s.label, selected: false })),
    ];
    this.filterTools();
  }

  onSubCategoryDropdownSelect(event: any): void {
    this.selectedSubCategory = event.item.id;
    this.filterTools();
  }

  // Dropdown event handlers — modal classification
  onFormCategoryDropdownSelect(event: any): void {
    this.formData.category = event.item.id;
    this.formData.sub_category = '';
    const subs = this.formData.category
      ? (this.categories.find(c => c.label === this.formData.category)?.sub_categories || [])
      : [];
    this.formSubCategoryDropdownItems = [
      { content: 'None', id: '', selected: true },
      ...subs.map(s => ({ content: s.label, id: s.label, selected: false })),
    ];
  }

  onFormSubCategoryDropdownSelect(event: any): void {
    this.formData.sub_category = event.item.id;
  }

  // Tool type dropdown — modal
  onToolTypeDropdownSelect(event: any): void {
    this.selectedType = event.item.id;
  }

  addTagFilter(): void {
    const tag = this.tagInputValue.trim();
    if (tag && !this.activeTagFilters.includes(tag)) {
      this.activeTagFilters = [...this.activeTagFilters, tag];
      this.filterTools();
    }
    this.tagInputValue = '';
  }

  removeTagFilter(tag: string): void {
    this.activeTagFilters = this.activeTagFilters.filter(t => t !== tag);
    this.filterTools();
  }

  clearAllFilters(): void {
    this.selectedCategory = '';
    this.selectedSubCategory = '';
    this.activeTagFilters = [];
    this.searchQuery = '';
    this.filterTools();
  }

  get hasActiveFilters(): boolean {
    return !!(this.selectedCategory || this.selectedSubCategory || this.activeTagFilters.length || this.searchQuery);
  }

  getChildTools(parentId: string): Tool[] {
    return this.tools.filter(t => t.parent_id === parentId);
  }

  truncateWords(text: string | null | undefined, maxWords = 200): string {
    if (!text) return 'No description provided';
    const words = text.split(/\s+/);
    if (words.length <= maxWords) return text;
    return words.slice(0, maxWords).join(' ') + '...';
  }

  // Carbon Search component events
  onSearchChange(value: string): void {
    this.searchQuery = value;
    this.filterTools();
  }

  onSearchClear(): void {
    this.searchQuery = '';
    this.filterTools();
  }

  // ─── CRUD Operations ───────────────────────────────────────────

  openCreateModal(): void {
    this.editingTool = null;
    this.selectedType = 'REST';
    this.formData = {
      name: '',
      description: '',
      type: 'REST',
      is_enabled: true,
      connection_config: {},
      schema_def: {},
      category: '',
      sub_category: '',
      tags: [],
    };
    this.connectionConfigJson = '{}';
    this.schemaDefJson = '{}';
    this.formTagInputValue = '';
    this.mcpFormData = null;
    this.mcpFormValid = false;
    this.showModal = true;
  }

  openEditModal(tool: Tool): void {
    this.editingTool = tool;
    this.selectedType = tool.type === 'MCP_SERVER' ? 'MCP_SERVER' : 'REST';
    this.formTagInputValue = '';
    
    if (tool.type === 'REST') {
      this.formData = {
        name: tool.name,
        description: tool.description || '',
        type: tool.type,
        is_enabled: tool.is_enabled,
        connection_config: tool.connection_config || {},
        schema_def: tool.schema_def || {},
        category: tool.category || '',
        sub_category: tool.sub_category || '',
        tags: [...(tool.tags || [])],
      };
      this.connectionConfigJson = JSON.stringify(tool.connection_config || {}, null, 2);
      this.schemaDefJson = JSON.stringify(tool.schema_def || {}, null, 2);
    } else if (tool.type === 'MCP_SERVER') {
      // MCP Server edit state is handled by the sub-component via input
      this.mcpFormData = {
        name: tool.name,
        type: 'MCP_SERVER',
        transport: tool.transport,
        command: tool.command,
        args: tool.args,
        env: tool.env,
        url: tool.url,
        is_enabled: tool.is_enabled,
        status: tool.status,
        category: tool.category || '',
        sub_category: tool.sub_category || '',
        tags: [...(tool.tags || [])],
      };
      // Also populate formData for category/tags fields used in MCP form section
      this.formData = {
        ...this.formData,
        category: tool.category || '',
        sub_category: tool.sub_category || '',
        tags: [...(tool.tags || [])],
      };
    }
    
    this.showModal = true;
  }

  addFormTag(): void {
    const tag = this.formTagInputValue.trim();
    if (tag && !(this.formData.tags || []).includes(tag)) {
      this.formData.tags = [...(this.formData.tags || []), tag];
    }
    this.formTagInputValue = '';
  }

  removeFormTag(tag: string): void {
    this.formData.tags = (this.formData.tags || []).filter(t => t !== tag);
  }

  get formSubCategories(): { id: string; label: string }[] {
    const cat = this.categories.find(c => c.label === this.formData.category);
    return cat ? cat.sub_categories : [];
  }

  closeModal(): void {
    this.showModal = false;
    this.editingTool = null;
  }

  onTypeChange(event: any): void {
    this.selectedType = event.item.value;
  }

  // Sub-component handlers for MCP
  onMCPFormDataChange(data: any): void {
    this.mcpFormData = {
      ...data,
      type: 'MCP_SERVER'
    };
  }

  onMCPFormValidationChange(isValid: boolean): void {
    this.mcpFormValid = isValid;
  }

  saveTool(): void {
    if (!this.activeWorkspace) return;

    let payload: ToolCreate;

    if (this.selectedType === 'REST') {
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
      payload = {
        ...this.formData,
        type: 'REST',
        category: this.formData.category || undefined,
        sub_category: this.formData.sub_category || undefined,
        tags: this.formData.tags?.length ? this.formData.tags : undefined,
      };
    } else {
      if (!this.mcpFormData || !this.mcpFormValid) return;
      payload = {
        ...this.mcpFormData,
        category: this.formData.category || undefined,
        sub_category: this.formData.sub_category || undefined,
        tags: this.formData.tags?.length ? this.formData.tags : undefined,
      };
    }

    if (this.editingTool) {
      this.platformApi
        .updateTool(this.activeWorkspace.id, this.editingTool.id, payload)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Updated', message: `Tool "${payload.name}" updated.` };
            this.closeModal();
            this.loadTools();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Update Failed', message: err.error?.detail || err.message };
          },
        });
    } else {
      this.platformApi
        .createTool(this.activeWorkspace.id, payload)
        .subscribe({
          next: () => {
            this.notification = { type: 'success', title: 'Registered', message: `Tool "${payload.name}" registered.` };
            this.closeModal();
            this.loadTools();
          },
          error: (err) => {
            this.notification = { type: 'error', title: 'Registration Failed', message: err.error?.detail || err.message };
          },
        });
    }
  }

  // ─── Import from Default Workspace ─────────────────────────────

  defaultWorkspaceId: string | null = null;

  openImportModal(): void {
    if (!this.activeWorkspace) return;
    
    // Find Default Workspace ID
    this.workspaceService.workspaces$.subscribe(wsList => {
      const defaultWs = wsList.find(ws => ws.is_default === true);
      if (!defaultWs) {
        this.notification = { type: 'error', title: 'Not Found', message: 'Default Workspace not found. Ensure the system has been seeded.' };
        return;
      }
      
      if (defaultWs.id === this.activeWorkspace?.id) {
        this.notification = { type: 'info', title: 'Info', message: 'You are already in the Default Workspace' };
        return;
      }

      this.defaultWorkspaceId = defaultWs.id;
      this.loading = true;
      this.platformApi.listTools(defaultWs.id).subscribe({
        next: (tools) => {
          // Only show top-level tools (MCP Servers and REST tools without parents)
          this.masterTools = tools.filter(t => !t.parent_id);
          this.selectedMasterToolIds.clear();
          this.showImportModal = true;
          this.loading = false;
        },
        error: (err) => {
          this.notification = { type: 'error', title: 'Load Failed', message: 'Failed to load master tools' };
          this.loading = false;
        }
      });
    }).unsubscribe();
  }

  closeImportModal(): void {
    this.showImportModal = false;
    this.masterTools = [];
    this.selectedMasterToolIds.clear();
  }

  toggleMasterToolSelection(toolId: string): void {
    if (this.selectedMasterToolIds.has(toolId)) {
      this.selectedMasterToolIds.delete(toolId);
    } else {
      this.selectedMasterToolIds.add(toolId);
    }
  }

  isMasterToolSelected(toolId: string): boolean {
    return this.selectedMasterToolIds.has(toolId);
  }

  importSelectedTools(): void {
    if (!this.activeWorkspace || this.selectedMasterToolIds.size === 0) return;
    
    this.importing = true;
    const toolIds = Array.from(this.selectedMasterToolIds);
    
    this.platformApi.importMasterTools(
      this.activeWorkspace.id,
      toolIds,
      this.defaultWorkspaceId || undefined
    ).subscribe({
      next: (result) => {
        const msg = result.skipped > 0
          ? `Cloned ${result.cloned} tool(s), ${result.skipped} already existed.`
          : `Successfully cloned ${result.cloned} tool(s).`;
        this.notification = { 
          type: 'success', 
          title: 'Import Successful', 
          message: msg,
        };
        this.importing = false;
        this.closeImportModal();
        this.loadTools();
      },
      error: (err) => {
        this.notification = { 
          type: 'error', 
          title: 'Import Failed', 
          message: err.error?.detail || err.message 
        };
        this.importing = false;
      }
    });
  }

  deleteTool(tool: Tool): void {
    if (!this.activeWorkspace) return;
    if (!confirm(`Delete "${tool.name}"? This cannot be undone.`)) return;

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

  testConnection(tool: Tool): void {
    if (!this.activeWorkspace) return;
    this.notification = { type: 'info', title: 'Testing...', message: `Connecting to ${tool.name}...` };
    
    this.platformApi.testToolConnection(this.activeWorkspace.id, tool.id).subscribe({
      next: (result) => {
        if (result.success) {
          this.notification = {
            type: 'success',
            title: 'Success',
            message: `Connected. Found ${result.tools_count} tools.`
          };
        } else {
          this.notification = {
            type: 'error',
            title: 'Failed',
            message: result.error || 'Connection failed'
          };
        }
        this.loadTools();
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Test Failed', message: err.error?.detail || err.message };
      },
    });
  }

  toggleToolStatus(tool: Tool): void {
    this.setToolStatus(tool, !tool.is_enabled);
  }

  setToolStatus(tool: Tool, newStatus: boolean): void {
    if (!this.activeWorkspace) return;
    this.platformApi.updateTool(this.activeWorkspace.id, tool.id, { is_enabled: newStatus }).subscribe({
      next: () => {
        tool.is_enabled = newStatus;
        this.notification = { type: 'success', title: 'Status Updated', message: `Tool ${tool.name} is now ${newStatus ? 'enabled' : 'disabled'}.` };
      },
      error: (err) => {
        this.notification = { type: 'error', title: 'Failed', message: err.message };
        // revert toggle on error by triggering change detection if needed
        setTimeout(() => tool.is_enabled = !newStatus, 0);
      }
    });
  }

  getToolTypeLabel(type: string): string {
    if (type === 'MCP_SERVER') return 'MCP Server';
    if (type === 'MCP_TOOL') return 'MCP Tool';
    return 'REST API';
  }

  getParentServerName(parentId: string): string {
    const parent = this.tools.find(t => t.id === parentId);
    return parent ? parent.name : parentId.substring(0, 8) + '...';
  }

  getStatusColor(status: string): any {
    switch (status) {
      case 'active': return 'green';
      case 'disabled': return 'warm-gray';
      case 'error': return 'red';
      default: return 'gray';
    }
  }

  dismissNotification(): void {
    this.notification = null;
  }
}

