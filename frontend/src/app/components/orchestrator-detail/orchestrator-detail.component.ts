import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { ButtonModule, InputModule, ModalModule, TabsModule, TagModule, ToggleModule, SelectModule } from 'carbon-components-angular';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PlatformApiService } from '../../services/platform-api.service';
import { WorkspaceService } from '../../services/workspace.service';
import { Agent, Orchestration, Workspace } from '../../models/platform.model';

interface WorkflowType {
  id: string;
  name: string;
  description: string;
  icon: string;
  features: string[];
  useCases: string[];
}

interface WorkflowCapabilities {
  enableCheckpointing: boolean;
  checkpointBackend: string;
  enableApprovalGates: boolean;
  enableParallelExecution: boolean;
  enableConditionalRouting: boolean;
  enableEventDriven: boolean;
  enableLongRunning: boolean;
}

@Component({
  selector: 'app-orchestrator-detail',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    InputModule,
    ModalModule,
    TabsModule,
    TagModule,
    ToggleModule,
    SelectModule,
    PageWrapperComponent,
    PageHeaderComponent
  ],
  templateUrl: './orchestrator-detail.component.html',
  styleUrl: './orchestrator-detail.component.scss'
})
export class OrchestratorDetailComponent implements OnInit, OnDestroy {
  orchestratorId: string | null = null;
  isEditMode = false;
  activeTab = 0;
  saving = false;
  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];

  orchestration: Partial<Orchestration> = {
    name: '',
    framework: 'LANGGRAPH',
    architecture_type: 'SUPERVISOR',
    workflow_type: '',
    enable_checkpointing: true,
    requires_approval: false,
    config: {}
  };

  agents: Agent[] = [];
  selectedAgents: string[] = [];
  configJson = '{}';

  workflowTypes: WorkflowType[] = [
    {
      id: 'sequential',
      name: 'Sequential',
      description: 'Execute agents one after another in a defined order',
      icon: '→',
      features: ['Linear flow', 'State passing', 'Error handling'],
      useCases: ['Data pipelines', 'Multi-step processing', 'Document workflows']
    },
    {
      id: 'parallel',
      name: 'Parallel',
      description: 'Execute multiple agents simultaneously for faster processing',
      icon: '⫴',
      features: ['Concurrent execution', 'Result aggregation', 'Fan-out/Fan-in'],
      useCases: ['Batch processing', 'Multi-source data gathering', 'Parallel analysis']
    },
    {
      id: 'conditional',
      name: 'Conditional',
      description: 'Route execution based on conditions and business logic',
      icon: '◇',
      features: ['Dynamic routing', 'Rule-based decisions', 'Branch handling'],
      useCases: ['Decision trees', 'Approval workflows', 'Smart routing']
    },
    {
      id: 'hitl',
      name: 'Human-in-the-Loop',
      description: 'Pause for human review and approval at critical points',
      icon: '👤',
      features: ['Approval gates', 'Human feedback', 'Manual intervention'],
      useCases: ['Content moderation', 'Financial approvals', 'Quality control']
    },
    {
      id: 'long_running',
      name: 'Long-Running',
      description: 'Handle workflows that span hours, days, or weeks',
      icon: '⏱',
      features: ['Persistent state', 'Resume capability', 'Timeout handling'],
      useCases: ['Background jobs', 'Scheduled tasks', 'Multi-day processes']
    },
    {
      id: 'event_driven',
      name: 'Event-Driven',
      description: 'React to external events and triggers in real-time',
      icon: '⚡',
      features: ['Event listeners', 'Async processing', 'Webhook support'],
      useCases: ['Real-time alerts', 'Webhook handlers', 'Stream processing']
    }
  ];

  capabilities: WorkflowCapabilities = {
    enableCheckpointing: true,
    checkpointBackend: 'redis',
    enableApprovalGates: false,
    enableParallelExecution: false,
    enableConditionalRouting: false,
    enableEventDriven: false,
    enableLongRunning: false
  };

  selectedWorkflowType = '';

  // Visual workflow builder state
  workflowNodes: any[] = [];
  workflowEdges: any[] = [];

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private platformService: PlatformApiService,
    private workspaceService: WorkspaceService
  ) {}

  ngOnInit() {
    this.orchestratorId = this.route.snapshot.paramMap.get('id');
    this.isEditMode = this.orchestratorId !== 'new';

    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) {
          this.loadAgents();
          if (this.isEditMode && this.orchestratorId) {
            this.loadOrchestrator(this.orchestratorId);
          }
        }
      })
    );
  }

  ngOnDestroy() {
    this.subs.forEach((s) => s.unsubscribe());
  }

  loadAgents() {
    if (!this.activeWorkspace) return;
    this.platformService.listAgents(this.activeWorkspace.id).subscribe({
      next: (agents: Agent[]) => {
        this.agents = agents;
      },
      error: (err: any) => console.error('Failed to load agents:', err)
    });
  }

  loadOrchestrator(id: string) {
    if (!this.activeWorkspace) return;
    this.platformService.getOrchestration(this.activeWorkspace.id, id).subscribe({
      next: (orch: Orchestration) => {
        this.orchestration = { ...orch };
        this.selectedWorkflowType = orch.workflow_type || '';
        this.configJson = JSON.stringify(orch.config || {}, null, 2);
        
        // Load capabilities from config
        if (orch.config) {
          this.capabilities = {
            enableCheckpointing: orch.enable_checkpointing || false,
            checkpointBackend: orch.config['checkpoint_backend'] || 'redis',
            enableApprovalGates: orch.requires_approval || false,
            enableParallelExecution: orch.config['enable_parallel'] || false,
            enableConditionalRouting: orch.config['enable_conditional'] || false,
            enableEventDriven: orch.config['enable_events'] || false,
            enableLongRunning: orch.config['enable_long_running'] || false
          };
        }
      },
      error: (err: any) => console.error('Failed to load orchestrator:', err)
    });
  }

  selectWorkflowType(typeId: string) {
    this.selectedWorkflowType = typeId;
    this.orchestration.workflow_type = typeId;

    // Auto-enable capabilities based on workflow type
    if (typeId === 'parallel') {
      this.capabilities.enableParallelExecution = true;
    } else if (typeId === 'conditional') {
      this.capabilities.enableConditionalRouting = true;
    } else if (typeId === 'hitl') {
      this.capabilities.enableApprovalGates = true;
    } else if (typeId === 'long_running') {
      this.capabilities.enableLongRunning = true;
      this.capabilities.enableCheckpointing = true;
    } else if (typeId === 'event_driven') {
      this.capabilities.enableEventDriven = true;
    }
  }

  getAgentNames(): string {
    return this.agents.map(a => a.name).join(', ');
  }

  toggleAgentSelection(agentId: string) {
    const index = this.selectedAgents.indexOf(agentId);
    if (index > -1) {
      this.selectedAgents.splice(index, 1);
    } else {
      this.selectedAgents.push(agentId);
    }
  }

  getAgentName(agentId: string): string {
    const agent = this.agents.find(a => a.id === agentId);
    return agent ? agent.name : 'Unknown Agent';
  }

  addAgentToWorkflow() {
    // Add selected agent to visual workflow builder
    if (this.selectedAgents.length > 0) {
      const agentId = this.selectedAgents[0];
      const agent = this.agents.find(a => a.id === agentId);
      if (agent) {
        this.workflowNodes.push({
          id: `node-${Date.now()}`,
          type: 'agent',
          data: { agent },
          position: { x: 100, y: 100 }
        });
      }
    }
  }

  saveOrchestrator() {
    if (!this.activeWorkspace || this.saving) return;
    
    this.saving = true;
    
    try {
      // Parse config JSON
      const config = JSON.parse(this.configJson);
      
      // Merge capabilities into config
      config.checkpoint_backend = this.capabilities.checkpointBackend;
      config.enable_parallel = this.capabilities.enableParallelExecution;
      config.enable_conditional = this.capabilities.enableConditionalRouting;
      config.enable_events = this.capabilities.enableEventDriven;
      config.enable_long_running = this.capabilities.enableLongRunning;

      const orchestrationData: any = {
        name: this.orchestration.name,
        framework: this.orchestration.framework,
        architecture_type: this.orchestration.architecture_type,
        workflow_type: this.selectedWorkflowType,
        enable_checkpointing: this.capabilities.enableCheckpointing,
        requires_approval: this.capabilities.enableApprovalGates,
        config
      };

      if (this.isEditMode && this.orchestratorId) {
        this.platformService.updateOrchestration(
          this.activeWorkspace.id,
          this.orchestratorId,
          orchestrationData
        ).subscribe({
          next: () => {
            this.saving = false;
            this.router.navigate(['/orchestrator']);
          },
          error: (err: any) => {
            this.saving = false;
            console.error('Failed to update orchestrator:', err);
          }
        });
      } else {
        this.platformService.createOrchestration(
          this.activeWorkspace.id,
          orchestrationData
        ).subscribe({
          next: () => {
            this.saving = false;
            this.router.navigate(['/orchestrator']);
          },
          error: (err: any) => {
            this.saving = false;
            console.error('Failed to create orchestrator:', err);
          }
        });
      }
    } catch (err: any) {
      this.saving = false;
      console.error('Invalid JSON config:', err);
      alert('Invalid JSON configuration. Please check your config.');
    }
  }

  cancel() {
    this.router.navigate(['/orchestrator']);
  }

  onTabChange(event: any) {
    this.activeTab = event;
  }
}

// Made with Bob
