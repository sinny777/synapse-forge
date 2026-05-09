import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';

// ─── Tooltip Definitions ──────────────────────────────────────────
// Centralised map of field-level help text drawn from config.py + README docs
export const FIELD_TOOLTIPS: Record<string, string> = {
  // LLM Config
  teacher_model: 'LiteLLM model identifier for synthetic data generation (Phase 1). E.g., ollama/granite4.1:8b, gpt-4o-mini, claude-3-haiku.',
  teacher_temperature: 'Controls randomness of synthetic query generation. Higher = more diverse queries (0.0–2.0).',
  teacher_max_tokens: 'Maximum tokens the teacher LLM may output per generation call.',
  ollama_api_base: 'Base URL for local Ollama server. Leave blank to use cloud LLM providers.',
  openai_api_key: 'Optional. Read from OPENAI_API_KEY env var if blank. Required when teacher_model starts with "gpt".',
  anthropic_api_key: 'Optional. Read from ANTHROPIC_API_KEY env var if blank. Required for Claude models.',
  google_api_key: 'Optional. Read from GOOGLE_API_KEY env var if blank. Required for Gemini models.',
  groq_api_key: 'Optional. Read from GROQ_API_KEY env var if blank. Required for Groq-hosted models.',

  // Embedding Config
  base_model_name: 'sentence-transformers model to fine-tune. Swap to paraphrase-MiniLM-L3-v2 for speed or all-mpnet-base-v2 for accuracy.',
  fine_tuned_model_dir: 'Directory where the fine-tuned embedding model weights are saved after training.',
  embedding_dim: 'Auto-detected from the base model. Override only for custom models.',
  device: 'Hardware for training & inference: CPU (universal), CUDA (NVIDIA GPU), MPS (Apple Silicon).',

  // Vector Store Config
  store_type: 'FAISS for high-speed CPU/GPU retrieval, ChromaDB for persistence with metadata filtering.',
  top_k: 'Number of tools to retrieve per query. Lower = faster (2), higher = more accurate (5).',
  similarity_threshold: 'Minimum cosine similarity score to consider a tool match (0.0–1.0).',
  faiss_index_path: 'File path to the serialised FAISS binary index.',
  faiss_index_type: 'IndexFlatIP = cosine similarity (recommended). IndexFlatL2 = Euclidean distance.',
  chromadb_path: 'Directory for ChromaDB persistent storage.',
  chromadb_collection_name: 'ChromaDB collection name for tool embeddings.',

  // MCP Config
  connection_timeout: 'Max seconds to wait when connecting to an MCP server before timing out.',
  tool_cache_path: 'JSON file storing cached MCP tool schemas (avoids re-fetching on each run).',
  mcp_servers: 'Define MCP servers that expose tools to the framework. Each server needs command, args, and transport.',

  // Data Generation Config
  queries_per_tool: 'Number of synthetic training queries generated per discovered MCP tool.',
  direct_query_ratio: 'Fraction of generated queries that directly name the tool\'s function (e.g., "send email").',
  implicit_query_ratio: 'Fraction of queries that describe the intent without naming the function (e.g., "I need to contact someone").',
  multi_tool_query_ratio: 'Fraction of queries requiring multiple tools working together.',
  num_hard_negatives: 'Number of semantically similar but incorrect tools included as hard negatives in contrastive training.',
  output_path: 'Path where generated synthetic query data (JSONL) is written.',
  batch_size_datagen: 'Number of tools to process in parallel during synthetic data generation.',

  // Training Config
  batch_size: 'Mini-batch size for contrastive training. Larger = more stable gradients but more memory.',
  num_epochs: 'Number of full passes through the training data. More epochs = better accuracy but risk of overfitting.',
  learning_rate: 'Step size for the AdamW optimizer. Default 2e-5 is safe; increase cautiously.',
  warmup_steps: 'Number of steps with linearly increasing learning rate before reaching the target LR.',
  loss_function: 'MultipleNegativesRankingLoss is recommended for contrastive learning with in-batch negatives.',
  eval_steps: 'Run evaluation every N training steps.',
  save_steps: 'Save a model checkpoint every N training steps.',
  training_data_path: 'Path to the JSONL file containing synthetic training queries from Phase 1.',
  logging_dir: 'Directory for TensorBoard training logs.',

  // Runtime Config
  enable_query_expansion: 'When ON, a fast LLM breaks user queries into logical sub-steps before retrieval (improves recall).',
  expansion_prompt_template: 'Prompt template for query expansion. Must contain {query} placeholder.',
  enable_fallback_tool: 'When ON, a search_available_tools fallback function is always available to the heavy LLM.',
  fallback_tool_name: 'Name of the dynamic fallback tool the LLM can call when initial retrieval misses.',
  max_tool_calls: 'Maximum number of tool invocations the LLM may make per user query.',
  tool_call_timeout: 'Timeout in seconds for individual MCP tool execution calls.',
  log_level: 'Verbosity of runtime logging: DEBUG, INFO, WARNING, ERROR.',
  log_file: 'File path for runtime log output.',

  // Runtime LLM Config
  expansion_model: 'Fast/cheap LLM for query expansion (e.g., gpt-4o-mini, ollama/granite4.1:8b).',
  expansion_temperature: 'Temperature for expansion LLM. Low (0.1–0.3) for consistent decomposition.',
  expansion_max_tokens: 'Max tokens for query expansion output.',
  heavy_model: 'Primary "brain" LLM for parameter extraction & tool execution (e.g., gpt-4o, claude-3.5-sonnet).',
  heavy_temperature: 'Temperature for heavy LLM. 0.0 for deterministic tool calling.',
  heavy_max_tokens: 'Max output tokens for the heavy LLM\'s tool-calling response.',
};

// ─── Profile Presets ──────────────────────────────────────────────
// Based on README § "Customization & Tuning" — speed, accuracy, cost
export interface ConfigProfile {
  id: string;
  name: string;
  description: string;
  icon: string;
  overrides: Record<string, any>;
}

export const CONFIG_PROFILES: ConfigProfile[] = [
  {
    id: 'default',
    name: 'Default',
    description: 'Balanced defaults for development and testing.',
    icon: '⚙️',
    overrides: {},
  },
  {
    id: 'speed',
    name: '🚀 Optimize for Speed',
    description: 'paraphrase-MiniLM-L3-v2, Top-K 2, expansion OFF, FAISS CPU.',
    icon: '🚀',
    overrides: {
      'embedding.base_model_name': 'sentence-transformers/paraphrase-MiniLM-L3-v2',
      'vectorStore.top_k': 2,
      'vectorStore.store_type': 'faiss',
      'runtime.enable_query_expansion': false,
    },
  },
  {
    id: 'accuracy',
    name: '🎯 Optimize for Accuracy',
    description: 'all-mpnet-base-v2, Top-K 5, more epochs, Hybrid Retrieval.',
    icon: '🎯',
    overrides: {
      'embedding.base_model_name': 'sentence-transformers/all-mpnet-base-v2',
      'vectorStore.top_k': 5,
      'training.num_epochs': 10,
      'runtime.enable_query_expansion': true,
    },
  },
  {
    id: 'cost',
    name: '💸 Optimize for Cost',
    description: 'Use gpt-4o-mini for expansion, local Ollama for heavy LLM.',
    icon: '💸',
    overrides: {
      'llm.expansion_model': 'gpt-4o-mini',
      'llm.heavy_model': 'ollama/granite4.1:8b',
      'llm.teacher_model': 'ollama/granite4.1:8b',
    },
  },
];

// ─── Validation ───────────────────────────────────────────────────
export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

@Injectable({
  providedIn: 'root',
})
export class ConfigService {
  private apiUrl = 'http://localhost:8000/api';

  /** Sync status: 'synced' | 'unsaved' | 'error' */
  private _syncStatus = new BehaviorSubject<'synced' | 'unsaved' | 'error'>('unsaved');
  syncStatus$ = this._syncStatus.asObservable();

  /** Currently active profile */
  private _activeProfile = new BehaviorSubject<string>('default');
  activeProfile$ = this._activeProfile.asObservable();

  /** Saved profiles in localStorage */
  private readonly PROFILE_STORAGE_KEY = 'ntr_saved_profiles';
  private readonly CONFIG_STORAGE_KEY = 'ntr_config_snapshot';

  private _customProfiles: ConfigProfile[] = [];

  constructor(private http: HttpClient) {
    this.loadCustomProfiles();
  }

  // ─── Profile Management ─────────────────────────────────────────
  private loadCustomProfiles(): void {
    try {
      const stored = localStorage.getItem(this.PROFILE_STORAGE_KEY);
      if (stored) {
        this._customProfiles = JSON.parse(stored);
      }
    } catch (e) {
      console.warn('Failed to load custom profiles', e);
    }
  }

  private saveCustomProfiles(): void {
    try {
      localStorage.setItem(this.PROFILE_STORAGE_KEY, JSON.stringify(this._customProfiles));
    } catch (e) {
      console.warn('Failed to save custom profiles', e);
    }
  }

  getProfiles(): ConfigProfile[] {
    return [...CONFIG_PROFILES, ...this._customProfiles];
  }

  getActiveProfileId(): string {
    return this._activeProfile.value;
  }

  setActiveProfile(profileId: string): void {
    this._activeProfile.next(profileId);
  }

  getProfileById(id: string): ConfigProfile | undefined {
    return this.getProfiles().find((p) => p.id === id);
  }

  saveAsNewProfile(name: string, description: string, overrides: Record<string, any>): ConfigProfile {
    const newProfile: ConfigProfile = {
      id: `custom_${Date.now()}`,
      name,
      description,
      icon: '💾',
      overrides,
    };
    this._customProfiles.push(newProfile);
    this.saveCustomProfiles();
    return newProfile;
  }

  deleteProfile(id: string): void {
    this._customProfiles = this._customProfiles.filter(p => p.id !== id);
    this.saveCustomProfiles();
    if (this._activeProfile.value === id) {
      this.setActiveProfile('default');
    }
  }

  // ─── Export / Import ────────────────────────────────────────────
  exportConfig(config: any): void {
    const json = JSON.stringify(config, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `toolrouter_config_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  importConfig(file: File): Promise<any> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const config = JSON.parse(reader.result as string);
          resolve(config);
        } catch (e) {
          reject(new Error('Invalid JSON file.'));
        }
      };
      reader.onerror = () => reject(new Error('Failed to read file.'));
      reader.readAsText(file);
    });
  }

  // ─── Diff Detection ─────────────────────────────────────────────
  /**
   * Returns the number of fields in `current` that differ from `defaults`.
   * Performs a shallow key-by-key comparison.
   */
  countModifiedFields(current: Record<string, any>, defaults: Record<string, any>): number {
    let count = 0;
    for (const key of Object.keys(defaults)) {
      const cVal = current[key];
      const dVal = defaults[key];
      if (typeof cVal === 'object' && cVal !== null) {
        // Skip nested objects (handled per section)
        continue;
      }
      if (cVal !== dVal) {
        count++;
      }
    }
    return count;
  }

  /**
   * Returns an array of field names that differ from defaults.
   */
  getModifiedFields(current: Record<string, any>, defaults: Record<string, any>): string[] {
    const modified: string[] = [];
    for (const key of Object.keys(defaults)) {
      const cVal = current[key];
      const dVal = defaults[key];
      if (typeof cVal === 'object' && cVal !== null) continue;
      if (cVal !== dVal) modified.push(key);
    }
    return modified;
  }

  // ─── Validation ─────────────────────────────────────────────────
  validateGenerateConfig(llm: any, embedding: any, vectorStore: any, mcp: any, dataGen: any): Record<string, ValidationResult> {
    const results: Record<string, ValidationResult> = {};

    // LLM section
    const llmErrors: string[] = [];
    if (!llm.teacher_model?.trim()) llmErrors.push('Teacher model is required.');
    if (llm.teacher_temperature < 0 || llm.teacher_temperature > 2) llmErrors.push('Temperature must be 0–2.');
    if (llm.teacher_max_tokens < 100) llmErrors.push('Max tokens must be ≥ 100.');
    if (llm.teacher_model?.includes('gpt') && !llm.openai_api_key) llmErrors.push('OpenAI API key needed for GPT models.');
    if (llm.teacher_model?.includes('claude') && !llm.anthropic_api_key) llmErrors.push('Anthropic API key needed for Claude models.');
    results['llm'] = { valid: llmErrors.length === 0, errors: llmErrors };

    // Embedding section
    const embErrors: string[] = [];
    if (!embedding.base_model_name?.trim()) embErrors.push('Base model name is required.');
    results['embedding'] = { valid: embErrors.length === 0, errors: embErrors };

    // Vector Store section
    const vsErrors: string[] = [];
    if (vectorStore.top_k < 1) vsErrors.push('Top-K must be ≥ 1.');
    if (vectorStore.similarity_threshold < 0 || vectorStore.similarity_threshold > 1) vsErrors.push('Similarity threshold must be 0–1.');
    results['vectorStore'] = { valid: vsErrors.length === 0, errors: vsErrors };

    // MCP section
    const mcpErrors: string[] = [];
    if (mcp.connection_timeout < 1) mcpErrors.push('Connection timeout must be ≥ 1s.');
    results['mcp'] = { valid: mcpErrors.length === 0, errors: mcpErrors };

    // Data Generation section
    const dgErrors: string[] = [];
    if (dataGen.queries_per_tool < 1) dgErrors.push('Queries per tool must be ≥ 1.');
    const ratioSum = dataGen.direct_query_ratio + dataGen.implicit_query_ratio + dataGen.multi_tool_query_ratio;
    if (Math.abs(ratioSum - 1.0) > 0.01) dgErrors.push(`Query ratios must sum to 1.0 (current: ${ratioSum.toFixed(2)}).`);
    results['dataGeneration'] = { valid: dgErrors.length === 0, errors: dgErrors };

    return results;
  }

  validateTrainConfig(training: any, embedding: any): Record<string, ValidationResult> {
    const results: Record<string, ValidationResult> = {};

    const tErrors: string[] = [];
    if (training.batch_size < 1) tErrors.push('Batch size must be ≥ 1.');
    if (training.num_epochs < 1) tErrors.push('Epochs must be ≥ 1.');
    if (training.learning_rate <= 0) tErrors.push('Learning rate must be > 0.');
    if (training.warmup_steps < 0) tErrors.push('Warmup steps must be ≥ 0.');
    results['training'] = { valid: tErrors.length === 0, errors: tErrors };

    const eErrors: string[] = [];
    if (!embedding.base_model_name?.trim()) eErrors.push('Base model name is required.');
    results['embedding'] = { valid: eErrors.length === 0, errors: eErrors };

    results['monitoring'] = { valid: true, errors: [] };

    return results;
  }

  validateRunConfig(runtime: any, llm: any): Record<string, ValidationResult> {
    const results: Record<string, ValidationResult> = {};

    const rtErrors: string[] = [];
    if (runtime.max_tool_calls < 1) rtErrors.push('Max tool calls must be ≥ 1.');
    if (runtime.tool_call_timeout < 1) rtErrors.push('Tool call timeout must be ≥ 1s.');
    if (runtime.enable_query_expansion && !runtime.expansion_prompt_template?.includes('{query}')) {
      rtErrors.push('Expansion prompt template must contain {query} placeholder.');
    }
    results['runtimeConfig'] = { valid: rtErrors.length === 0, errors: rtErrors };

    const llmErrors: string[] = [];
    if (!llm.expansion_model?.trim()) llmErrors.push('Expansion model is required.');
    if (!llm.heavy_model?.trim()) llmErrors.push('Heavy model is required.');
    if (llm.expansion_temperature < 0 || llm.expansion_temperature > 2) llmErrors.push('Expansion temperature must be 0–2.');
    if (llm.heavy_temperature < 0 || llm.heavy_temperature > 2) llmErrors.push('Heavy temperature must be 0–2.');
    results['llmConfig'] = { valid: llmErrors.length === 0, errors: llmErrors };

    return results;
  }

  // ─── Sync Status ────────────────────────────────────────────────
  markUnsaved(): void {
    this._syncStatus.next('unsaved');
  }

  markSynced(): void {
    this._syncStatus.next('synced');
  }

  markError(): void {
    this._syncStatus.next('error');
  }

  // ─── Tooltip Helper ─────────────────────────────────────────────
  getTooltip(field: string): string {
    return FIELD_TOOLTIPS[field] || '';
  }

  // ─── Persistence Helpers ────────────────────────────────────────
  saveConfigSnapshot(config: any): void {
    try {
      localStorage.setItem(this.CONFIG_STORAGE_KEY, JSON.stringify(config));
    } catch (e) {
      console.warn('Failed to save config snapshot to localStorage', e);
    }
  }

  loadConfigSnapshot(): any | null {
    try {
      const stored = localStorage.getItem(this.CONFIG_STORAGE_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch (e) {
      return null;
    }
  }
}
