import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { tap, catchError, map } from 'rxjs/operators';
import {
  LLMModelConfig,
  LLMModelConfigCreate,
  LLMModelConfigUpdate,
  LLMProvider,
  ProviderCredentials,
  PROVIDER_INFO
} from '../models/llm-config.model';

@Injectable({
  providedIn: 'root'
})
export class LLMConfigService {
  private readonly API_BASE = 'http://localhost:8000/api';

  private _configurations = new BehaviorSubject<LLMModelConfig[]>([]);
  public configurations$ = this._configurations.asObservable();

  constructor(private http: HttpClient) {}

  // ─── API Operations ────────────────────────────────────────────

  /**
   * Load configurations from the backend for a specific workspace
   */
  loadConfigurations(workspaceId: string): void {
    this.http
      .get<LLMModelConfig[]>(`${this.API_BASE}/workspaces/${workspaceId}/llm-configs`)
      .pipe(
        catchError((err) => {
          console.warn('Failed to load LLM configurations:', err);
          return of([]);
        })
      )
      .subscribe((configs) => {
        this._configurations.next(configs);
      });
  }

  /**
   * Get all configurations (current snapshot)
   */
  getConfigurations(): LLMModelConfig[] {
    return this._configurations.value;
  }

  /**
   * Get configuration by ID
   */
  getConfigurationById(id: string): LLMModelConfig | undefined {
    return this._configurations.value.find(config => config.id === id);
  }

  /**
   * Create a new configuration in a workspace
   */
  createConfiguration(
    workspaceId: string,
    config: LLMModelConfigCreate
  ): Observable<LLMModelConfig> {
    return this.http
      .post<LLMModelConfig>(
        `${this.API_BASE}/workspaces/${workspaceId}/llm-configs`,
        config
      )
      .pipe(
        tap((newConfig) => {
          const configs = [...this._configurations.value, newConfig];
          this._configurations.next(configs);
        })
      );
  }

  /**
   * Update an existing configuration
   */
  updateConfiguration(
    workspaceId: string,
    configId: string,
    updates: LLMModelConfigUpdate
  ): Observable<LLMModelConfig> {
    return this.http
      .put<LLMModelConfig>(
        `${this.API_BASE}/workspaces/${workspaceId}/llm-configs/${configId}`,
        updates
      )
      .pipe(
        tap((updatedConfig) => {
          const configs = this._configurations.value.map((c) =>
            c.id === configId ? updatedConfig : c
          );
          this._configurations.next(configs);
        })
      );
  }

  /**
   * Delete a configuration
   */
  deleteConfiguration(
    workspaceId: string,
    configId: string
  ): Observable<void> {
    return this.http
      .delete<void>(
        `${this.API_BASE}/workspaces/${workspaceId}/llm-configs/${configId}`
      )
      .pipe(
        tap(() => {
          const configs = this._configurations.value.filter(
            (c) => c.id !== configId
          );
          this._configurations.next(configs);
        })
      );
  }

  // ─── Validation ────────────────────────────────────────────────

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
    providerInfo.credentialFields.forEach((field: any) => {
      if (field.required) {
        const value = credentials[field.key];
        if (!value || (typeof value === 'string' && value.trim() === '')) {
          errors.push(`${field.label} is required`);
        }
      }
    });

    // Validate URL fields
    providerInfo.credentialFields
      .filter((field: any) => field.type === 'url' && credentials[field.key])
      .forEach((field: any) => {
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
  validateModelConfig(config: Partial<LLMModelConfigCreate>): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!config.name || config.name.trim() === '') {
      errors.push('Configuration name is required');
    }

    if (!config.provider) {
      errors.push('Provider is required');
    }

    if (!config.model_name || config.model_name.trim() === '') {
      errors.push('Model name is required');
    }

    if (config.credentials && config.provider) {
      const credValidation = this.validateCredentials(config.provider, config.credentials);
      errors.push(...credValidation.errors);
    }

    if (config.temperature !== undefined) {
      if (config.temperature < 0 || config.temperature > 2) {
        errors.push('Temperature must be between 0 and 2');
      }
    }

    if (config.max_tokens !== undefined) {
      if (config.max_tokens < 1) {
        errors.push('Max tokens must be at least 1');
      }
    }

    return { valid: errors.length === 0, errors };
  }

  // ─── Export / Import ───────────────────────────────────────────

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
   * Import configurations from JSON into a workspace
   */
  async importConfigurations(
    workspaceId: string,
    file: File
  ): Promise<{ success: boolean; imported: number; errors: string[] }> {
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

          const promises = configs.map((config: any, index: number) => {
            const validation = this.validateModelConfig(config);
            if (!validation.valid) {
              errors.push(`Config ${index + 1}: ${validation.errors.join(', ')}`);
              return Promise.resolve();
            }

            return this.createConfiguration(workspaceId, config)
              .toPromise()
              .then(() => { imported++; })
              .catch(() => { errors.push(`Config ${index + 1}: Failed to import`); });
          });

          Promise.all(promises).then(() => {
            resolve({ success: imported > 0, imported, errors });
          });
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

  // ─── Provider Helpers ──────────────────────────────────────────

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
   * Clear all local state
   */
  clearConfigurations(): void {
    this._configurations.next([]);
  }
}

// Made with Bob
