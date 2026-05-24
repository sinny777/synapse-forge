import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { IconModule, IconService } from 'carbon-components-angular/icon';

import ArrowRight16 from '@carbon/icons/es/arrow--right/16';
import LogoGithub16 from '@carbon/icons/es/logo--github/16';
import WarningAlt24 from '@carbon/icons/es/warning--alt/24';
import Time24 from '@carbon/icons/es/time/24';
import ChartLine24 from '@carbon/icons/es/chart--line/24';
import Misuse24 from '@carbon/icons/es/misuse/24';
import CloseOutline24 from '@carbon/icons/es/close--outline/24';
import Close16 from '@carbon/icons/es/close/16';
import CheckmarkOutline24 from '@carbon/icons/es/checkmark--outline/24';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import Warning20 from '@carbon/icons/es/warning/20';
import ModelBuilder20 from '@carbon/icons/es/model-builder/20';
import Layers32 from '@carbon/icons/es/layers/32';
import Api16 from '@carbon/icons/es/api/16';
import DataBase16 from '@carbon/icons/es/data--base/16';
import MachineLearningModel16 from '@carbon/icons/es/machine-learning-model/16';
import Network_416 from '@carbon/icons/es/network--4/16';
import SettingsAdjust32 from '@carbon/icons/es/settings--adjust/32';
import Meter16 from '@carbon/icons/es/meter/16';
import TaskComplete16 from '@carbon/icons/es/task--complete/16';
import CurrencyDollar16 from '@carbon/icons/es/currency--dollar/16';
import FlowData16 from '@carbon/icons/es/flow--data/16';
import Copy16 from '@carbon/icons/es/copy/16';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, IconModule],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss']
})
export class HomeComponent {
  constructor(
    private router: Router,
    private iconService: IconService
  ) {
    this.iconService.registerAll([
      ArrowRight16,
      LogoGithub16,
      WarningAlt24,
      Time24,
      ChartLine24,
      Misuse24,
      CloseOutline24,
      Close16,
      CheckmarkOutline24,
      Checkmark16,
      Warning20,
      ModelBuilder20,
      Layers32,
      Api16,
      DataBase16,
      MachineLearningModel16,
      Network_416,
      SettingsAdjust32,
      Meter16,
      TaskComplete16,
      CurrencyDollar16,
      FlowData16,
      Copy16,
    ]);
  }

  navigateToWorkflow(): void {
    this.router.navigate(['/workflow']);
  }

  openGithub(): void {
    window.open('https://github.com/sinny777/synapse-forge', '_blank');
  }
}

// Made with Bob
