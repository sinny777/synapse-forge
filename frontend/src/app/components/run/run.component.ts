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
import { ToggletipModule } from 'carbon-components-angular/toggletip';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { NeuralToolService } from '../../services/neural-tool.service';
import { ConfigService, FIELD_TOOLTIPS, ValidationResult } from '../../services/config.service';

import PlayFilled16 from '@carbon/icons/es/play--filled/16';
import Reset16 from '@carbon/icons/es/reset/16';
import ChevronDown16 from '@carbon/icons/es/chevron--down/16';
import InformationFilled16 from '@carbon/icons/es/information--filled/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import Download16 from '@carbon/icons/es/download/16';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import Warning16 from '@carbon/icons/es/warning/16';
import ViewAll16 from '@carbon/icons/es/view/16';
import List16 from '@carbon/icons/es/list/16';
import ListDropdown16 from '@carbon/icons/es/list--dropdown/16';

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

  constructor(
    private service: NeuralToolService,
    private iconService: IconService,
    public configService: ConfigService,
    private ngZone: NgZone
  ) {
    this.iconService.registerAll([
      PlayFilled16, Reset16, ChevronDown16, InformationFilled16,
      TrashCan16, Download16, Checkmark16, Warning16, ViewAll16,
      List16, ListDropdown16,
      Rocket20, Settings20, ChartLine20, Keyboard20,
      Rocket16, Settings16, ChartLine16, Keyboard16,
    ]);
  }

  ngOnInit(): void {
    const savedMode = localStorage.getItem('run_viewMode');
    if (savedMode) this.viewMode = savedMode;
    this.runValidation();
    this.loadModels();
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
}
