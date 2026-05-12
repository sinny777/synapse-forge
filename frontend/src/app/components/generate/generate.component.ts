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
  PaginationModule,
  PaginationModel,
  ContentSwitcherModule,
} from 'carbon-components-angular';
import { ToggletipModule } from 'carbon-components-angular/toggletip';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { NeuralToolService } from '../../services/neural-tool.service';
import { ConfigService, FIELD_TOOLTIPS, ValidationResult } from '../../services/config.service';
import { LLMConfigService } from '../../services/llm-config.service';
import { LLMModelConfig } from '../../models/llm-config.model';

import PlayFilled16 from '@carbon/icons/es/play--filled/16';
import Save16 from '@carbon/icons/es/save/16';
import Reset16 from '@carbon/icons/es/reset/16';
import ChevronDown16 from '@carbon/icons/es/chevron--down/16';
import Settings16 from '@carbon/icons/es/settings/16';
import InformationFilled16 from '@carbon/icons/es/information--filled/16';
import Add16 from '@carbon/icons/es/add/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import WarningAltFilled16 from '@carbon/icons/es/warning--filled/16';
import ViewAll16 from '@carbon/icons/es/view/16';
import List16 from '@carbon/icons/es/list/16';
import ListDropdown16 from '@carbon/icons/es/list--dropdown/16';

// Size 20 icons for section headers
import Settings20 from '@carbon/icons/es/settings/20';
import MachineLearningModel20 from '@carbon/icons/es/machine-learning-model/20';
import DataCategorical20 from '@carbon/icons/es/data--categorical/20';
import Connect20 from '@carbon/icons/es/connect/20';
import DocumentExport20 from '@carbon/icons/es/document--export/20';
import DataBase20 from '@carbon/icons/es/data--base/20';

// Size 16 icons for tabs
import MachineLearningModel16 from '@carbon/icons/es/machine-learning-model/16';
import DataCategorical16 from '@carbon/icons/es/data--categorical/16';
import Connect16 from '@carbon/icons/es/connect/16';
import DocumentExport16 from '@carbon/icons/es/document--export/16';
import DataBase16 from '@carbon/icons/es/data--base/16';

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
    PaginationModule,
    ContentSwitcherModule,
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
    syntheticData: true,
  };

  /** View mode: vertical tabs or accordion */
  viewMode = 'tabs';

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

  
  // Teacher model selection
  teacherConfigs: LLMModelConfig[] = [];
  selectedTeacherConfigId = '';
  syntheticData: any[] = [];
  cachedTools: any[] = [];
  
  // Dataset Management
  availableDatasets: any[] = [];
  selectedDataset: string = '';
  datasetDropdownItems: any[] = [
    { content: 'New Dataset', id: '', selected: true }
  ];
  datasetArchiveName: string = '';
  datasetArchiveVersion: string = '1.0';
  isArchivingDataset = false;
  currentDatasetPath: string = 'data/synthetic_queries.jsonl';
  
  // Pagination
  paginationModel = new PaginationModel();

  get paginatedData() {
    const pLen = this.paginationModel.pageLength || 20;
    const startIndex = (this.paginationModel.currentPage - 1) * pLen;
    return this.syntheticData.slice(startIndex, startIndex + pLen);
  }
  
  onSelectPage(event: any) {
    this.paginationModel.currentPage = event.page;
  }

  /** Handle view mode change from content switcher */
  onViewModeChange(event: any): void {
    this.viewMode = event.name || event.item.name;
    localStorage.setItem('generate_viewMode', this.viewMode);
  }

  isDataLoading = false;
  isDataSaving = false;

  constructor(
    private service: NeuralToolService,
    private iconService: IconService,
    public configService: ConfigService,
    private llmConfigService: LLMConfigService
  ) {
    this.iconService.registerAll([
      PlayFilled16, Save16, Reset16, ChevronDown16,
      Settings16, InformationFilled16, Add16, TrashCan16,
      Checkmark16, WarningAltFilled16, ViewAll16,
      List16, ListDropdown16,
      Settings20, MachineLearningModel20, DataCategorical20,
      Connect20, DocumentExport20, DataBase20,
      MachineLearningModel16, DataCategorical16, Connect16,
      DocumentExport16, DataBase16,
    ]);
  }

  ngOnInit(): void {
    const savedMode = localStorage.getItem('generate_viewMode');
    if (savedMode) this.viewMode = savedMode;
    this.paginationModel.pageLength = 20;
    this.paginationModel.currentPage = 1;
    this.syncMCPtoTable();
    this.runValidation();
    // Initialize dropdown with default item
    this.updateDatasetDropdownItems();
    this.loadDatasets();
    // Don't load synthetic data on init - only when user selects a dataset
    this.loadTeacherConfigs();
  }

  loadTeacherConfigs(): void {
    this.llmConfigService.configurations$.subscribe(configs => {
      this.teacherConfigs = configs.filter(c => c.role === 'teacher');
    });
  }

  onTeacherModelSelect(): void {
    if (this.selectedTeacherConfigId) {
      const config = this.llmConfigService.getConfigurationById(this.selectedTeacherConfigId);
      if (config) {
        let modelName = config.modelName;
        if (config.provider === 'ollama' && !modelName.startsWith('ollama/')) {
          modelName = `ollama/${modelName}`;
        }
        
        this.llmConfig.teacher_model = modelName;
        
        if (config.credentials) {
          if (config.credentials['api_key']) {
            if (config.provider === 'openai') {
              this.llmConfig.openai_api_key = config.credentials['api_key'] as string;
            } else if (config.provider === 'anthropic') {
              this.llmConfig.anthropic_api_key = config.credentials['api_key'] as string;
            } else if (config.provider === 'google') {
              this.llmConfig.google_api_key = config.credentials['api_key'] as string;
            } else if (config.provider === 'groq') {
              this.llmConfig.groq_api_key = config.credentials['api_key'] as string;
            }
          }
          if (config.credentials['api_base'] && config.provider === 'ollama') {
            this.llmConfig.ollama_api_base = config.credentials['api_base'] as string;
          }
        }
        
        if (config.temperature !== undefined) {
          this.llmConfig.teacher_temperature = config.temperature;
        }
        if (config.maxTokens !== undefined) {
          this.llmConfig.teacher_max_tokens = config.maxTokens;
        }
        
        this.onConfigChange();
      }
    }
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
    // Set output path based on dataset name and version
    if (this.datasetArchiveName && this.datasetArchiveVersion) {
      this.dataGenConfig.output_path = `data/datasets/${this.datasetArchiveName}_v${this.datasetArchiveVersion}.jsonl`;
    } else {
      this.dataGenConfig.output_path = 'data/synthetic_queries.jsonl';
    }
    
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
        
        // Auto-archive the newly generated dataset if name and version are provided
        if (this.datasetArchiveName && this.datasetArchiveVersion) {
          this.archiveDataset();
        }
        
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
    
    // Fetch tools first for the dropdown
    this.service.getCachedTools().subscribe({
      next: (toolsRes) => {
        this.cachedTools = toolsRes.tools || [];
        
        // Then fetch synthetic data
        this.service.getSyntheticData().subscribe({
          next: (res) => {
            this.syntheticData = res.data || [];
            this.isDataLoading = false;
            this.paginationModel.totalDataLength = this.syntheticData.length;
            this.paginationModel.currentPage = 1; // Reset to first page
          },
          error: (err) => {
            console.error("Failed to load synthetic data", err);
            this.isDataLoading = false;
          }
        });
      },
      error: (err) => {
        console.error("Failed to load tools cache", err);
        this.isDataLoading = false;
      }
    });
  }

  loadDatasets(): void {
    this.service.getDatasets().subscribe({
      next: (res) => {
        if (res.status === 'success') {
          this.availableDatasets = res.datasets || [];
          // Force update dropdown items after a brief delay to ensure Angular change detection
          setTimeout(() => {
            this.updateDatasetDropdownItems();
          }, 0);
        }
      },
      error: (err) => {
        console.error('Error loading datasets', err);
      }
    });
  }

  updateDatasetDropdownItems(): void {
    this.datasetDropdownItems = [
      { content: 'New Dataset', id: '', selected: !this.selectedDataset },
      ...this.availableDatasets.map(ds => ({
        content: `${ds.name} (v${ds.version})`,
        id: ds.name,
        selected: ds.name === this.selectedDataset
      }))
    ];
  }

  onDatasetSelectFromDropdown(event: any): void {
    const datasetId = event?.item?.id ?? event?.id ?? event;
    this.selectedDataset = datasetId;
    if (datasetId) {
      this.onDatasetSelect();
    } else {
      // New dataset selected - clear synthetic data
      this.createNewDataset();
    }
    this.updateDatasetDropdownItems();
  }

  onDatasetSelect(): void {
    if (this.selectedDataset) {
      // Find the dataset object to get its path
      const dataset = this.availableDatasets.find(ds => ds.name === this.selectedDataset);
      if (!dataset) {
        this.notification = { type: 'error', title: 'Error', message: 'Dataset not found.' };
        return;
      }
      
      this.isDataLoading = true;
      this.service.loadDataset(dataset.path).subscribe({
        next: (res) => {
          this.syntheticData = res.data || [];
          this.isDataLoading = false;
          this.paginationModel.totalDataLength = this.syntheticData.length;
          this.paginationModel.currentPage = 1;
          this.currentDatasetPath = dataset.path;
          this.datasetArchiveName = dataset.name;
          this.datasetArchiveVersion = dataset.version;
          this.notification = { type: 'success', title: 'Dataset Loaded', message: `Loaded dataset: ${dataset.name} (v${dataset.version})` };
        },
        error: (err) => {
          this.isDataLoading = false;
          this.notification = { type: 'error', title: 'Load Failed', message: 'Failed to load selected dataset.' };
        }
      });
    }
  }

  archiveDataset(): void {
    if (!this.datasetArchiveName || !this.datasetArchiveVersion) {
      this.notification = { type: 'error', title: 'Validation Error', message: 'Dataset name and version are required for archiving.' };
      return;
    }
    
    this.isArchivingDataset = true;
    const sourcePath = this.dataGenConfig.output_path || this.currentDatasetPath;
    this.service.archiveDataset(this.datasetArchiveName, this.datasetArchiveVersion, sourcePath).subscribe({
      next: (res) => {
        this.isArchivingDataset = false;
        this.notification = { type: 'success', title: 'Dataset Archived', message: res.message };
        
        // Set the newly archived dataset as selected
        const newDatasetName = this.datasetArchiveName;
        this.datasetArchiveName = '';
        this.datasetArchiveVersion = '1.0';
        
        // Reload datasets and select the new one
        this.loadDatasets();
        setTimeout(() => {
          this.selectedDataset = newDatasetName;
          this.updateDatasetDropdownItems();
          this.onDatasetSelect();
        }, 500);
      },
      error: (err) => {
        this.isArchivingDataset = false;
        this.notification = { type: 'error', title: 'Archive Failed', message: err.error?.detail || err.message };
      }
    });
  }

  deleteDataset(datasetName: string): void {
    if (confirm(`Are you sure you want to delete dataset ${datasetName}?`)) {
      this.service.deleteDataset(datasetName).subscribe({
        next: (res) => {
          this.notification = { type: 'success', title: 'Dataset Deleted', message: res.message };
          this.loadDatasets();
          if (this.selectedDataset === datasetName) {
            this.selectedDataset = '';
            this.loadSyntheticData();
          }
        },
        error: (err) => {
          this.notification = { type: 'error', title: 'Deletion Failed', message: err.error?.detail || err.message };
        }
      });
    }
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

  createNewDataset(): void {
    // Reset to default configuration for new dataset generation
    this.selectedDataset = '';
    this.datasetArchiveName = '';
    this.datasetArchiveVersion = '1.0';
    this.currentDatasetPath = 'data/synthetic_queries.jsonl';
    this.syntheticData = [];
    this.updateDatasetDropdownItems();
    this.notification = {
      type: 'info',
      title: 'New Dataset',
      message: 'Configure settings and click "Start Generation" to create a new synthetic dataset.'
    };
  }
}
