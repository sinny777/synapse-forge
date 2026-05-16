import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule,
  SelectModule,
  InputModule,
  ModalModule,
  NotificationModule,
  TableModule,
  TagModule,
  DropdownModule,
  TooltipModule
} from 'carbon-components-angular';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';

import Add16 from '@carbon/icons/es/add/16';
import Edit16 from '@carbon/icons/es/edit/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Save16 from '@carbon/icons/es/save/16';
import Close16 from '@carbon/icons/es/close/16';
import Upload16 from '@carbon/icons/es/upload/16';
import Download16 from '@carbon/icons/es/download/16';
import View16 from '@carbon/icons/es/view/16';
import ViewOff16 from '@carbon/icons/es/view--off/16';
import InformationFilled16 from '@carbon/icons/es/information--filled/16';

import { LLMConfigService } from '../../services/llm-config.service';
import { WorkspaceService } from '../../services/workspace.service';
import { Workspace } from '../../models/platform.model';
import {
  LLMModelConfig,
  LLMModelConfigCreate,
  LLMProvider,
  ProviderCredentials,
  PROVIDER_INFO,
  ProviderInfo,
  CredentialField
} from '../../models/llm-config.model';

@Component({
  selector: 'app-llm-config',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    SelectModule,
    InputModule,
    ModalModule,
    NotificationModule,
    TableModule,
    TagModule,
    DropdownModule,
    IconModule,
    TooltipModule
  ],
  templateUrl: './llm-config.component.html',
  styleUrls: ['./llm-config.component.scss']
})
export class LLMConfigComponent implements OnInit, OnDestroy {
  // Modal state
  showModal = false;
  modalMode: 'add' | 'edit' = 'add';
  editingConfigId: string | null = null;

  // Form data
  configName = '';
  selectedProvider: LLMProvider = 'ollama';
  modelName = '';
  temperature = 0.7;
  maxTokens = 2048;
  credentials: ProviderCredentials = {};
  showCredentials: { [key: string]: boolean } = {};

  // Data
  configurations: LLMModelConfig[] = [];

  // Workspace context
  activeWorkspace: Workspace | null = null;
  isDefaultWorkspace = false;

  // Provider info
  providers: ProviderInfo[] = Object.values(PROVIDER_INFO);
  currentProviderInfo: ProviderInfo | null = null;

  // Notifications
  notification: any = null;

  // Subscriptions
  private subs: Subscription[] = [];

  constructor(
    private llmConfigService: LLMConfigService,
    private workspaceService: WorkspaceService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Add16, Edit16, TrashCan16, Save16, Close16,
      Upload16, Download16, View16, ViewOff16, InformationFilled16
    ]);
  }

  ngOnInit(): void {
    // Subscribe to workspace changes
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe(ws => {
        this.activeWorkspace = ws;
        this.isDefaultWorkspace = ws?.is_default ?? false;
        if (ws) {
          this.llmConfigService.loadConfigurations(ws.id);
        }
      })
    );

    // Subscribe to configuration updates
    this.subs.push(
      this.llmConfigService.configurations$.subscribe(configs => {
        this.configurations = configs;
      })
    );

    this.updateProviderInfo();
  }

  ngOnDestroy(): void {
    this.subs.forEach(sub => sub.unsubscribe());
  }

  /**
   * Get provider label
   */
  getProviderLabel(provider: LLMProvider): string {
    return PROVIDER_INFO[provider]?.name ?? provider;
  }

  /**
   * Get provider icon
   */
  getProviderIcon(provider: LLMProvider): string {
    return PROVIDER_INFO[provider]?.icon ?? '🔧';
  }

  /**
   * Open modal to add new configuration
   */
  openAddModal(): void {
    this.modalMode = 'add';
    this.resetForm();
    this.showModal = true;
  }

  /**
   * Open modal to edit configuration
   */
  openEditModal(config: LLMModelConfig): void {
    this.modalMode = 'edit';
    this.editingConfigId = config.id;
    this.configName = config.name;
    this.selectedProvider = config.provider;
    this.modelName = config.model_name;
    this.temperature = config.temperature ?? 0.7;
    this.maxTokens = config.max_tokens ?? 2048;
    this.credentials = { ...(config.credentials || {}) };
    this.updateProviderInfo();
    this.showModal = true;
  }

  /**
   * Close modal
   */
  closeModal(): void {
    this.showModal = false;
    this.resetForm();
  }

  /**
   * Reset form
   */
  resetForm(): void {
    this.editingConfigId = null;
    this.configName = '';
    this.selectedProvider = 'ollama';
    this.modelName = '';
    this.temperature = 0.7;
    this.maxTokens = 2048;
    this.credentials = {};
    this.showCredentials = {};
    this.updateProviderInfo();
  }

  /**
   * Update provider info when provider changes
   */
  updateProviderInfo(): void {
    this.currentProviderInfo = PROVIDER_INFO[this.selectedProvider];
    const newCredentials: ProviderCredentials = {};
    this.currentProviderInfo.credentialFields.forEach((field: CredentialField) => {
      newCredentials[field.key] = this.credentials[field.key] || '';
    });
    this.credentials = newCredentials;
  }

  /**
   * Handle provider change
   */
  onProviderChange(): void {
    this.showCredentials = {};
    this.updateProviderInfo();
  }

  /**
   * Toggle credential visibility
   */
  toggleCredentialVisibility(key: string): void {
    this.showCredentials[key] = !this.showCredentials[key];
  }

  /**
   * Save configuration
   */
  saveConfiguration(): void {
    if (!this.activeWorkspace) {
      this.showNotification('error', 'Error', 'No workspace selected');
      return;
    }

    const configData: LLMModelConfigCreate = {
      name: this.configName.trim(),
      provider: this.selectedProvider,
      model_name: this.modelName.trim(),
      temperature: this.temperature,
      max_tokens: this.maxTokens,
      credentials: this.credentials
    };

    // Validate
    const validation = this.llmConfigService.validateModelConfig(configData);
    if (!validation.valid) {
      this.showNotification('error', 'Validation Error', validation.errors.join(', '));
      return;
    }

    if (this.modalMode === 'add') {
      this.llmConfigService
        .createConfiguration(this.activeWorkspace.id, configData)
        .subscribe({
          next: () => {
            this.showNotification('success', 'Success', 'Configuration added successfully');
            this.closeModal();
          },
          error: (err) => {
            const detail = err.error?.detail || 'Failed to save configuration';
            this.showNotification('error', 'Error', detail);
          }
        });
    } else if (this.editingConfigId) {
      this.llmConfigService
        .updateConfiguration(this.activeWorkspace.id, this.editingConfigId, configData)
        .subscribe({
          next: () => {
            this.showNotification('success', 'Success', 'Configuration updated successfully');
            this.closeModal();
          },
          error: (err) => {
            const detail = err.error?.detail || 'Failed to update configuration';
            this.showNotification('error', 'Error', detail);
          }
        });
    }
  }

  /**
   * Delete configuration
   */
  deleteConfiguration(config: LLMModelConfig): void {
    if (!this.activeWorkspace) return;

    if (confirm(`Are you sure you want to delete "${config.name}"?`)) {
      this.llmConfigService
        .deleteConfiguration(this.activeWorkspace.id, config.id)
        .subscribe({
          next: () => {
            this.showNotification('success', 'Success', 'Configuration deleted successfully');
          },
          error: (err) => {
            const detail = err.error?.detail || 'Failed to delete configuration';
            this.showNotification('error', 'Error', detail);
          }
        });
    }
  }

  /**
   * Export configurations
   */
  exportConfigurations(): void {
    this.llmConfigService.exportConfigurations();
    this.showNotification('success', 'Success', 'Configurations exported successfully');
  }

  /**
   * Import configurations
   */
  async importConfigurations(event: Event): Promise<void> {
    if (!this.activeWorkspace) return;

    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    const result = await this.llmConfigService.importConfigurations(
      this.activeWorkspace.id,
      file
    );

    if (result.success) {
      this.showNotification(
        'success',
        'Import Successful',
        `Imported ${result.imported} configuration(s)`
      );
    } else {
      this.showNotification(
        'error',
        'Import Failed',
        result.errors.join(', ')
      );
    }

    if (input) {
      input.value = '';
    }
  }

  /**
   * Show notification
   */
  showNotification(type: 'success' | 'error' | 'info' | 'warning', title: string, message: string): void {
    this.notification = {
      type,
      title,
      message,
      showClose: true
    };

    // Auto-hide after 5 seconds
    setTimeout(() => {
      this.notification = null;
    }, 5000);
  }

  /**
   * Close notification
   */
  closeNotification(): void {
    this.notification = null;
  }

  /**
   * Get credential input type
   */
  getCredentialInputType(field: CredentialField, key: string): string {
    if (field.type === 'password') {
      return this.showCredentials[key] ? 'text' : 'password';
    }
    return field.type === 'url' ? 'url' : 'text';
  }
}

// Made with Bob
