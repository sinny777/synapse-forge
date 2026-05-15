import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  TabsModule,
  ButtonModule,
  InputModule,
  SelectModule,
  TagModule,
  IconModule,
  NotificationModule,
  ToggleModule,
} from 'carbon-components-angular';
import { ToggletipModule } from 'carbon-components-angular/toggletip';
import { IconService } from 'carbon-components-angular/icon';
import { z } from 'zod';
import { Tool, ToolCreate, MCPTransport } from '../../models/platform.model';

import View16 from '@carbon/icons/es/view/16';
import ViewOff16 from '@carbon/icons/es/view--off/16';
import Code16 from '@carbon/icons/es/code/16';
import Edit16 from '@carbon/icons/es/edit/16';
import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import WarningAlt16 from '@carbon/icons/es/warning--alt/16';
import Help16 from '@carbon/icons/es/help/16';

interface EnvVar {
  key: string;
  value: string;
  masked: boolean;
}

const mcpServerSchema = z.object({
  name: z.string().min(1, "Display name is required"),
  transport: z.enum(['stdio', 'sse']),
  command: z.string().optional(),
  args: z.array(z.string()).optional(),
  env: z.record(z.string(), z.string()).optional(),
  url: z.string().optional(),
  status: z.enum(['active', 'disabled', 'error']).optional(),
  is_enabled: z.boolean().optional()
}).superRefine((data, ctx) => {
  if (data.transport === 'stdio') {
    if (!data.command || data.command.trim() === '') {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Command is required for stdio transport",
        path: ["command"]
      });
    }
  } else if (data.transport === 'sse') {
    if (!data.url || data.url.trim() === '') {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "URL is required for sse transport",
        path: ["url"]
      });
    } else {
      try {
        new URL(data.url);
      } catch {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Invalid URL format",
          path: ["url"]
        });
      }
    }
  }
});

@Component({
  selector: 'app-mcp-server-form',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    TabsModule,
    ButtonModule,
    InputModule,
    SelectModule,
    TagModule,
    IconModule,
    NotificationModule,
    ToggleModule,
    ToggletipModule,
  ],
  template: `
    <div class="mcp-form-container">
      <!-- Tab Switcher & Status Toggle -->
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--cds-border-subtle);">
        <cds-tab-header-group [followFocus]="true" class="form-tabs">
          <button cdsTabHeader [active]="activeView === 'form'" (click)="switchView('form')">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <svg cdsIcon="edit" size="16"></svg>
              <span>Form View</span>
            </div>
          </button>
          <button cdsTabHeader [active]="activeView === 'json'" (click)="switchView('json')">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <svg cdsIcon="code" size="16"></svg>
              <span>JSON View</span>
            </div>
          </button>
        </cds-tab-header-group>

        <!-- Enable/Disable Toggle -->
        <div style="margin-left: auto; display: flex; align-items: center;">
          <cds-toggle
            *ngIf="isEditMode"
            size="sm"
            [checked]="!!formData.is_enabled"
            [disabled]="isReadonly"
            (checkedChange)="formData.is_enabled = $event; onFormChange()"
            [onText]="'Enabled'"
            [offText]="'Disabled'">
          </cds-toggle>
        </div>
      </div>

      <!-- Form View -->
      <div *ngIf="activeView === 'form'" class="view-content form-view">
        <div class="form-grid">
          <!-- Name -->
          <div class="cds--form-item">
            <cds-label>Server Display Name <span class="required">*</span></cds-label>
            <input
              cdsText
              [(ngModel)]="formData.name"
              placeholder="e.g., Weather API Server"
              (ngModelChange)="onFormChange()"
              [invalid]="hasError('name')"
              [disabled]="isReadonly"
            />
            <div *ngIf="hasError('name')" class="cds--form-requirement">{{ getError('name') }}</div>
          </div>

          <!-- Transport Type -->
          <div class="cds--form-item">
            <cds-label>Transport Protocol <span class="required">*</span></cds-label>
            <cds-select
              [(ngModel)]="formData.transport"
              [disabled]="isReadonly"
              (ngModelChange)="onFormChange()">
              <option value="stdio">stdio (Local Process)</option>
              <option value="sse">sse (Remote Server)</option>
            </cds-select>
          </div>
        </div>

        <div class="protocol-help">
          <cds-tag type="blue" size="sm">stdio</cds-tag> <span>Local process spawning</span>
          <cds-tag type="magenta" size="sm">sse</cds-tag> <span>Remote SSE/HTTP connection</span>
        </div>

        <!-- Stdio Configuration -->
        <div *ngIf="formData.transport === 'stdio'" class="transport-config-panel">
          <div class="panel-header">
            <h4 class="config-section-title">Local Process Settings</h4>
          </div>

          <!-- Command -->
          <div class="cds--form-item">
            <cds-label>Executable Command <span class="required">*</span></cds-label>
            <input
              cdsText
              [(ngModel)]="formData.command"
              placeholder="e.g., node, python, npx"
              (ngModelChange)="onFormChange()"
              [invalid]="hasError('command')"
              [disabled]="isReadonly"
            />
            <div *ngIf="hasError('command')" class="cds--form-requirement">{{ getError('command') }}</div>
          </div>

          <!-- Arguments -->
          <div class="cds--form-item">
            <cds-label>Arguments <span class="helper-text">(One argument per line)</span></cds-label>
            <textarea
              cdsTextArea
              rows="4"
              [(ngModel)]="argsText"
              placeholder="e.g.&#10;server.js&#10;--port&#10;3000"
              (ngModelChange)="onArgsChange()"
              class="mono-font"
              [disabled]="isReadonly"
            ></textarea>
          </div>

          <!-- Environment Variables -->
          <div class="cds--form-item">
            <cds-label>Environment Variables <span class="helper-text">(Sensitive keys/tokens)</span></cds-label>
            <div class="env-builder">
              <div *ngFor="let envVar of envVars; let i = index" class="env-row">
                <input
                  cdsText
                  [(ngModel)]="envVar.key"
                  placeholder="VARIABLE_NAME"
                  class="env-key mono-font"
                  (ngModelChange)="onEnvChange()"
                  [disabled]="isReadonly"
                />
                <div class="env-value-container">
                  <input
                    [type]="envVar.masked ? 'password' : 'text'"
                    cdsText
                    [(ngModel)]="envVar.value"
                    placeholder="value"
                    class="env-value mono-font"
                    (ngModelChange)="onEnvChange()"
                    [disabled]="isReadonly"
                  />
                  <button
                    cdsButton="ghost"
                    size="sm"
                    class="mask-toggle-btn"
                    (click)="toggleMask(i)"
                    [title]="envVar.masked ? 'Reveal value' : 'Hide value'">
                    <svg [cdsIcon]="envVar.masked ? 'view' : 'view--off'" size="16"></svg>
                  </button>
                </div>
                <button
                  *ngIf="!isReadonly"
                  cdsButton="danger--ghost"
                  size="sm"
                  class="delete-row-btn"
                  (click)="removeEnvVar(i)"
                  title="Remove variable">
                  <svg cdsIcon="trash-can" size="16"></svg>
                </button>
              </div>
              <button *ngIf="!isReadonly" cdsButton="tertiary" size="sm" (click)="addEnvVar()" class="add-var-btn">
                <svg cdsIcon="add" size="16" class="cds--btn__icon"></svg>
                Add Environment Variable
              </button>
            </div>
          </div>
        </div>

        <!-- SSE Configuration -->
        <div *ngIf="formData.transport === 'sse'" class="transport-config-panel">
          <div class="panel-header">
            <h4 class="config-section-title">Remote Server Settings</h4>
          </div>

          <!-- URL -->
          <div class="cds--form-item">
            <cds-label>SSE Endpoint URL <span class="required">*</span></cds-label>
            <input
              cdsText
              [(ngModel)]="formData.url"
              placeholder="https://mcp.your-server.com/sse"
              type="url"
              (ngModelChange)="onFormChange()"
              [invalid]="hasError('url')"
              [disabled]="isReadonly"
            />
            <div *ngIf="hasError('url')" class="cds--form-requirement">{{ getError('url') }}</div>
          </div>
        </div>
      </div>

      <!-- JSON View -->
      <div *ngIf="activeView === 'json'" class="view-content json-view">
        <div class="editor-container">
          <div class="editor-header">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span class="editor-title">configuration.json</span>
              <cds-toggletip align="bottom">
                <button cdsToggletipButton ariaLabel="Show schema reference">
                  <svg cdsIcon="help" size="16"></svg>
                </button>
                <div cdsToggletipContent>
                  <div style="padding: 0.5rem; max-width: 400px;">
                    <p style="margin-bottom: 0.5rem; font-size: 0.875rem;">The configuration follows the standard MCP server format:</p>
                    <pre class="schema-preview mono-font" style="margin: 0;">{{jsonSchemaExample}}</pre>
                  </div>
                </div>
              </cds-toggletip>
            </div>
            <div class="status-indicators">
              <cds-tag *ngIf="!jsonError" type="green" size="sm">
                <svg cdsIcon="checkmark" size="12" class="tag-icon-left"></svg>
                Valid
              </cds-tag>
              <cds-tag *ngIf="jsonError" type="red" size="sm">
                <svg cdsIcon="warning--alt" size="12" class="tag-icon-left"></svg>
                Invalid
              </cds-tag>
            </div>
          </div>
          <textarea
            cdsTextArea
            class="json-editor mono-font" 
            [(ngModel)]="jsonText"
            (ngModelChange)="onJsonChange()"
            [class.has-error]="jsonError"
            placeholder='{ ... }'
            rows="13"
            [disabled]="isReadonly"
          ></textarea>
        </div>
        
        <!-- JSON Error Message -->
        <div *ngIf="jsonError" class="error-panel">
          <svg cdsIcon="warning--alt" size="16"></svg>
          <div class="error-content">
            <div class="error-title">JSON Syntax Error</div>
            <div class="error-message">{{ jsonError }}</div>
          </div>
        </div>
      </div>

      <!-- Discovered Tools Visible in Both Views -->
      <div *ngIf="isEditMode && formData.is_enabled && childTools?.length" class="discovered-tools-panel" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--cds-border-subtle);">
        <div class="panel-header" style="margin-bottom: 0.75rem;">
          <h4 class="config-section-title">Discovered Tools</h4>
        </div>
        <div style="display: flex; flex-direction: column; gap: 0.5rem; max-height: 250px; overflow-y: auto;">
          <div *ngFor="let child of childTools" style="background: var(--cds-layer-02, #393939); padding: 0.75rem; border-radius: 4px; border-left: 2px solid var(--cds-support-info, #a56eff);">
            <div style="font-weight: 600; font-size: 0.875rem; color: var(--cds-text-primary, #f4f4f4); margin-bottom: 0.25rem;">{{ child.name }}</div>
            <div style="font-size: 0.75rem; color: var(--cds-text-secondary, #c6c6c6);">{{ truncateWords(child.description || '') }}</div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .mcp-form-container {
      display: flex;
      flex-direction: column;
      gap: 1rem;
      width: 100%;
    }

    .form-tabs {
      border-bottom: 1px solid var(--cds-border-subtle);
      margin-bottom: 0.5rem;
    }

    .tab-icon { margin-right: 0.5rem; }

    .view-content {
      display: flex;
      flex-direction: column;
      gap: 1rem;
      animation: fadeIn 0.2s ease-out;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .form-grid {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      width: 100%;
    }

    .required { color: var(--cds-support-error); }

    .helper-text {
      font-size: 0.75rem;
      color: var(--cds-text-secondary);
      margin-left: 0.25rem;
    }

    .protocol-help {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.75rem;
      color: var(--cds-text-secondary);
    }

    .transport-config-panel {
      background: var(--cds-layer-01);
      border: 1px solid var(--cds-border-subtle);
      border-radius: 4px;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      width: 100%;
    }

    .config-section-title {
      font-size: 0.875rem;
      font-weight: 600;
      color: var(--cds-text-primary);
    }

    .mono-font {
      font-family: 'IBM Plex Mono', 'Menlo', 'Monaco', monospace !important;
      font-size: 0.875rem !important;
    }

    .env-builder {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      margin-top: 0.25rem;
    }

    .env-row {
      display: flex;
      gap: 0.75rem;
      align-items: center;
      width: 100%;
      margin-bottom: 0.5rem;

      .env-key {
        flex: 1;
      }

      .env-value-container {
        flex: 2;
      }
    }

    .env-value-container {
      position: relative;
      display: flex;
      align-items: center;
      flex: 2;
      
      .env-value {
        width: 100%;
      }
    }

    .mask-toggle-btn {
      position: absolute;
      right: 4px;
      height: 32px;
      width: 32px;
      padding: 0;
      border: none;
      background: transparent;
      color: var(--cds-icon-primary);
    }

    .delete-row-btn {
      height: 40px;
      width: 40px;
      flex: 0 0 40px;
    }

    .add-var-btn { margin-top: 0.5rem; align-self: flex-start; }

    /* JSON Editor Styles */
    .editor-container {
      display: flex;
      flex-direction: column;
      border: 1px solid var(--cds-border-subtle);
      border-radius: 4px;
      overflow: hidden;
    }

    .editor-header {
      background: var(--cds-layer-02);
      padding: 0.25rem 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--cds-border-subtle);
      height: 40px;
    }

    .editor-title {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--cds-text-secondary);
    }

    .status-indicators {
      display: flex;
      align-items: center;
    }

    .tag-icon-left {
      margin-right: 4px;
    }

    .json-editor {
      width: 100%;
      height: 350px;
      min-height: 200px;
      resize: vertical;
      border: none !important;
      background: var(--cds-field-01) !important;
      padding: 1rem !important;
      line-height: 1.6 !important;
      overflow-y: auto !important;
    }

    .json-editor.has-error { border-left: 4px solid var(--cds-support-error) !important; }

    .error-panel {
      display: flex;
      gap: 1rem;
      padding: 0.75rem;
      background: var(--cds-support-error-inverse);
      color: white;
      border-radius: 4px;
    }

    .error-content { display: flex; flex-direction: column; gap: 0.125rem; }
    .error-title { font-weight: 600; font-size: 0.875rem; }
    .error-message { font-size: 0.75rem; opacity: 0.9; }

    .json-docs {
      background: var(--cds-layer-01);
      padding: 1rem;
      border-radius: 4px;
      border: 1px solid var(--cds-border-subtle);
    }

    .json-docs h5 { font-size: 0.875rem; margin-bottom: 0.25rem; }
    .json-docs p { font-size: 0.75rem; color: var(--cds-text-secondary); margin-bottom: 0.75rem; }

    .schema-preview {
      margin: 0;
      padding: 0.75rem;
      background: var(--cds-layer-02);
      border-radius: 4px;
      font-size: 0.75rem;
      color: var(--cds-text-primary);
      overflow-x: auto;
      max-height: 150px;
      overflow-y: auto;
    }
  `],
})
export class MCPServerFormComponent implements OnInit, OnChanges {
  @Input() server: Tool | null = null;
  @Input() isEditMode = false;
  @Input() isReadonly = false;
  @Input() childTools: Tool[] = [];
  @Output() formDataChange = new EventEmitter<ToolCreate>();
  @Output() validationChange = new EventEmitter<boolean>();

  activeView: 'form' | 'json' = 'form';
  formData: ToolCreate = {
    name: '',
    type: 'MCP_SERVER',
    transport: 'stdio',
    command: '',
    args: [],
    env: {},
    url: '',
    status: 'active',
  };

  // Form-specific state
  argsText = '';
  envVars: EnvVar[] = [];

  // JSON view state
  jsonText = '';
  jsonError = '';

  // Zod Errors
  formErrors: Record<string, string> = {};

  jsonSchemaExample = `{
  "name": "My MCP Server",
  "transport": "stdio",
  "is_enabled": true,
  "command": "node",
  "args": ["server.js"],
  "env": {
    "API_KEY": "your-key"
  }
}`;

  constructor(private iconService: IconService) {
    this.iconService.registerAll([
      View16, ViewOff16, Code16, Edit16, Add16, TrashCan16, Checkmark16, WarningAlt16, Help16
    ]);
  }

  ngOnInit(): void {
    this.initializeForm();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['server'] && this.server) {
      this.initializeForm();
    }
  }

  private initializeForm(): void {
    if (this.server) {
      this.formData = {
        name: this.server.name,
        type: 'MCP_SERVER',
        transport: this.server.transport || 'stdio',
        command: this.server.command,
        args: this.server.args || [],
        env: this.server.env || {},
        url: this.server.url,
        status: this.server.status || 'active',
        is_enabled: this.server.is_enabled ?? true,
      };
    }

    // Initialize form-specific state
    this.argsText = (this.formData.args || []).join('\n');
    this.envVars = Object.entries(this.formData.env || {}).map(([key, value]) => ({
      key,
      value,
      masked: true,
    }));

    // Initial validation
    this.validateAndEmit();
  }

  // ─── View Switching ─────────────────────────────────────────────────────

  switchView(view: 'form' | 'json'): void {
    if (view === 'json' && this.activeView === 'form') {
      this.syncFormToJson();
    } else if (view === 'form' && this.activeView === 'json') {
      this.syncJsonToForm();
    }
    this.activeView = view;
  }

  // ─── Form → JSON Sync ───────────────────────────────────────────────────

  private syncFormToJson(): void {
    const cleanData = this.getNormalizedFormData();
    this.jsonText = JSON.stringify(cleanData, null, 2);
    this.jsonError = '';
  }

  private getNormalizedFormData(): ToolCreate {
    const data: ToolCreate = {
      name: this.formData.name,
      type: 'MCP_SERVER',
      transport: this.formData.transport,
      status: this.formData.status,
      is_enabled: this.formData.is_enabled,
    };

    if (this.formData.transport === 'stdio') {
      data.command = this.formData.command;
      if (this.formData.args && this.formData.args.length > 0) {
        data.args = this.formData.args;
      }
      if (this.formData.env && Object.keys(this.formData.env).length > 0) {
        data.env = this.formData.env;
      }
    } else {
      data.url = this.formData.url;
    }

    return data;
  }

  // ─── JSON → Form Sync ───────────────────────────────────────────────────

  private syncJsonToForm(): void {
    if (!this.jsonText.trim()) return;

    try {
      const parsed = JSON.parse(this.jsonText);
      this.formData = {
        name: parsed.name || '',
        type: 'MCP_SERVER',
        transport: parsed.transport || 'stdio',
        command: parsed.command,
        args: parsed.args || [],
        env: parsed.env || {},
        url: parsed.url,
        status: parsed.status || 'active',
        is_enabled: parsed.is_enabled ?? true,
      };

      // Update UI state from model
      this.argsText = (this.formData.args || []).join('\n');
      this.envVars = Object.entries(this.formData.env || {}).map(([key, value]) => ({
        key,
        value,
        masked: true,
      }));

      this.jsonError = '';
      this.validateAndEmit();
    } catch (error) {
      this.jsonError = (error as Error).message;
    }
  }

  // ─── Event Handlers ─────────────────────────────────────────────────────

  onFormChange(): void {
    this.validateAndEmit();
  }

  onArgsChange(): void {
    this.formData.args = this.argsText
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0);
    this.onFormChange();
  }

  onEnvChange(): void {
    this.formData.env = {};
    this.envVars.forEach(envVar => {
      const key = envVar.key.trim();
      if (key) {
        this.formData.env![key] = envVar.value;
      }
    });
    this.onFormChange();
  }

  onJsonChange(): void {
    try {
      const parsed = JSON.parse(this.jsonText);
      this.jsonError = '';

      const result = mcpServerSchema.safeParse(parsed);
      if (!result.success) {
        this.jsonError = result.error.issues.map((e: any) => `${e.path.join('.')}: ${e.message}`).join(', ');
        this.validationChange.emit(false);
      } else {
        this.validationChange.emit(true);
        this.formDataChange.emit({ ...result.data, type: 'MCP_SERVER' } as ToolCreate);
      }
    } catch (error) {
      this.jsonError = `Invalid JSON Syntax: ${(error as Error).message}`;
      this.validationChange.emit(false);
    }
  }

  // ─── Env Var UI Actions ─────────────────────────────────────────────────

  addEnvVar(): void {
    this.envVars.push({ key: '', value: '', masked: true });
  }

  removeEnvVar(index: number): void {
    this.envVars.splice(index, 1);
    this.onEnvChange();
  }

  toggleMask(index: number): void {
    this.envVars[index].masked = !this.envVars[index].masked;
  }

  // ─── Validation Logic ───────────────────────────────────────────────────

  private validateAndEmit(): void {
    this.formErrors = {};
    const normalizedData = this.getNormalizedFormData();
    const result = mcpServerSchema.safeParse(normalizedData);

    if (!result.success) {
      result.error.issues.forEach((err: any) => {
        const path = err.path.join('.');
        if (!this.formErrors[path]) {
          this.formErrors[path] = err.message;
        }
      });
      this.validationChange.emit(false);
    } else {
      this.validationChange.emit(true);
      this.formDataChange.emit(normalizedData);
    }
  }

  hasError(field: string): boolean {
    return !!this.formErrors[field];
  }

  getError(field: string): string {
    return this.formErrors[field] || '';
  }

  truncateWords(text: string, limit: number = 200): string {
    if (!text) return '';
    const words = text.split(' ');
    if (words.length > limit) {
      return words.slice(0, limit).join(' ') + '...';
    }
    return text;
  }
}
