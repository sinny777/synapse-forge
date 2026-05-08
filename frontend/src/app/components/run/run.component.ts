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
  TabsModule,
  DropdownModule,
  TagModule,
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

// Size 20 icons for section headers
import Rocket20 from '@carbon/icons/es/rocket/20';
import Settings20 from '@carbon/icons/es/settings/20';
import ChartLine20 from '@carbon/icons/es/chart--line/20';
import Keyboard20 from '@carbon/icons/es/keyboard/20';

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

  constructor(
    private service: NeuralToolService,
    private iconService: IconService,
    public configService: ConfigService
  ) {
    this.iconService.registerAll([
      PlayFilled16, Reset16, ChevronDown16, InformationFilled16,
      TrashCan16, Download16, Checkmark16, Warning16, ViewAll16,
      Rocket20, Settings20, ChartLine20, Keyboard20,
    ]);
  }

  ngOnInit(): void {
    this.runValidation();
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
  }

  private buildPayload(): any {
    return {
      query: this.queryInput,
      runtime: { ...this.runtimeConfig },
      llm: { ...this.runtimeLLMConfig },
    };
  }

  onSubmit(): void {
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
    const payload = this.buildPayload();

    this.service.run(payload).subscribe({
      next: (res) => {
        this.isLoading = false;
        this.resultData = res.data || res;
        this.configService.markSynced();
        this.notification = { type: 'success', title: 'Query Processed', message: res.message || 'Tool routing completed successfully.' };
      },
      error: (err) => {
        this.isLoading = false;
        this.configService.markError();
        this.notification = { type: 'error', title: 'Execution Failed', message: err.error?.message || err.message || 'Query execution failed.' };
      },
    });
  }
}
