import { Routes } from '@angular/router';
import { HomeComponent } from './components/home/home.component';
import { LoginComponent } from './components/login/login.component';
import { WorkflowComponent } from './components/workflow/workflow.component';
import { LLMConfigComponent } from './components/llm-config/llm-config.component';
import { ToolRegistryComponent } from './components/tool-registry/tool-registry.component';
import { AgentStudioComponent } from './components/agent-studio/agent-studio.component';
import { OrchestratorBuilderComponent } from './components/orchestrator-builder/orchestrator-builder.component';
import { PlaygroundComponent } from './components/playground/playground.component';
import { authGuard } from './guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    component: HomeComponent,
    pathMatch: 'full'
  },
  {
    path: 'login',
    component: LoginComponent
  },
  {
    path: 'workflow',
    component: WorkflowComponent,
    canActivate: [authGuard]
  },
  {
    path: 'settings',
    component: LLMConfigComponent,
    canActivate: [authGuard]
  },
  {
    path: 'tools',
    component: ToolRegistryComponent,
    canActivate: [authGuard]
  },
  {
    path: 'neural-router',
    component: WorkflowComponent,
    canActivate: [authGuard]
  },
  {
    path: 'agents',
    component: AgentStudioComponent,
    canActivate: [authGuard]
  },
  {
    path: 'orchestrator',
    component: OrchestratorBuilderComponent,
    canActivate: [authGuard]
  },
  {
    path: 'playground',
    component: PlaygroundComponent,
    canActivate: [authGuard]
  },
  {
    path: '**',
    redirectTo: ''
  }
];

// Made with Bob
