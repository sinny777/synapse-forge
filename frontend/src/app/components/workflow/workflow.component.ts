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
import Warning16 from '@carbon/icons/es/warning/16';
import Edit16 from '@carbon/icons/es/edit/16';

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
      Upload16, Download16, Checkmark16, Warning16, Edit16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.configService.syncStatus$.subscribe((s) => (this.syncStatus = s)),
      this.configService.activeProfile$.subscribe((p) => (this.selectedProfileId = p))
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  onProfileChange(event: any): void {
    const profileId = event?.item?.id || event?.id || event;
    this.configService.setActiveProfile(profileId);
    this.selectedProfileId = profileId;
    // Update the selected state in profileItems
    this.profileItems = this.profileItems.map(p => ({ ...p, selected: p.id === profileId }));
    this.notification = {
      type: 'info',
      title: 'Profile Applied',
      message: `Switched to "${this.profiles.find(p => p.id === profileId)?.name}" profile. Open config sections to see updated values.`,
    };
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
