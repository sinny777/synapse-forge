import { Component, OnInit, NgZone } from '@angular/core';
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
  TabsModule,
  DropdownModule,
  TagModule,
  ContentSwitcherModule,
} from 'carbon-components-angular';
import { TagType } from 'carbon-components-angular/tag';
import { ToggletipModule } from 'carbon-components-angular/toggletip';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { NeuralToolService } from '../../services/neural-tool.service';
import { ConfigService, FIELD_TOOLTIPS, ValidationResult } from '../../services/config.service';
import { LLMConfigService } from '../../services/llm-config.service';
import { LLMModelConfig } from '../../models/llm-config.model';

import PlayFilled16 from '@carbon/icons/es/play--filled/16';
import Reset16 from '@carbon/icons/es/reset/16';
import ChevronDown16 from '@carbon/icons/es/chevron--down/16';
import InformationFilled16 from '@carbon/icons/es/information--filled/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Download16 from '@carbon/icons/es/download/16';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import CheckmarkFilled16 from '@carbon/icons/es/checkmark--filled/16';
import CheckmarkFilled20 from '@carbon/icons/es/checkmark--filled/20';
import WarningAltFilled16 from '@carbon/icons/es/warning--filled/16';
import ViewAll16 from '@carbon/icons/es/view/16';
import List16 from '@carbon/icons/es/list/16';
import ListDropdown16 from '@carbon/icons/es/list--dropdown/16';
import User16 from '@carbon/icons/es/user/16';

// Size 20 icons for section headers
import Rocket20 from '@carbon/icons/es/rocket/20';
import Settings20 from '@carbon/icons/es/settings/20';
import ChartLine20 from '@carbon/icons/es/chart--line/20';
import Keyboard20 from '@carbon/icons/es/keyboard/20';

// Size 16 icons for tabs
import Rocket16 from '@carbon/icons/es/rocket/16';
import Settings16 from '@carbon/icons/es/settings/16';
import ChartLine16 from '@carbon/icons/es/chart--line/16';
import Keyboard16 from '@carbon/icons/es/keyboard/16';

// Agent Mode icons
import Bot16 from '@carbon/icons/es/bot/16';
import Bot20 from '@carbon/icons/es/bot/20';
import Network_316 from '@carbon/icons/es/network--3/16';
import Network_320 from '@carbon/icons/es/network--3/20';
import DataVis_416 from '@carbon/icons/es/data-vis--4/16';
import Time16 from '@carbon/icons/es/time/16';
import Collaborate16 from '@carbon/icons/es/collaborate/16';
import Idea16 from '@carbon/icons/es/idea/16';
import Chat16 from '@carbon/icons/es/chat/16';

/** Interfaces matching backend config.py RuntimeConfig + LLMConfig */
interface RuntimeConfig {
  enable_query_expansion: boolean;
  expansion_prompt_template: string;
  enable_fallback_tool: boolean;
  fallback_tool_name: string;
  max_tool_calls: number;
  tool_call_timeout: number;
  log_level: string;
  log_file: string;
}

interface RuntimeLLMConfig {
  expansion_model: string;
  expansion_temperature: number;
  expansion_max_tokens: number;
  heavy_model: string;
  heavy_temperature: number;
  heavy_max_tokens: number;
}

/** Agent-related interfaces */
interface AgentScenario {
  id: string;
  name: string;
  description: string;
  framework: string;
  agents: AgentInfo[];
  example_query: string;
  estimated_duration: number;
  total_tools: number;
  use_case: string;
  benefits: string[];
}

interface AgentInfo {
  name: string;
  role: string;
  description: string;
  tools_count: number;
}

interface AgentStep {
  agentName: string;
  agentRole: string;
  framework: string;
  toolsRetrieved: Array<{name: string, score: number, args?: any}>;
  reasoning: string;
  toolExecutions: Array<{tool: string, args: any, result: any, time: number, success: boolean, expanded?: boolean}>;
  response: string;
  timestamp: number;
  startTime?: number;
  endTime?: number;
  executionTime?: number;
  expanded: boolean;
}

interface AgentExecutionData {
  scenarioId?: string;
  scenarioName?: string;
  userQuery?: string;
  executionMode?: string;
  finalResponse?: string;
  steps: AgentStep[];
  metrics: {
    execution_time?: number;
    agents_executed?: number;
    tools_retrieved?: number;
    tools_executed?: number;
    context_reduction?: number;
  };
  isExecuting: boolean;
  startTime?: number | null;
  endTime?: number | null;
}

@Component({
  selector: 'app-run',
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
    TabsModule,
    IconModule,
    DropdownModule,
    TagModule,
    ContentSwitcherModule,
    ToggletipModule,
  ],
  templateUrl: './run.component.html',
  styleUrls: ['./run.component.scss'],
})
export class RunComponent implements OnInit {
  /** Section collapse states */
  sections: Record<string, boolean> = {
    runtimeConfig: false,
    llmConfig: false,
  };

  /** View mode: vertical tabs or accordion */
  viewMode = 'tabs';

  /** Handle view mode change from content switcher */
  onViewModeChange(event: any): void {
    this.viewMode = event.name || event.item.name;
    localStorage.setItem('run_viewMode', this.viewMode);
  }

  /** Default snapshots for diff */
  private readonly DEFAULTS = {
    runtimeConfig: {
      enable_query_expansion: true,
      expansion_prompt_template: `Given the user query, break it down into logical steps or sub-tasks that would be needed to accomplish it.\nBe specific and actionable. List 2-5 steps.\n\nUser Query: {query}\n\nLogical Steps:`,
      enable_fallback_tool: true,
      fallback_tool_name: 'search_available_tools',
      max_tool_calls: 10,
      tool_call_timeout: 30,
      log_level: 'INFO',
      log_file: 'logs/runtime.log',
    } as RuntimeConfig,
    llmConfig: {
      expansion_model: 'ollama/granite4.1:8b',
      expansion_temperature: 0.3,
      expansion_max_tokens: 500,
      heavy_model: 'ollama/granite4.1:8b',
      heavy_temperature: 0.0,
      heavy_max_tokens: 4000,
    } as RuntimeLLMConfig,
  };

  /** Live config */
  runtimeConfig: RuntimeConfig = { ...this.DEFAULTS.runtimeConfig };
  runtimeLLMConfig: RuntimeLLMConfig = { ...this.DEFAULTS.llmConfig };

  /** Validation */
  validationResults: Record<string, ValidationResult> = {};

  /** Tooltips */
  tooltips = FIELD_TOOLTIPS;

  /** Dropdown options */
  logLevelOptions = [
    { content: 'DEBUG', value: 'DEBUG' },
    { content: 'INFO', value: 'INFO' },
    { content: 'WARNING', value: 'WARNING' },
    { content: 'ERROR', value: 'ERROR' },
  ];

  /** Query console state */
  queryInput = '';
  isLoading = false;
  resultData: any = null;
  notification: any = null;
  
  /** Trace Expand States */
  traceExpanded: Record<string, boolean> = {
    expansion: false,
    routing: false,
    reasoning: false,
    tools: false
  };

  /** Models */
  availableModels: any[] = [];
  selectedModel: string = '';

  /** LLM Config Integration */
  expansionConfigs: LLMModelConfig[] = [];
  heavyConfigs: LLMModelConfig[] = [];
  selectedExpansionConfigId = '';
  selectedHeavyConfigId = '';

  /** Agent Mode Properties */
  agentModeEnabled = true;
  showAgentMode = false;
  agentScenarios: AgentScenario[] = [];
  selectedScenarioId: string = '';
  agentExecutionData: AgentExecutionData = {
    isExecuting: false,
    startTime: null,
    endTime: null,
    steps: [],
    metrics: {
      execution_time: 0,
      agents_executed: 0,
      tools_retrieved: 0,
      tools_executed: 0,
      context_reduction: 0
    }
  };
  currentAgentStep: AgentStep | null = null;

  constructor(
    private service: NeuralToolService,
    private iconService: IconService,
    public configService: ConfigService,
    private ngZone: NgZone,
    private llmConfigService: LLMConfigService
  ) {
    this.iconService.registerAll([
      PlayFilled16, Reset16, ChevronDown16, InformationFilled16,
      TrashCan16, Download16, Checkmark16, CheckmarkFilled16, CheckmarkFilled20,
      WarningAltFilled16, ViewAll16, List16, ListDropdown16, User16,
      Rocket20, Settings20, ChartLine20, Keyboard20,
      Rocket16, Settings16, ChartLine16, Keyboard16,
      Bot16, Bot20, Network_316, Network_320, DataVis_416, Time16, Collaborate16,
      Idea16, Chat16,
    ]);
  }

  ngOnInit(): void {
    const savedMode = localStorage.getItem('run_viewMode');
    if (savedMode) this.viewMode = savedMode;
    this.runValidation();
    this.loadModels();
    this.loadLLMConfigs();
    this.loadAgentScenarios();
  }

  loadLLMConfigs(): void {
    this.llmConfigService.configurations$.subscribe(configs => {
      this.expansionConfigs = configs.filter(c => c.role === 'expansion');
      this.heavyConfigs = configs.filter(c => c.role === 'heavy');
    });
  }

  onExpansionModelSelect(): void {
    if (this.selectedExpansionConfigId) {
      const config = this.expansionConfigs.find(c => c.id === this.selectedExpansionConfigId);
      if (config) {
        this.runtimeLLMConfig.expansion_model = config.modelName;
        this.runValidation();
      }
    }
  }

  onHeavyModelSelect(): void {
    if (this.selectedHeavyConfigId) {
      const config = this.heavyConfigs.find(c => c.id === this.selectedHeavyConfigId);
      if (config) {
        this.runtimeLLMConfig.heavy_model = config.modelName;
        this.runValidation();
      }
    }
  }

  loadModels(): void {
    this.service.getModels().subscribe({
      next: (res) => {
        if (res.status === 'success') {
          this.availableModels = res.models;
        }
      },
      error: (err) => {
        console.error('Error loading models', err);
      }
    });
  }

  toggleSection(section: string): void {
    this.sections[section] = !this.sections[section];
  }

  expandAll(): void {
    Object.keys(this.sections).forEach((k) => (this.sections[k] = true));
  }

  collapseAll(): void {
    Object.keys(this.sections).forEach((k) => (this.sections[k] = false));
  }

  allExpanded(): boolean {
    return Object.values(this.sections).every((v) => v);
  }

  getModifiedCount(sectionKey: string): number {
    const defaultsMap: Record<string, any> = { runtimeConfig: this.DEFAULTS.runtimeConfig, llmConfig: this.DEFAULTS.llmConfig };
    const currentMap: Record<string, any> = { runtimeConfig: this.runtimeConfig, llmConfig: this.runtimeLLMConfig };
    return this.configService.countModifiedFields(currentMap[sectionKey] || {}, defaultsMap[sectionKey] || {});
  }

  isFieldModified(sectionKey: string, fieldName: string): boolean {
    const defaultsMap: Record<string, any> = { runtimeConfig: this.DEFAULTS.runtimeConfig, llmConfig: this.DEFAULTS.llmConfig };
    const currentMap: Record<string, any> = { runtimeConfig: this.runtimeConfig, llmConfig: this.runtimeLLMConfig };
    return currentMap[sectionKey]?.[fieldName] !== defaultsMap[sectionKey]?.[fieldName];
  }

  runValidation(): void {
    this.validationResults = this.configService.validateRunConfig(this.runtimeConfig, this.runtimeLLMConfig);
  }

  getSectionValidation(sectionKey: string): ValidationResult {
    return this.validationResults[sectionKey] || { valid: true, errors: [] };
  }

  onConfigChange(): void {
    this.configService.markUnsaved();
    this.runValidation();
  }

  resetDefaults(): void {
    this.runtimeConfig = { ...this.DEFAULTS.runtimeConfig };
    this.runtimeLLMConfig = { ...this.DEFAULTS.llmConfig };
    this.runValidation();
    this.notification = { type: 'info', title: 'Reset', message: 'All runtime configuration values have been reset to defaults.' };
  }

  clearQuery(): void {
    this.queryInput = '';
    this.resultData = null;
    this.resetTraceExpanded();
  }

  resetTraceExpanded(): void {
    this.traceExpanded = {
      expansion: false,
      routing: false,
      reasoning: false,
      tools: false
    };
  }

  toggleTrace(phase: string): void {
    this.traceExpanded[phase] = !this.traceExpanded[phase];
  }

  private buildPayload(): any {
    return {
      query: this.queryInput,
      model_path: this.selectedModel || null,
      runtime: { ...this.runtimeConfig },
      llm: { ...this.runtimeLLMConfig },
    };
  }

  async onSubmit(): Promise<void> {
    if (!this.queryInput.trim()) return;

    this.runValidation();
    const hasErrors = Object.values(this.validationResults).some((v) => !v.valid);
    if (hasErrors) {
      const allErrors = Object.values(this.validationResults).flatMap((v) => v.errors);
      this.notification = { type: 'error', title: 'Validation Error', message: allErrors.join(' ') };
      return;
    }

    this.isLoading = true;
    this.notification = null;
    this.resultData = null;
    this.resetTraceExpanded();
    const payload = this.buildPayload();

    try {
      this.resultData = { timings: {}, tool_results: [] };
      await this.service.runStream(payload, (chunk) => {
        this.ngZone.run(() => {
          if (chunk.event === 'start') {
            this.resultData.query = chunk.data.query;
            this.resultData.isExpanding = true;
            this.traceExpanded['expansion'] = true; // Auto-expand
          } else if (chunk.event === 'expansion_stream') {
            this.resultData.expanded_query = (this.resultData.expanded_query || '') + chunk.data.chunk;
            this.traceExpanded['expansion'] = true;
          } else if (chunk.event === 'expansion') {
            this.resultData.expanded_query = chunk.data.expanded_query;
            this.resultData.timings.expansion_time = chunk.data.time;
            this.resultData.isExpanding = false;
          } else if (chunk.event === 'routing') {
            this.resultData.retrieved_tools = chunk.data.retrieved_tools;
            this.resultData.timings.routing_time = chunk.data.time;
            this.resultData.isReasoning = true;
            this.traceExpanded['routing'] = true; // Auto-expand
          } else if (chunk.event === 'reasoning_stream') {
            this.resultData.raw_content = (this.resultData.raw_content || '') + chunk.data.chunk;
            this.traceExpanded['reasoning'] = true; // Auto-expand
          } else if (chunk.event === 'reasoning') {
            this.resultData.llm_reasoning = chunk.data.llm_reasoning;
            this.resultData.raw_content = chunk.data.raw_content;
            this.resultData.timings.llm_time = chunk.data.time;
            this.resultData.isReasoning = false;
          } else if (chunk.event === 'tool_execution') {
            const toolRes = { ...chunk.data, expanded: true }; // Auto-expand tool output
            this.resultData.tool_results.push(toolRes);
          } else if (chunk.event === 'complete') {
            this.resultData.timings = chunk.data.timings;
          }
        });
      });
      
      this.ngZone.run(() => {
        this.isLoading = false;
        this.configService.markSynced();
        this.notification = { type: 'success', title: 'Query Processed', message: 'Tool routing completed successfully.' };
      });
    } catch (err: any) {
      this.ngZone.run(() => {
        this.isLoading = false;
        this.configService.markError();
        this.notification = { type: 'error', title: 'Execution Failed', message: err.message || 'Query execution failed.' };
      });
    }
  }

  // ============================================================================
  // Agent Mode Methods
  // ============================================================================

  /**
   * Load available agent scenarios
   */
  loadAgentScenarios(): void {
    this.service.getAgentScenarios().subscribe({
      next: (response) => {
        if (response.status === 'success') {
          this.agentScenarios = response.scenarios;
        }
      },
      error: (err) => {
        console.error('Error loading agent scenarios:', err);
        this.notification = {
          type: 'error',
          title: 'Failed to Load Scenarios',
          message: 'Could not load agent scenarios. Please try again.'
        };
      }
    });
  }

  /**
   * Execute selected agent scenario
   */
  async executeAgentScenario(): Promise<void> {
    if (!this.selectedScenarioId) {
      this.notification = {
        type: 'warning',
        title: 'No Scenario Selected',
        message: 'Please select an agent scenario to execute.'
      };
      return;
    }

    // Validate configuration
    this.runValidation();
    const hasErrors = Object.values(this.validationResults).some((v) => !v.valid);
    if (hasErrors) {
      const allErrors = Object.values(this.validationResults).flatMap((v) => v.errors);
      this.notification = {
        type: 'error',
        title: 'Configuration Error',
        message: allErrors.join(' ')
      };
      return;
    }

    // Initialize execution data
    const scenario = this.agentScenarios.find(s => s.id === this.selectedScenarioId);
    if (!scenario) return;

    this.agentExecutionData = {
      scenarioId: this.selectedScenarioId,
      scenarioName: scenario.name,
      userQuery: scenario.example_query,
      finalResponse: '',
      steps: [],
      metrics: {
        execution_time: 0,
        agents_executed: 0,
        tools_retrieved: 0,
        tools_executed: 0,
        context_reduction: 0
      },
      isExecuting: true,
      startTime: Date.now(),
      endTime: null
    };

    this.currentAgentStep = null;
    this.notification = null;

    try {
      await this.service.executeAgentScenario(
        this.selectedScenarioId,
        this.runtimeLLMConfig,
        this.runtimeConfig,
        (event) => {
          this.ngZone.run(() => {
            this.handleAgentEvent(event);
          });
        }
      );

      this.ngZone.run(() => {
        if (this.agentExecutionData) {
          this.agentExecutionData.isExecuting = false;
        }
        this.notification = {
          type: 'success',
          title: 'Scenario Complete',
          message: `${scenario.name} executed successfully!`
        };
      });
    } catch (err: any) {
      this.ngZone.run(() => {
        if (this.agentExecutionData) {
          this.agentExecutionData.isExecuting = false;
        }
        this.notification = {
          type: 'error',
          title: 'Execution Failed',
          message: err.message || 'Agent scenario execution failed.'
        };
      });
    }
  }

  /**
   * Handle agent execution events
   */
  handleAgentEvent(event: any): void {
    if (!this.agentExecutionData) {
      return;
    }

    switch (event.type) {
      case 'scenario_start':
        // Scenario started - capture user query and execution mode
        if (event.data.scenario && this.agentExecutionData) {
          this.agentExecutionData.userQuery = event.data.scenario.example_query;
          this.agentExecutionData.executionMode = event.data.execution_mode || 'mock';
        }
        break;

      case 'agent_activated':
        // New agent activated - create new step
        this.currentAgentStep = {
          agentName: event.data.agent_name,
          agentRole: event.data.agent_role,
          framework: event.data.framework,
          toolsRetrieved: [],
          reasoning: '',
          toolExecutions: [],
          response: '',
          timestamp: event.timestamp,
          startTime: Date.now(),
          expanded: true // Auto-expand current step
        };
        if (!this.agentExecutionData.steps) {
          this.agentExecutionData.steps = [];
        }
        this.agentExecutionData.steps.push(this.currentAgentStep);
        break;

      case 'supervisor_routing':
        // LangGraph supervisor routing decision
        if (this.currentAgentStep) {
          this.currentAgentStep.reasoning = `Supervisor routed from ${event.data.from_agent} to ${event.data.to_agent}: ${event.data.reasoning}`;
        }
        break;

      case 'tool_retrieval':
        // Tools retrieved by router
        if (this.currentAgentStep) {
          this.currentAgentStep.toolsRetrieved = event.data.tools || [];
        }
        // Update metrics
        if (this.agentExecutionData.metrics) {
          this.agentExecutionData.metrics.tools_retrieved = (this.agentExecutionData.metrics.tools_retrieved || 0) + (event.data.tools?.length || 0);
        }
        break;

      case 'tool_execution':
        // Tool executed
        if (this.currentAgentStep) {
          this.currentAgentStep.toolExecutions.push({
            tool: event.data.tool_name,
            args: event.data.tool_args,
            result: event.data.result || 'Success',
            time: event.data.execution_time,
            success: event.data.success,
            expanded: false // Start collapsed
          });
        }
        // Update metrics
        if (this.agentExecutionData.metrics) {
          this.agentExecutionData.metrics.tools_executed = (this.agentExecutionData.metrics.tools_executed || 0) + 1;
        }
        break;

      case 'agent_reasoning':
        // Agent reasoning/thought process
        if (this.currentAgentStep) {
          this.currentAgentStep.reasoning = event.data.reasoning;
        }
        break;

      case 'agent_response':
        // Agent final response
        if (this.currentAgentStep) {
          this.currentAgentStep.response = event.data.response;
          this.currentAgentStep.endTime = Date.now();
          // Calculate execution time for this step
          if (this.currentAgentStep.startTime) {
            this.currentAgentStep.executionTime = (this.currentAgentStep.endTime - this.currentAgentStep.startTime) / 1000;
          }
          // Keep agent expanded to show response
          // this.currentAgentStep.expanded = false; // Removed - keep expanded to show details
          // Store as final response (will be overwritten by each agent, keeping the last one)
          if (this.agentExecutionData) {
            this.agentExecutionData.finalResponse = event.data.response;
          }
        }
        // Update metrics
        if (this.agentExecutionData.metrics) {
          this.agentExecutionData.metrics.agents_executed = (this.agentExecutionData.metrics.agents_executed || 0) + 1;
        }
        break;

      case 'scenario_complete':
        // Scenario completed - merge metrics (keep accumulated values, only update execution_time and context_reduction from backend)
        if (this.agentExecutionData.metrics) {
          this.agentExecutionData.metrics = {
            ...this.agentExecutionData.metrics,
            execution_time: event.data.execution_time || this.agentExecutionData.metrics.execution_time,
            context_reduction: event.data.context_reduction || this.agentExecutionData.metrics.context_reduction
          };
        }
        break;

      case 'error':
        // Error occurred
        this.notification = {
          type: 'error',
          title: 'Execution Error',
          message: event.data.error
        };
        break;
    }
  }

  /**
   * Toggle agent step expansion
   */
  toggleAgentStep(step: AgentStep): void {
    step.expanded = !step.expanded;
  }

  /**
   * Clear agent execution data
   */
  clearAgentExecution(): void {
    this.agentExecutionData = {
      isExecuting: false,
      startTime: null,
      endTime: null,
      steps: [],
      metrics: {
        execution_time: 0,
        agents_executed: 0,
        tools_retrieved: 0,
        tools_executed: 0,
        context_reduction: 0
      }
    };
    this.currentAgentStep = null;
    this.selectedScenarioId = '';
  }

  /**
   * Get framework badge color
   */
  getFrameworkBadgeType(framework: string): TagType {
    return framework === 'beeai' ? 'blue' : 'purple';
  }

  /**
   * Get tool execution status color
   */
  getToolStatusType(success: boolean): TagType {
    return success ? 'green' : 'red';
  }
}
