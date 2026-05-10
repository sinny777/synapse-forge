import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
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
import {
  LLMModelConfig,
  ModelRole,
  LLMProvider,
  ProviderCredentials,
  PROVIDER_INFO,
  MODEL_ROLE_INFO,
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
  selectedRole: ModelRole = 'teacher';
  selectedProvider: LLMProvider = 'ollama';
  modelName = '';
  temperature = 0.7;
  maxTokens = 2048;
  credentials: ProviderCredentials = {};
  showCredentials: { [key: string]: boolean } = {};

  // Environment credentials cache
  private envCredentials: any = null;

  // Data
  configurations: LLMModelConfig[] = [];
  filteredConfigurations: LLMModelConfig[] = [];
  selectedRoleFilter: ModelRole | 'all' = 'all';

  // Provider info
  providers = Object.values(PROVIDER_INFO);
  currentProviderInfo: ProviderInfo | null = null;

  // Role info
  roleInfo = MODEL_ROLE_INFO;
  roles: ModelRole[] = ['teacher', 'expansion', 'heavy'];

  // Notifications
  notification: any = null;

  // Subscriptions
  private subs: Subscription[] = [];

  constructor(
    private llmConfigService: LLMConfigService,
    private iconService: IconService,
    private http: HttpClient
  ) {
    this.iconService.registerAll([
      Add16, Edit16, TrashCan16, Save16, Close16,
      Upload16, Download16, View16, ViewOff16, InformationFilled16
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.llmConfigService.configurations$.subscribe(configs => {
        this.configurations = configs;
        this.filterConfigurations();
      })
    );
    this.updateProviderInfo();
    this.loadEnvironmentCredentials();
  }

  /**
   * Load environment credentials from backend
   */
  private async loadEnvironmentCredentials(): Promise<void> {
    try {
      this.envCredentials = await this.http.get<any>('http://localhost:8000/api/env/llm-credentials').toPromise();
    } catch (error) {
      console.warn('Failed to load environment credentials:', error);
    }
  }

  ngOnDestroy(): void {
    this.subs.forEach(sub => sub.unsubscribe());
  }

  /**
   * Filter configurations by role
   */
  filterConfigurations(): void {
    if (this.selectedRoleFilter === 'all') {
      this.filteredConfigurations = this.configurations;
    } else {
      this.filteredConfigurations = this.configurations.filter(
        config => config.role === this.selectedRoleFilter
      );
    }
  }

  /**
   * Get role label
   */
  getRoleLabel(role: ModelRole): string {
    return this.roleInfo[role].label;
  }

  /**
   * Get role icon
   */
  getRoleIcon(role: ModelRole): string {
    return this.roleInfo[role].icon;
  }

  /**
   * Get provider label
   */
  getProviderLabel(provider: LLMProvider): string {
    return PROVIDER_INFO[provider].name;
  }

  /**
   * Get provider icon
   */
  getProviderIcon(provider: LLMProvider): string {
    return PROVIDER_INFO[provider].icon;
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
    this.selectedRole = config.role;
    this.selectedProvider = config.provider;
    this.modelName = config.modelName;
    this.temperature = config.temperature || 0.7;
    this.maxTokens = config.maxTokens || 2048;
    this.credentials = { ...config.credentials };
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
    this.selectedRole = 'teacher';
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
    // Initialize credentials object with values from environment or empty
    const newCredentials: ProviderCredentials = {};
    this.currentProviderInfo.credentialFields.forEach(field => {
      // Try to get value from existing credentials first, then from environment
      let value = this.credentials[field.key] || '';
      
      // If no existing value and we have environment credentials, try to populate from env
      if (!value && this.envCredentials) {
        value = this.envCredentials[field.key] || '';
      }
      
      newCredentials[field.key] = value;
    });
    this.credentials = newCredentials;
  }

  /**
   * Handle provider change
   */
  onProviderChange(): void {
    // Don't clear credentials, let updateProviderInfo populate from environment
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
    const config = {
      role: this.selectedRole,
      provider: this.selectedProvider,
      modelName: this.modelName.trim(),
      temperature: this.temperature,
      maxTokens: this.maxTokens,
      credentials: this.credentials
    };

    // Validate
    const validation = this.llmConfigService.validateModelConfig(config);
    if (!validation.valid) {
      this.showNotification('error', 'Validation Error', validation.errors.join(', '));
      return;
    }

    try {
      if (this.modalMode === 'add') {
        this.llmConfigService.addConfiguration(config);
        this.showNotification('success', 'Success', 'Configuration added successfully');
      } else if (this.editingConfigId) {
        this.llmConfigService.updateConfiguration(this.editingConfigId, config);
        this.showNotification('success', 'Success', 'Configuration updated successfully');
      }
      this.closeModal();
    } catch (error) {
      this.showNotification('error', 'Error', 'Failed to save configuration');
    }
  }

  /**
   * Delete configuration
   */
  deleteConfiguration(config: LLMModelConfig): void {
    if (confirm(`Are you sure you want to delete the configuration for ${config.modelName}?`)) {
      const success = this.llmConfigService.deleteConfiguration(config.id);
      if (success) {
        this.showNotification('success', 'Success', 'Configuration deleted successfully');
      } else {
        this.showNotification('error', 'Error', 'Failed to delete configuration');
      }
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
  async importConfigurations(event: any): Promise<void> {
    const file = event.target.files[0];
    if (!file) return;

    const result = await this.llmConfigService.importConfigurations(file);
    
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

    // Reset file input
    event.target.value = '';
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

  /**
   * Get role summary
   */
  getRoleSummary(role: ModelRole): string {
    const summary = this.llmConfigService.getRoleSummary(role);
    return `${summary.count} configuration(s)`;
  }

  /**
   * Handle role filter change
   */
  onRoleFilterChange(): void {
    this.filterConfigurations();
  }
}

// Made with Bob
