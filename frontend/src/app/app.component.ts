import { Component, ViewEncapsulation, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WorkflowComponent } from './components/workflow/workflow.component';
import {
  UIShellModule,
  PlaceholderModule
} from 'carbon-components-angular';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import Dashboard16 from '@carbon/icons/es/dashboard/16';
import Settings16 from '@carbon/icons/es/settings/16';
import Help20 from '@carbon/icons/es/help/20';
import Menu20 from '@carbon/icons/es/menu/20';
import Close20 from '@carbon/icons/es/close/20';
import FlowData16 from '@carbon/icons/es/flow--data/16';


@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    WorkflowComponent,
    UIShellModule,
    PlaceholderModule,
    IconModule
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  encapsulation: ViewEncapsulation.None
})
export class AppComponent implements OnInit {
  activePhase: 'workflow' | 'dashboard' | 'settings' = 'dashboard';
  sidenavExpanded = false;
  isDark = true;

  constructor(protected iconService: IconService) {
    this.iconService.registerAll([
      Dashboard16,
      Settings16,
      Help20,
      Menu20,
      Close20,
      FlowData16,
    ]);
  }

  ngOnInit(): void {
    console.log('NeuralToolRouter App initialized');
    const savedTheme = localStorage.getItem('theme');
    this.isDark = savedTheme !== 'light';
    this.applyTheme();
  }

  toggleSidenav(): void {
    this.sidenavExpanded = !this.sidenavExpanded;
  }

  closeSidenav(): void {
    this.sidenavExpanded = false;
  }

  setActivePhase(phase: 'workflow' | 'dashboard' | 'settings'): void {
    this.activePhase = phase;
  }

  toggleTheme(): void {
    this.isDark = !this.isDark;
    this.applyTheme();
    localStorage.setItem('theme', this.isDark ? 'dark' : 'light');
  }

  private applyTheme(): void {
    if (this.isDark) {
      document.body.classList.remove('cds--white');
      document.body.classList.add('cds--g100');
      document.documentElement.setAttribute('data-carbon-theme', 'g100');
    } else {
      document.body.classList.remove('cds--g100');
      document.body.classList.add('cds--white');
      document.documentElement.setAttribute('data-carbon-theme', 'white');
    }
  }
}
