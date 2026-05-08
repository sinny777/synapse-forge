import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule,
  InputModule,
  NotificationModule,
  ToggleModule,
  NumberModule,
  SelectModule,
  AccordionModule,
  SliderModule,
  TabsModule,
  DropdownModule,
  TagModule,
} from 'carbon-components-angular';
import { ToggletipModule } from 'carbon-components-angular/toggletip';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { NeuralToolService } from '../../services/neural-tool.service';
import { ConfigService, FIELD_TOOLTIPS, ValidationResult } from '../../services/config.service';

import PlayFilled16 from '@carbon/icons/es/play--filled/16';
import Save16 from '@carbon/icons/es/save/16';
import Reset16 from '@carbon/icons/es/reset/16';
import ChevronDown16 from '@carbon/icons/es/chevron--down/16';
import DataBase16 from '@carbon/icons/es/data--base/16';
import Settings16 from '@carbon/icons/es/settings/16';
import InformationFilled16 from '@carbon/icons/es/information--filled/16';
import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import Warning16 from '@carbon/icons/es/warning/16';
import ViewAll16 from '@carbon/icons/es/view/16';

// Size 20 icons for section headers
import Settings20 from '@carbon/icons/es/settings/20';
import MachineLearningModel20 from '@carbon/icons/es/machine-learning-model/20';
import DataCategorical20 from '@carbon/icons/es/data--categorical/20';
import Connect20 from '@carbon/icons/es/connect/20';
import DocumentExport20 from '@carbon/icons/es/document--export/20';

/** Interfaces matching the backend config.py dataclasses */
interface LLMConfig {
  teacher_model: string;
  teacher_temperature: number;
  teacher_max_tokens: number;
  ollama_api_base: string;
  openai_api_key: string;
  anthropic_api_key: string;
  google_api_key: string;
  groq_api_key: string;
}

interface EmbeddingConfig {
  base_model_name: string;
  fine_tuned_model_dir: string;
  embedding_dim: number | null;
  device: string;
}

interface VectorStoreConfig {
  store_type: string;
  faiss_index_path: string;
  faiss_index_type: string;
  chromadb_path: string;
  chromadb_collection_name: string;
  top_k: number;
  similarity_threshold: number;
}

interface MCPConfig {
  servers: Record<string, any>;
  connection_timeout: number;
  tool_cache_path: string;
}

interface DataGenerationConfig {
  queries_per_tool: number;
  direct_query_ratio: number;
  implicit_query_ratio: number;
  multi_tool_query_ratio: number;
  num_hard_negatives: number;
  output_path: string;
  batch_size: number;
}

/** MCP Server entry for table */
interface MCPServerEntry {
  name: string;
  command: string;
  args: string;
  transport: string;
}

@Component({
  selector: 'app-generate',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    InputModule,
    NotificationModule,
    ToggleModule,
    NumberModule,
    SelectModule,
    AccordionModule,
    SliderModule,
    TabsModule,
    IconModule,
    DropdownModule,
    TagModule,
    ToggletipModule,
  ],
  templateUrl: './generate.component.html',
  styleUrls: ['./generate.component.scss'],
})
export class GenerateComponent implements OnInit {
  /** Section collapse states (false = collapsed by default) */
  sections: Record<string, boolean> = {
    llm: false,
    embedding: false,
    vectorStore: false,
    mcp: false,
    dataGeneration: false,
  };

  /** Default config snapshots for diff detection */
  private readonly DEFAULTS = {
    llm: {
      teacher_model: 'ollama/granite4.1:8b',
      teacher_temperature: 0.7,
      teacher_max_tokens: 2000,
      ollama_api_base: 'http://localhost:11434',
      openai_api_key: '',
      anthropic_api_key: '',
      google_api_key: '',
      groq_api_key: '',
    } as LLMConfig,
    embedding: {
      base_model_name: 'sentence-transformers/all-MiniLM-L6-v2',
      fine_tuned_model_dir: 'models/fine_tuned_tool_router',
      embedding_dim: null,
      device: 'cpu',
    } as EmbeddingConfig,
    vectorStore: {
      store_type: 'faiss',
      faiss_index_path: 'data/faiss_index.bin',
      faiss_index_type: 'IndexFlatIP',
      chromadb_path: 'data/chromadb',
      chromadb_collection_name: 'tool_embeddings',
      top_k: 3,
      similarity_threshold: 0.3,
    } as VectorStoreConfig,
    mcp: {
      servers: {},
      connection_timeout: 30,
      tool_cache_path: 'data/tool_cache.json',
    } as MCPConfig,
    dataGeneration: {
      queries_per_tool: 10,
      direct_query_ratio: 0.4,
      implicit_query_ratio: 0.4,
      multi_tool_query_ratio: 0.2,
      num_hard_negatives: 3,
      output_path: 'data/synthetic_queries.jsonl',
      batch_size: 5,
    } as DataGenerationConfig,
  };

  /** Live config */
  llmConfig: LLMConfig = { ...this.DEFAULTS.llm };
  embeddingConfig: EmbeddingConfig = { ...this.DEFAULTS.embedding };
  vectorStoreConfig: VectorStoreConfig = { ...this.DEFAULTS.vectorStore };
  mcpConfig: MCPConfig = { servers: {}, connection_timeout: 30, tool_cache_path: 'data/tool_cache.json' };
  dataGenConfig: DataGenerationConfig = { ...this.DEFAULTS.dataGeneration };

  /** MCP Servers as table rows (Recommendation #7) */
  mcpServers: MCPServerEntry[] = [];
  newServer: MCPServerEntry = { name: '', command: '', args: '', transport: 'stdio' };

  /** Validation results (Recommendation #6) */
  validationResults: Record<string, ValidationResult> = {};

  /** Tooltips reference */
  tooltips = FIELD_TOOLTIPS;

  /** Dropdown options */
  deviceOptions = [
    { content: 'CPU', value: 'cpu' },
    { content: 'CUDA (GPU)', value: 'cuda' },
    { content: 'MPS (Apple Silicon)', value: 'mps' },
  ];

  storeTypeOptions = [
    { content: 'FAISS', value: 'faiss' },
    { content: 'ChromaDB', value: 'chromadb' },
  ];

  faissIndexOptions = [
    { content: 'IndexFlatIP (Cosine Similarity)', value: 'IndexFlatIP' },
    { content: 'IndexFlatL2 (Euclidean)', value: 'IndexFlatL2' },
    { content: 'IndexIVFFlat', value: 'IndexIVFFlat' },
  ];

  predefinedMcpOptions = [
    { content: 'Select an MCP Server...', value: '' },
    { content: 'UHNW Private Banking Example', value: 'uhnwc_banking' },
    { content: 'Mediclaim Processing Example', value: 'mediclaim' },
    { content: 'Filesystem (Local)', value: 'filesystem' },
  ];
  selectedPredefinedMcp = '';

  isLoading = false;
  notification: any = null;
  
  progressStatus: any = null;
  statusInterval: any;

  syntheticData: any[] = [];
  isDataLoading = false;
  isDataSaving = false;

  constructor(
    private service: NeuralToolService,
    private iconService: IconService,
    public configService: ConfigService
  ) {
    this.iconService.registerAll([
      PlayFilled16, Save16, Reset16, ChevronDown16, DataBase16,
      Settings16, InformationFilled16, Add16, TrashCan16,
      Checkmark16, Warning16, ViewAll16,
      Settings20, MachineLearningModel20, DataCategorical20,
      Connect20, DocumentExport20,
    ]);
  }

  ngOnInit(): void {
    this.syncMCPtoTable();
    this.runValidation();
    this.loadSyntheticData();
  }

  ngOnDestroy(): void {
    if (this.statusInterval) clearInterval(this.statusInterval);
  }

  toggleSection(section: string): void {
    this.sections[section] = !this.sections[section];
  }

  // ─── Recommendation #4: Expand / Collapse All ──────────────────
  expandAll(): void {
    Object.keys(this.sections).forEach((k) => (this.sections[k] = true));
  }

  collapseAll(): void {
    Object.keys(this.sections).forEach((k) => (this.sections[k] = false));
  }

  allExpanded(): boolean {
    return Object.values(this.sections).every((v) => v);
  }

  // ─── Recommendation #5: Diff Detection ─────────────────────────
  getModifiedCount(sectionKey: string): number {
    const defaultsMap: Record<string, any> = {
      llm: this.DEFAULTS.llm,
      embedding: this.DEFAULTS.embedding,
      vectorStore: this.DEFAULTS.vectorStore,
      mcp: this.DEFAULTS.mcp,
      dataGeneration: this.DEFAULTS.dataGeneration,
    };
    const currentMap: Record<string, any> = {
      llm: this.llmConfig,
      embedding: this.embeddingConfig,
      vectorStore: this.vectorStoreConfig,
      mcp: this.mcpConfig,
      dataGeneration: this.dataGenConfig,
    };
    return this.configService.countModifiedFields(currentMap[sectionKey], defaultsMap[sectionKey]);
  }

  isFieldModified(sectionKey: string, fieldName: string): boolean {
    const defaultsMap: Record<string, any> = {
      llm: this.DEFAULTS.llm,
      embedding: this.DEFAULTS.embedding,
      vectorStore: this.DEFAULTS.vectorStore,
      mcp: this.DEFAULTS.mcp,
      dataGeneration: this.DEFAULTS.dataGeneration,
    };
    const currentMap: Record<string, any> = {
      llm: this.llmConfig,
      embedding: this.embeddingConfig,
      vectorStore: this.vectorStoreConfig,
      mcp: this.mcpConfig,
      dataGeneration: this.dataGenConfig,
    };
    return currentMap[sectionKey]?.[fieldName] !== defaultsMap[sectionKey]?.[fieldName];
  }

  // ─── Recommendation #6: Validation ─────────────────────────────
  runValidation(): void {
    this.validationResults = this.configService.validateGenerateConfig(
      this.llmConfig, this.embeddingConfig, this.vectorStoreConfig, this.mcpConfig, this.dataGenConfig
    );
  }

  getSectionValidation(sectionKey: string): ValidationResult {
    return this.validationResults[sectionKey] || { valid: true, errors: [] };
  }

  // ─── Recommendation #7: MCP Table ──────────────────────────────
  private syncMCPtoTable(): void {
    this.mcpServers = Object.entries(this.mcpConfig.servers).map(([name, cfg]) => ({
      name,
      command: cfg.command || '',
      args: Array.isArray(cfg.args) ? cfg.args.join(' ') : (cfg.args || ''),
      transport: cfg.transport || 'stdio',
    }));
  }

  private syncTableToMCP(): void {
    const servers: Record<string, any> = {};
    for (const srv of this.mcpServers) {
      if (srv.name.trim()) {
        servers[srv.name.trim()] = {
          command: srv.command,
          args: srv.args.split(/\s+/).filter(Boolean),
          transport: srv.transport,
        };
      }
    }
    this.mcpConfig.servers = servers;
    this.onConfigChange();
  }

  addServer(): void {
    if (!this.newServer.name.trim()) return;
    this.mcpServers.push({ ...this.newServer });
    this.newServer = { name: '', command: '', args: '', transport: 'stdio' };
    this.selectedPredefinedMcp = '';
    this.syncTableToMCP();
  }

  onPredefinedMcpSelect(): void {
    if (this.selectedPredefinedMcp === 'uhnwc_banking') {
      this.newServer = {
        name: 'uhnwc_banking',
        command: 'python',
        args: '../examples/langgraph_UHNW_banking/mock_fastmcp_server.py',
        transport: 'stdio'
      };
    } else if (this.selectedPredefinedMcp === 'mediclaim') {
      this.newServer = {
        name: 'mediclaim',
        command: 'python',
        args: '../examples/beeai_mediclaim_processing/mock_fastmcp_server.py',
        transport: 'stdio'
      };
    } else if (this.selectedPredefinedMcp === 'filesystem') {
      this.newServer = {
        name: 'filesystem',
        command: 'npx',
        args: '-y @modelcontextprotocol/server-filesystem /tmp',
        transport: 'stdio'
      };
    } else {
      this.newServer = { name: '', command: '', args: '', transport: 'stdio' };
    }
  }

  removeServer(index: number): void {
    this.mcpServers.splice(index, 1);
    this.syncTableToMCP();
  }

  onServerChange(): void {
    this.syncTableToMCP();
  }

  // ─── Common ─────────────────────────────────────────────────────
  onConfigChange(): void {
    this.configService.markUnsaved();
    this.runValidation();
    this.saveSnapshot();
  }

  private saveSnapshot(): void {
    this.configService.saveConfigSnapshot(this.buildPayload());
  }

  resetDefaults(): void {
    this.llmConfig = { ...this.DEFAULTS.llm };
    this.embeddingConfig = { ...this.DEFAULTS.embedding };
    this.vectorStoreConfig = { ...this.DEFAULTS.vectorStore };
    this.mcpConfig = { servers: {}, connection_timeout: 30, tool_cache_path: 'data/tool_cache.json' };
    this.dataGenConfig = { ...this.DEFAULTS.dataGeneration };
    this.syncMCPtoTable();
    this.runValidation();
    this.notification = { type: 'info', title: 'Reset', message: 'All configuration values have been reset to defaults.' };
  }

  getRatioSum(): string {
    const sum = this.dataGenConfig.direct_query_ratio + this.dataGenConfig.implicit_query_ratio + this.dataGenConfig.multi_tool_query_ratio;
    return sum.toFixed(2);
  }

  isRatioValid(): boolean {
    const sum = this.dataGenConfig.direct_query_ratio + this.dataGenConfig.implicit_query_ratio + this.dataGenConfig.multi_tool_query_ratio;
    return Math.abs(sum - 1.0) <= 0.01;
  }

  private buildPayload(): any {
    return {
      llm: { ...this.llmConfig },
      embedding: { ...this.embeddingConfig },
      vector_store: { ...this.vectorStoreConfig },
      mcp: { ...this.mcpConfig },
      data_generation: { ...this.dataGenConfig },
    };
  }

  onSubmit(): void {
    this.runValidation();
    const hasErrors = Object.values(this.validationResults).some((v) => !v.valid);
    if (hasErrors) {
      const allErrors = Object.values(this.validationResults).flatMap((v) => v.errors);
      this.notification = { type: 'error', title: 'Validation Error', message: allErrors.join(' ') };
      return;
    }

    this.isLoading = true;
    this.notification = null;
    const payload = this.buildPayload();

    this.startPolling();

    this.service.generate(payload).subscribe({
      next: (res) => {
        this.stopPolling();
        this.isLoading = false;
        this.configService.markSynced();
        this.notification = { type: 'success', title: 'Success', message: res.message || 'Synthetic data generation completed.' };
        this.loadSyntheticData();
      },
      error: (err) => {
        this.stopPolling();
        this.isLoading = false;
        this.configService.markError();
        this.notification = { type: 'error', title: 'Error', message: err.error?.detail || err.message || 'Generation failed.' };
      },
    });
  }

  startPolling() {
    this.progressStatus = { message: 'Starting generation...', progress: 0 };
    this.statusInterval = setInterval(() => {
      this.service.getStatus().subscribe(status => {
        if (status && status.phase === 'generate') {
          this.progressStatus = status;
        }
      });
    }, 1000);
  }

  stopPolling() {
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
  }

  loadSyntheticData() {
    this.isDataLoading = true;
    this.service.getSyntheticData().subscribe({
      next: (res) => {
        this.syntheticData = res.data || [];
        this.isDataLoading = false;
      },
      error: (err) => {
        console.error("Failed to load synthetic data", err);
        this.isDataLoading = false;
      }
    });
  }

  saveData() {
    this.isDataSaving = true;
    this.service.saveSyntheticData(this.syntheticData).subscribe({
      next: (res) => {
        this.isDataSaving = false;
        this.notification = { type: 'success', title: 'Data Saved', message: 'Synthetic data updated successfully.' };
      },
      error: (err) => {
        this.isDataSaving = false;
        this.notification = { type: 'error', title: 'Save Failed', message: 'Failed to save synthetic data updates.' };
      }
    });
  }
}
