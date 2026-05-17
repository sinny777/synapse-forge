import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  TabsModule, ButtonModule, SelectModule, NotificationModule,
  DropdownModule, TagModule, BreadcrumbModule, LoadingModule, ToggleModule,
} from 'carbon-components-angular';
import { TagType } from 'carbon-components-angular/tag';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { TooltipModule } from 'carbon-components-angular/tooltip';
import { GenerateComponent } from '../generate/generate.component';
import { TrainComponent } from '../train/train.component';
import { RunComponent } from '../run/run.component';
import { ConfigService, CONFIG_PROFILES, ConfigProfile } from '../../services/config.service';
import { WorkspaceService } from '../../services/workspace.service';
import { LLMConfigService } from '../../services/llm-config.service';
import { PlatformApiService } from '../../services/platform-api.service';
import { NeuralToolService } from '../../services/neural-tool.service';
import { LLMModelConfig } from '../../models/llm-config.model';
import { Tool, Workspace } from '../../models/platform.model';
import { Subscription } from 'rxjs';

import MagicWand16 from '@carbon/icons/es/magic-wand/16';
import ModelBuilder16 from '@carbon/icons/es/model-builder/16';
import Rocket16 from '@carbon/icons/es/rocket/16';
import Upload16 from '@carbon/icons/es/upload/16';
import Download16 from '@carbon/icons/es/download/16';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import WarningAltFilled16 from '@carbon/icons/es/warning--filled/16';
import Edit16 from '@carbon/icons/es/edit/16';
import Save16 from '@carbon/icons/es/save/16';
import TrashCan16 from '@carbon/icons/es/trash-can/16';
import InformationFilled16 from '@carbon/icons/es/information--filled/16';
import SettingsAdjust16 from '@carbon/icons/es/settings--adjust/16';
import Copy16 from '@carbon/icons/es/copy/16';

@Component({
  selector: 'app-workflow',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    TabsModule,
    ButtonModule,
    SelectModule,
    NotificationModule,
    IconModule,
    DropdownModule,
    TagModule,
    GenerateComponent,
    TrainComponent,
    RunComponent,
    BreadcrumbModule,
    TooltipModule,
    LoadingModule,
    ToggleModule,
  ],
  templateUrl: './workflow.component.html',
  styleUrls: ['./workflow.component.scss'],
})
export class WorkflowComponent implements OnInit, OnDestroy {
  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;
  @ViewChild(GenerateComponent) generateComp!: GenerateComponent;
  @ViewChild(TrainComponent) trainComp!: TrainComponent;
  @ViewChild(RunComponent) runComp!: RunComponent;

  activeTab = 0;
  profiles: ConfigProfile[] = CONFIG_PROFILES;
  /** Carbon Dropdown items for profile selector */
  profileItems = CONFIG_PROFILES.map(p => ({ content: p.name, id: p.id, selected: p.id === 'default' }));
  selectedProfileId = 'default';
  syncStatus: 'synced' | 'unsaved' | 'error' = 'unsaved';
  notification: any = null;

  // ─── Workspace State ────────────────────────────────────────────
  activeWorkspace: Workspace | null = null;

  // ─── LLM Configuration per Phase ───────────────────────────────
  llmConfigs: LLMModelConfig[] = [];
  selectedGenerateLLMId = '';
  selectedTrainLLMId = '';
  selectedRunLLMId = '';
  llmDropdownItems: any[] = [];

  // Cloning State
  isCloningPhase1 = false;
  isCloningPhase2 = false;
  isCloningPhase3 = false;

  private subs: Subscription[] = [];

  constructor(
    private iconService: IconService,
    public configService: ConfigService,
    public workspaceService: WorkspaceService,
    private llmConfigService: LLMConfigService,
    private platformApi: PlatformApiService,
    private neuralToolService: NeuralToolService,
  ) {
    this.iconService.registerAll([
      MagicWand16, ModelBuilder16, Rocket16,
      Upload16, Download16, Checkmark16, WarningAltFilled16, Edit16,
      Save16, TrashCan16, InformationFilled16, SettingsAdjust16,
      Copy16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.configService.syncStatus$.subscribe((s) => (this.syncStatus = s)),
      this.configService.activeProfile$.subscribe((p) => (this.selectedProfileId = p))
    );

    // Subscribe to workspace changes to load workspace-scoped resources
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        if (ws && ws.id !== this.activeWorkspace?.id) {
          this.activeWorkspace = ws;
          this.loadWorkspaceResources();
        } else if (!ws) {
          this.activeWorkspace = null;
        }
      })
    );

    // Subscribe to LLM config changes
    this.subs.push(
      this.llmConfigService.configurations$.subscribe((configs) => {
        this.llmConfigs = configs;
        this.updateLLMDropdownItems();
      })
    );
  }

  // ─── Tab Navigation ─────────────────────────────────────────────

  onTabSelected(event: number | { index?: number }): void {
    const index = typeof event === 'number' ? event : event?.index ?? 0;
    this.activeTab = index;
    if (index === 0 && this.generateComp) {
      this.generateComp.loadSyntheticData();
    } else if (index === 1 && this.trainComp) {
      this.trainComp.loadModels();
    } else if (index === 2 && this.runComp) {
      this.runComp.loadModels();
    }
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  // ─── Profile Management ─────────────────────────────────────────

  onProfileChange(event: any): void {
    const profileId = event?.item?.id || event?.id || event;
    this.configService.setActiveProfile(profileId);
    this.selectedProfileId = profileId;
    this.updateProfileItems();
    this.notification = {
      type: 'info',
      title: 'Profile Applied',
      message: `Switched to "${this.profiles.find(p => p.id === profileId)?.name}" profile.`,
    };
    // Refresh current active tab data after profile change
    this.onTabSelected(this.activeTab);
  }

  updateProfileItems(): void {
    this.profiles = this.configService.getProfiles();
    this.profileItems = this.profiles.map(p => ({ 
      content: p.name, 
      id: p.id, 
      selected: p.id === this.selectedProfileId 
    }));
  }

  isCustomProfileSelected(): boolean {
    return this.selectedProfileId.startsWith('custom_');
  }

  saveCurrentAsProfile(): void {
    const snapshot = this.configService.loadConfigSnapshot();
    if (!snapshot) {
      this.notification = { type: 'warning', title: 'No Config', message: 'No configuration found to save. Please make changes first.' };
      return;
    }
    
    const profileName = prompt('Enter a name for the new profile:', `Profile ${new Date().toLocaleTimeString()}`);
    if (!profileName) return;
    
    const newProfile = this.configService.saveAsNewProfile(profileName, 'User saved profile', snapshot);
    this.updateProfileItems();
    this.onProfileChange(newProfile.id);
    this.notification = { type: 'success', title: 'Profile Saved', message: `Saved configuration as "${profileName}".` };
  }

  deleteCurrentProfile(): void {
    if (!this.isCustomProfileSelected()) return;
    const confirmDelete = confirm('Are you sure you want to delete this custom profile?');
    if (!confirmDelete) return;

    this.configService.deleteProfile(this.selectedProfileId);
    this.updateProfileItems();
    this.onProfileChange('default');
    this.notification = { type: 'success', title: 'Profile Deleted', message: 'Custom profile deleted successfully.' };
  }

  openLLMConfig(): void {
    // Emit event to parent component to switch to settings view
    window.dispatchEvent(new CustomEvent('navigate-to-settings'));
  }

  onExport(): void {
    // Gather config from all child components via a custom event or build a full payload
    // For now, export the stored snapshot
    const snapshot = this.configService.loadConfigSnapshot();
    if (snapshot) {
      this.configService.exportConfig(snapshot);
      this.notification = { type: 'success', title: 'Exported', message: 'Configuration saved as JSON file.' };
    } else {
      this.notification = { type: 'warning', title: 'No Config', message: 'No configuration snapshot found. Make a change first.' };
    }
  }

  triggerImport(): void {
    this.fileInput?.nativeElement.click();
  }

  async onFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    try {
      const config = await this.configService.importConfig(input.files[0]);
      this.configService.saveConfigSnapshot(config);
      this.notification = {
        type: 'success',
        title: 'Imported',
        message: 'Configuration loaded. Refresh tabs to see updated values.',
      };
      this.configService.markUnsaved();
    } catch (e: any) {
      this.notification = { type: 'error', title: 'Import Failed', message: e.message };
    }
    input.value = '';
  }

  getSyncLabel(): string {
    switch (this.syncStatus) {
      case 'synced': return 'Synced';
      case 'unsaved': return 'Unsaved Changes';
      case 'error': return 'Sync Error';
      default: return '';
    }
  }

  getSyncTagType(): TagType {
    switch (this.syncStatus) {
      case 'synced': return 'green';
      case 'unsaved': return 'warm-gray';
      case 'error': return 'red';
      default: return 'gray';
    }
  }

  // ═══════════════════════════════════════════════════════════════
  //  Workspace-Scoped Resources (NeuralToolRouter)
  // ═══════════════════════════════════════════════════════════════

  isDefaultWorkspace(): boolean {
    return this.activeWorkspace?.is_default === true;
  }

  private loadWorkspaceResources(): void {
    if (!this.activeWorkspace) return;
    const wsId = this.activeWorkspace.id;

    // Load LLM configs for this workspace
    this.llmConfigService.loadConfigurations(wsId);

    // Load LLM configs for this workspace
    this.llmConfigService.loadConfigurations(wsId);
  }

  // ─── LLM Configuration per Phase ───────────────────────────────

  private updateLLMDropdownItems(): void {
    this.llmDropdownItems = this.llmConfigs.map((c) => ({
      content: `${c.name} (${c.provider}/${c.model_name})`,
      id: c.id,
      selected: false,
    }));
  }

  getGenerateLLMItems(): any[] {
    return this.llmDropdownItems.map((item) => ({
      ...item,
      selected: item.id === this.selectedGenerateLLMId,
    }));
  }

  getTrainLLMItems(): any[] {
    return this.llmDropdownItems.map((item) => ({
      ...item,
      selected: item.id === this.selectedTrainLLMId,
    }));
  }

  getRunLLMItems(): any[] {
    return this.llmDropdownItems.map((item) => ({
      ...item,
      selected: item.id === this.selectedRunLLMId,
    }));
  }

  onGenerateLLMSelect(event: any): void {
    this.selectedGenerateLLMId = event?.item?.id || event?.id || '';
    this.applyLLMToPhase('generate');
  }

  onTrainLLMSelect(event: any): void {
    this.selectedTrainLLMId = event?.item?.id || event?.id || '';
    this.applyLLMToPhase('train');
  }

  onRunLLMSelect(event: any): void {
    this.selectedRunLLMId = event?.item?.id || event?.id || '';
    this.applyLLMToPhase('run');
  }

  private applyLLMToPhase(phase: string): void {
    let configId = '';
    if (phase === 'generate') configId = this.selectedGenerateLLMId;
    else if (phase === 'train') configId = this.selectedTrainLLMId;
    else if (phase === 'run') configId = this.selectedRunLLMId;

    if (!configId) return;

    const config = this.llmConfigService.getConfigurationById(configId);
    if (!config) return;

    this.notification = {
      type: 'info',
      title: 'LLM Applied',
      message: `Applied "${config.name}" (${config.provider}/${config.model_name}) to ${phase} phase.`,
    };
  }

  getSelectedLLMName(phase: string): string {
    let configId = '';
    if (phase === 'generate') configId = this.selectedGenerateLLMId;
    else if (phase === 'train') configId = this.selectedTrainLLMId;
    else if (phase === 'run') configId = this.selectedRunLLMId;

    if (!configId) return 'Not selected';
    const config = this.llmConfigService.getConfigurationById(configId);
    return config ? config.name : 'Not selected';
  }

  hasLLMConfigs(): boolean {
    return this.llmConfigs.length > 0;
  }

  getSelectedMCPCount(): number {
    return 0; // Handled in GenerateComponent now
  }

  // ─── Clone Default Workspace Resources ─────────────────────────

  clonePhaseResources(phase: 'generate' | 'train' | 'run'): void {
    if (!this.activeWorkspace || this.activeWorkspace.is_default) {
      this.notification = {
        type: 'warning',
        title: 'Cannot Clone',
        message: 'Please select a custom workspace to clone resources into.',
      };
      return;
    }

    if (phase === 'generate') this.isCloningPhase1 = true;
    else if (phase === 'train') this.isCloningPhase2 = true;
    else if (phase === 'run') this.isCloningPhase3 = true;

    this.neuralToolService.cloneWorkflowResources(
      this.activeWorkspace.id, phase
    ).subscribe({
      next: (res: any) => {
        this.isCloningPhase1 = false;
        this.isCloningPhase2 = false;
        this.isCloningPhase3 = false;
        const phaseLabel = phase === 'generate' ? 'Phase 1' : phase === 'train' ? 'Phase 2' : 'Phase 3';
        this.notification = {
          type: 'success',
          title: `${phaseLabel} Resources Cloned`,
          message: res.message || `Default workspace resources cloned for ${phaseLabel}.`,
        };
        this.loadWorkspaceResources();
      },
      error: (err: any) => {
        this.isCloningPhase1 = false;
        this.isCloningPhase2 = false;
        this.isCloningPhase3 = false;
        this.notification = {
          type: 'error',
          title: 'Clone Failed',
          message: err.error?.detail || err.message || `Failed to clone resources.`,
        };
      },
    });
  }
}
