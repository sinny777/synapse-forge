import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TabsModule, ButtonModule, SelectModule, NotificationModule, DropdownModule, TagModule, BreadcrumbModule } from 'carbon-components-angular';
import { TagType } from 'carbon-components-angular/tag';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { TooltipModule } from 'carbon-components-angular/tooltip';
import { GenerateComponent } from '../generate/generate.component';
import { TrainComponent } from '../train/train.component';
import { RunComponent } from '../run/run.component';
import { ConfigService, CONFIG_PROFILES, ConfigProfile } from '../../services/config.service';
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

  private subs: Subscription[] = [];

  constructor(
    private iconService: IconService,
    public configService: ConfigService
  ) {
    this.iconService.registerAll([
      MagicWand16, ModelBuilder16, Rocket16,
      Upload16, Download16, Checkmark16, WarningAltFilled16, Edit16,
      Save16, TrashCan16, InformationFilled16, SettingsAdjust16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.configService.syncStatus$.subscribe((s) => (this.syncStatus = s)),
      this.configService.activeProfile$.subscribe((p) => (this.selectedProfileId = p))
    );
  }

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
}
