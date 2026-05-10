import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import {
  LLMModelConfig,
  ModelRole,
  LLMProvider,
  ProviderCredentials,
  PROVIDER_INFO
} from '../models/llm-config.model';

@Injectable({
  providedIn: 'root'
})
export class LLMConfigService {
  private readonly STORAGE_KEY = 'ntr_llm_configurations';
  private readonly API_URL = 'http://localhost:8000/api';
  
  private _configurations = new BehaviorSubject<LLMModelConfig[]>([]);
  public configurations$ = this._configurations.asObservable();

  constructor(private http: HttpClient) {
    this.loadConfigurations();
    this.initializeFromEnvironment();
  }

  /**
   * Initialize configurations from environment variables
   */
  private async initializeFromEnvironment(): Promise<void> {
    try {
      const envCreds = await this.http.get<any>(`${this.API_URL}/env/llm-credentials`).toPromise();
      
      if (!envCreds) return;

      const existingConfigs = this._configurations.value;
      
      // Create configurations from environment if they don't exist
      const roles: ModelRole[] = ['teacher', 'expansion', 'heavy'];
      
      roles.forEach(role => {
        const modelKey = `${role}_model`;
        const modelName = envCreds[modelKey];
        
        if (modelName && !existingConfigs.some(c => c.role === role)) {
          // Determine provider from model name
          let provider: LLMProvider = 'ollama';
          let credentials: ProviderCredentials = {};
          
          if (modelName.startsWith('gpt')) {
            provider = 'openai';
            credentials = { api_key: envCreds.openai_api_key || '' };
          } else if (modelName.startsWith('claude')) {
            provider = 'anthropic';
            credentials = { api_key: envCreds.anthropic_api_key || '' };
          } else if (modelName.startsWith('gemini')) {
            provider = 'google';
            credentials = { api_key: envCreds.google_api_key || '' };
          } else if (modelName.startsWith('ollama/')) {
            provider = 'ollama';
            credentials = { api_base: envCreds.ollama_api_base || 'http://localhost:11434' };
          }
          
          this.addConfiguration({
            role,
            provider,
            modelName: modelName.replace('ollama/', ''),
            credentials,
            temperature: 0.7,
            maxTokens: 2048
          });
        }
      });
    } catch (error) {
      console.warn('Failed to initialize from environment variables:', error);
    }
  }

  /**
   * Load configurations from localStorage
   */
  private loadConfigurations(): void {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      if (stored) {
        const configs = JSON.parse(stored);
        // Convert date strings back to Date objects
        configs.forEach((config: any) => {
          config.createdAt = new Date(config.createdAt);
          config.updatedAt = new Date(config.updatedAt);
        });
        this._configurations.next(configs);
      }
    } catch (error) {
      console.error('Failed to load LLM configurations:', error);
      this._configurations.next([]);
    }
  }

  /**
   * Save configurations to localStorage
   */
  private saveConfigurations(configs: LLMModelConfig[]): void {
    try {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(configs));
      this._configurations.next(configs);
    } catch (error) {
      console.error('Failed to save LLM configurations:', error);
      throw new Error('Failed to save configurations');
    }
  }

  /**
   * Get all configurations
   */
  getConfigurations(): LLMModelConfig[] {
    return this._configurations.value;
  }

  /**
   * Get configurations by role
   */
  getConfigurationsByRole(role: ModelRole): LLMModelConfig[] {
    return this._configurations.value.filter(config => config.role === role);
  }

  /**
   * Get configuration by ID
   */
  getConfigurationById(id: string): LLMModelConfig | undefined {
    return this._configurations.value.find(config => config.id === id);
  }

  /**
   * Add a new configuration
   */
  addConfiguration(config: Omit<LLMModelConfig, 'id' | 'createdAt' | 'updatedAt'>): LLMModelConfig {
    const newConfig: LLMModelConfig = {
      ...config,
      id: this.generateId(),
      createdAt: new Date(),
      updatedAt: new Date()
    };

    const configs = [...this._configurations.value, newConfig];
    this.saveConfigurations(configs);
    return newConfig;
  }

  /**
   * Update an existing configuration
   */
  updateConfiguration(id: string, updates: Partial<Omit<LLMModelConfig, 'id' | 'createdAt' | 'updatedAt'>>): LLMModelConfig | null {
    const configs = this._configurations.value;
    const index = configs.findIndex(c => c.id === id);
    
    if (index === -1) {
      return null;
    }

    const updatedConfig: LLMModelConfig = {
      ...configs[index],
      ...updates,
      updatedAt: new Date()
    };

    const newConfigs = [...configs];
    newConfigs[index] = updatedConfig;
    this.saveConfigurations(newConfigs);
    
    return updatedConfig;
  }

  /**
   * Delete a configuration
   */
  deleteConfiguration(id: string): boolean {
    const configs = this._configurations.value;
    const filteredConfigs = configs.filter(c => c.id !== id);
    
    if (filteredConfigs.length === configs.length) {
      return false; // Configuration not found
    }

    this.saveConfigurations(filteredConfigs);
    return true;
  }

  /**
   * Delete all configurations for a specific role
   */
  deleteConfigurationsByRole(role: ModelRole): number {
    const configs = this._configurations.value;
    const filteredConfigs = configs.filter(c => c.role !== role);
    const deletedCount = configs.length - filteredConfigs.length;
    
    if (deletedCount > 0) {
      this.saveConfigurations(filteredConfigs);
    }
    
    return deletedCount;
  }

  /**
   * Validate credentials for a provider
   */
  validateCredentials(provider: LLMProvider, credentials: ProviderCredentials): { valid: boolean; errors: string[] } {
    const providerInfo = PROVIDER_INFO[provider];
    const errors: string[] = [];

    if (!providerInfo) {
      errors.push('Invalid provider');
      return { valid: false, errors };
    }

    // Check required fields
    providerInfo.credentialFields.forEach(field => {
      if (field.required) {
        const value = credentials[field.key];
        if (!value || (typeof value === 'string' && value.trim() === '')) {
          errors.push(`${field.label} is required`);
        }
      }
    });

    // Validate URL fields
    providerInfo.credentialFields
      .filter(field => field.type === 'url' && credentials[field.key])
      .forEach(field => {
        const value = credentials[field.key];
        if (value && typeof value === 'string') {
          try {
            new URL(value);
          } catch {
            errors.push(`${field.label} must be a valid URL`);
          }
        }
      });

    return { valid: errors.length === 0, errors };
  }

  /**
   * Validate model configuration
   */
  validateModelConfig(config: Partial<LLMModelConfig>): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!config.role) {
      errors.push('Model role is required');
    }

    if (!config.provider) {
      errors.push('Provider is required');
    }

    if (!config.modelName || config.modelName.trim() === '') {
      errors.push('Model name is required');
    }

    if (!config.credentials) {
      errors.push('Credentials are required');
    } else if (config.provider) {
      const credValidation = this.validateCredentials(config.provider, config.credentials);
      errors.push(...credValidation.errors);
    }

    if (config.temperature !== undefined) {
      if (config.temperature < 0 || config.temperature > 2) {
        errors.push('Temperature must be between 0 and 2');
      }
    }

    if (config.maxTokens !== undefined) {
      if (config.maxTokens < 1) {
        errors.push('Max tokens must be at least 1');
      }
    }

    return { valid: errors.length === 0, errors };
  }

  /**
   * Export configurations to JSON
   */
  exportConfigurations(): void {
    const configs = this._configurations.value;
    const json = JSON.stringify(configs, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `llm_configurations_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Import configurations from JSON
   */
  async importConfigurations(file: File): Promise<{ success: boolean; imported: number; errors: string[] }> {
    return new Promise((resolve) => {
      const reader = new FileReader();
      
      reader.onload = () => {
        try {
          const configs = JSON.parse(reader.result as string);
          
          if (!Array.isArray(configs)) {
            resolve({ success: false, imported: 0, errors: ['Invalid file format: expected an array'] });
            return;
          }

          const errors: string[] = [];
          let imported = 0;

          configs.forEach((config, index) => {
            // Validate each configuration
            const validation = this.validateModelConfig(config);
            if (!validation.valid) {
              errors.push(`Config ${index + 1}: ${validation.errors.join(', ')}`);
            } else {
              try {
                this.addConfiguration(config);
                imported++;
              } catch (error) {
                errors.push(`Config ${index + 1}: Failed to import`);
              }
            }
          });

          resolve({ success: imported > 0, imported, errors });
        } catch (error) {
          resolve({ success: false, imported: 0, errors: ['Invalid JSON file'] });
        }
      };

      reader.onerror = () => {
        resolve({ success: false, imported: 0, errors: ['Failed to read file'] });
      };

      reader.readAsText(file);
    });
  }

  /**
   * Get provider information
   */
  getProviderInfo(provider: LLMProvider) {
    return PROVIDER_INFO[provider];
  }

  /**
   * Get all available providers
   */
  getAllProviders() {
    return Object.values(PROVIDER_INFO);
  }

  /**
   * Generate a unique ID for configurations
   */
  private generateId(): string {
    return `llm_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Clear all configurations (use with caution)
   */
  clearAllConfigurations(): void {
    this.saveConfigurations([]);
  }

  /**
   * Get configuration summary for a role
   */
  getRoleSummary(role: ModelRole): { count: number; providers: string[] } {
    const configs = this.getConfigurationsByRole(role);
    const providers = [...new Set(configs.map(c => c.provider))];
    return { count: configs.length, providers };
  }
}

// Made with Bob
