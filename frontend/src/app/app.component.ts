import { Component, ViewEncapsulation, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterOutlet, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AuthService } from './services/auth.service';
import {
  UIShellModule,
  PlaceholderModule,
  ModalModule,
  InputModule,
  NotificationModule,
} from 'carbon-components-angular';
import { IconModule, IconService } from 'carbon-components-angular/icon';
import { ChartsModule } from '@carbon/charts-angular';
import { WorkspaceService } from './services/workspace.service';
import { Workspace, WorkspaceCreate } from './models/platform.model';

import Dashboard16 from '@carbon/icons/es/dashboard/16';
import Settings16 from '@carbon/icons/es/settings/16';
import Help20 from '@carbon/icons/es/help/20';
import Menu20 from '@carbon/icons/es/menu/20';
import Close20 from '@carbon/icons/es/close/20';
import FlowData16 from '@carbon/icons/es/flow--data/16';

import WarningAlt24 from '@carbon/icons/es/warning--alt/24';
import Time24 from '@carbon/icons/es/time/24';
import ChartLine24 from '@carbon/icons/es/chart--line/24';
import Misuse24 from '@carbon/icons/es/misuse/24';
import CloseOutline24 from '@carbon/icons/es/close--outline/24';
import Close16 from '@carbon/icons/es/close/16';
import CheckmarkOutline24 from '@carbon/icons/es/checkmark--outline/24';
import Checkmark16 from '@carbon/icons/es/checkmark/16';
import Layers32 from '@carbon/icons/es/layers/32';
import Api16 from '@carbon/icons/es/api/16';
import DataBase16 from '@carbon/icons/es/data--base/16';
import MachineLearningModel16 from '@carbon/icons/es/machine-learning-model/16';
import Network_416 from '@carbon/icons/es/network--4/16';
import SettingsAdjust32 from '@carbon/icons/es/settings--adjust/32';
import Meter16 from '@carbon/icons/es/meter/16';
import TaskComplete16 from '@carbon/icons/es/task--complete/16';
import CurrencyDollar16 from '@carbon/icons/es/currency--dollar/16';
import ArrowRight16 from '@carbon/icons/es/arrow--right/16';
import LogoGithub16 from '@carbon/icons/es/logo--github/16';
import Copy16 from '@carbon/icons/es/copy/16';
// Phase 5–7 additional icons
import Switcher16 from '@carbon/icons/es/switcher/16';
import Add16 from '@carbon/icons/es/add/16';
import Bot16 from '@carbon/icons/es/bot/16';
import Play16 from '@carbon/icons/es/play/16';
import PlugFilled16 from '@carbon/icons/es/plug--filled/16';
import UserAvatar20 from '@carbon/icons/es/user--avatar/20';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterOutlet,
    UIShellModule,
    PlaceholderModule,
    ModalModule,
    InputModule,
    NotificationModule,
    IconModule,
    ChartsModule,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  encapsulation: ViewEncapsulation.None
})
export class AppComponent implements OnInit {
  currentRoute = '';
  sidenavExpanded = false;
  isProfileMenuOpen = false;
  isDark = true;

  // Workspace state
  workspaces: Workspace[] = [];
  activeWorkspace: Workspace | null = null;
  showWorkspaceModal = false;
  newWorkspaceName = '';
  newWorkspaceDesc = '';
  notifications: any[] = [];

  // Chart Data
  meterData = [
    { group: 'Context Reduction', value: 94 }
  ];
  meterOptions = {
    title: 'Context Window Saved',
    meter: { peak: 100 },
    height: '150px',
    color: { scale: { 'Context Reduction': '#0f62fe' } },
    theme: 'g100'
  };

  ttftData = [
    { group: 'Legacy Prompt', date: 'Latency', value: 4.5 },
    { group: 'SynapseForge', date: 'Latency', value: 1.2 }
  ];
  ttftOptions = {
    title: 'TTFT (Seconds)',
    axes: {
      left: { mapsTo: 'value' },
      bottom: { mapsTo: 'date', scaleType: 'labels' }
    },
    height: '150px',
    color: { scale: { 'Legacy Prompt': '#fa4d56', 'SynapseForge': '#24a148' } },
    theme: 'g100'
  };

  costData = [
    { group: 'API Cost', date: 'Day 1', value: 100 },
    { group: 'API Cost', date: 'Day 2', value: 90 },
    { group: 'API Cost', date: 'Day 3', value: 60 },
    { group: 'API Cost', date: 'Day 4', value: 30 },
    { group: 'API Cost', date: 'Day 5', value: 10 }
  ];
  costOptions = {
    title: 'Expenditure Drop',
    axes: {
      left: { mapsTo: 'value' },
      bottom: { mapsTo: 'date', scaleType: 'labels' }
    },
    height: '150px',
    color: { scale: { 'API Cost': '#24a148' } },
    theme: 'g100'
  };

  latencyData = [
    { group: 'O(N) Scaling', x: 0, y: 1 },
    { group: 'O(N) Scaling', x: 50, y: 5 },
    { group: 'O(N) Scaling', x: 100, y: 10 },
    { group: 'O(1) Neural', x: 0, y: 1 },
    { group: 'O(1) Neural', x: 50, y: 1.1 },
    { group: 'O(1) Neural', x: 100, y: 1.15 }
  ];
  latencyOptions = {
    title: 'Search Complexity',
    axes: {
      left: { title: 'Time', mapsTo: 'y' },
      bottom: { title: 'Tools', mapsTo: 'x', scaleType: 'linear' }
    },
    height: '150px',
    color: { scale: { 'O(N) Scaling': '#fa4d56', 'O(1) Neural': '#0f62fe' } },
    curve: 'curveMonotoneX',
    theme: 'g100'
  };

  constructor(
    protected iconService: IconService,
    public workspaceService: WorkspaceService,
    public authService: AuthService,
    private router: Router
  ) {
    this.iconService.registerAll([
      Dashboard16,
      Settings16,
      Help20,
      Menu20,
      Close20,
      FlowData16,
      WarningAlt24,
      Time24,
      ChartLine24,
      Misuse24,
      CloseOutline24,
      Close16,
      CheckmarkOutline24,
      Checkmark16,
      Layers32,
      Api16,
      DataBase16,
      MachineLearningModel16,
      Network_416,
      SettingsAdjust32,
      Meter16,
      TaskComplete16,
      CurrencyDollar16,
      ArrowRight16,
      LogoGithub16,
      Copy16,
      // Phase 5–7
      Switcher16,
      Add16,
      Bot16,
      Play16,
      PlugFilled16,
      UserAvatar20,
    ]);
  }

  ngOnInit(): void {
    console.log('SynapseForge App initialized');
    const savedTheme = localStorage.getItem('theme');
    this.isDark = savedTheme !== 'light';
    this.applyTheme();
    
    // Track current route
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: any) => {
      this.currentRoute = event.urlAfterRedirects;
    });

    // Listen for navigation events from child components
    window.addEventListener('navigate-to-settings', () => {
      this.router.navigate(['/settings']);
    });

    // Load workspaces from backend
    this.workspaceService.loadWorkspaces();
    this.workspaceService.workspaces$.subscribe((ws) => this.workspaces = ws);
    this.workspaceService.activeWorkspace$.subscribe((ws) => this.activeWorkspace = ws);

    // Authentication check
    this.authService.checkAuth().subscribe(user => {
      if (!user && this.currentRoute !== '/login' && this.currentRoute !== '/') {
        this.router.navigate(['/login']);
      }
    });
  }

  toggleSidenav(): void {
    this.sidenavExpanded = !this.sidenavExpanded;
  }

  closeSidenav(): void {
    this.sidenavExpanded = false;
  }

  toggleProfileMenu(): void {
    this.isProfileMenuOpen = !this.isProfileMenuOpen;
  }

  logout(): void {
    this.authService.logout().subscribe(() => {
      this.isProfileMenuOpen = false;
      this.router.navigate(['/login']);
    });
  }

  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.closeSidenav();
  }

  isActiveRoute(route: string): boolean {
    return this.currentRoute === route || this.currentRoute.startsWith(route + '/');
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

  // ─── Workspace Management ──────────────────────────────────────

  selectWorkspace(ws: Workspace): void {
    this.workspaceService.setActiveWorkspace(ws);
  }

  openNewWorkspaceModal(): void {
    this.newWorkspaceName = '';
    this.newWorkspaceDesc = '';
    this.showWorkspaceModal = true;
  }

  closeWorkspaceModal(): void {
    this.showWorkspaceModal = false;
  }

  createWorkspace(): void {
    if (!this.newWorkspaceName.trim()) return;
    const body: WorkspaceCreate = {
      name: this.newWorkspaceName.trim(),
      description: this.newWorkspaceDesc.trim() || undefined,
    };
    this.workspaceService.createWorkspace(body).subscribe({
      next: () => {
        this.closeWorkspaceModal();
        this.showNotification('success', 'Workspace Created', `Successfully created "${body.name}"`);
      },
      error: (err) => {
        console.error('Failed to create workspace:', err);
        const detail = err.error?.detail || err.message || 'Unknown error';
        this.showNotification('error', 'Creation Failed', detail);
      },
    });
  }

  showNotification(type: 'success' | 'error' | 'info' | 'warning', title: string, message: string): void {
    const notification = {
      type,
      title,
      message,
      id: Math.random().toString(36).substring(2, 9)
    };
    this.notifications.push(notification);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      this.notifications = this.notifications.filter(n => n.id !== notification.id);
    }, 5000);
  }

  onNotificationClosed(notification: any): void {
    this.notifications = this.notifications.filter(n => n.id !== notification.id);
  }
}
