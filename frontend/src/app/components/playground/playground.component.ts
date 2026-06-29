/**
 * Playground Component
 *
 * Phase 7 — Chat interface (left 70%) with tracing panel (right 30%).
 * Connects to backend SSE endpoint for real-time orchestration execution
 * and trace event visualization.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule, NotificationModule, IconModule,
  DropdownModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import {
  ChatExecutionContext, Workspace, Orchestration, PlaygroundMessage, TraceEvent,
} from '../../models/platform.model';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';
import { ExecutionChatComponent } from '../shared/execution-chat/execution-chat.component';

import Send16 from '@carbon/icons/es/send/16';
import Renew16 from '@carbon/icons/es/renew/16';
import Close16 from '@carbon/icons/es/close/16';
import Bot16 from '@carbon/icons/es/bot/16';
import UserAvatar16 from '@carbon/icons/es/user--avatar/16';

@Component({
  selector: 'app-playground',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    ButtonModule, NotificationModule, IconModule,
    DropdownModule,
    PageHeaderComponent, PageWrapperComponent, ExecutionChatComponent,
  ],
  templateUrl: './playground.component.html',
  styleUrls: ['./playground.component.scss'],
})
export class PlaygroundComponent implements OnInit, OnDestroy {

  messages: PlaygroundMessage[] = [];
  traceEvents: TraceEvent[] = [];
  orchestrations: Orchestration[] = [];
  selectedOrchestrationId: string | null = null;
  orchestrationDropdownItems: any[] = [];
  userInput = '';
  isExecuting = false;
  showTrace = true;
  notification: any = null;

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];
  private executionAbortController: AbortController | null = null;

  constructor(
    private workspaceService: WorkspaceService,
    private platformApi: PlatformApiService,
    private iconService: IconService,
  ) {
    this.iconService.registerAll([
      Send16, Renew16, Close16, Bot16, UserAvatar16,
    ]);
  }

  ngOnInit(): void {
    this.subs.push(
      this.workspaceService.activeWorkspace$.subscribe((ws) => {
        this.activeWorkspace = ws;
        if (ws) this.loadOrchestrations();
      })
    );
  }

  ngOnDestroy(): void {
    this.executionAbortController?.abort();
    this.subs.forEach((s) => s.unsubscribe());
  }

  // ─── Data Loading ──────────────────────────────────────────────

  loadOrchestrations(): void {
    if (!this.activeWorkspace) return;
    this.platformApi.listOrchestrations(this.activeWorkspace.id).subscribe({
      next: (orchs) => {
        this.orchestrations = orchs;
        this.orchestrationDropdownItems = orchs.map((o) => ({
          content: `${o.name} (${o.framework})`,
          id: o.id,
          selected: false,
        }));
        if (orchs.length > 0 && !this.selectedOrchestrationId) {
          this.selectedOrchestrationId = orchs[0].id;
          this.orchestrationDropdownItems[0].selected = true;
        }
      },
      error: () => {},
    });
  }

  onOrchestrationSelect(event: any): void {
    this.selectedOrchestrationId = event.item.id;
  }

  // ─── Chat ──────────────────────────────────────────────────────

  async sendMessage(): Promise<void> {
    if (!this.userInput.trim() || this.isExecuting) return;
    if (!this.selectedOrchestrationId) {
      this.notification = { type: 'warning', title: 'No Orchestration', message: 'Select an orchestration first.' };
      return;
    }

    const prompt = this.userInput.trim();
    this.userInput = '';

    // Add user message
    this.messages.push({
      role: 'user',
      content: prompt,
      timestamp: new Date(),
    });

    // Clear previous trace
    this.traceEvents = [];
    this.isExecuting = true;
    this.executionAbortController = new AbortController();

    try {
      await this.platformApi.executeOrchestration(
        this.selectedOrchestrationId,
        prompt,
        (event: any) => {
          // Add trace event
          this.traceEvents.push({
            type: event.type,
            label: event.label,
            detail: event.detail || '',
            timestamp: event.timestamp,
            latency_ms: event.latency_ms,
            status: event.status || 'success',
            metadata: event.metadata || event.data,
            format: event.type === 'assistant' ? 'markdown' : 'json',
          });

          // If it's an assistant response, add to chat
          if (event.type === 'assistant') {
            this.messages.push({
              role: 'assistant',
              content: event.detail || event.label,
              timestamp: new Date(),
              metadata: event.metadata || event.data,
              format: 'markdown',
            });
          }

          // If complete or error, stop executing
          if (event.type === 'complete' || event.type === 'error') {
            this.isExecuting = false;
          }
        },
        this.executionAbortController.signal
      );
    } catch (err: any) {
      const aborted = err?.name === 'AbortError';
      this.messages.push({
        role: 'system',
        content: aborted ? 'Execution stopped by user.' : `Error: ${err.message}`,
        timestamp: new Date(),
      });
      this.isExecuting = false;
    } finally {
      this.executionAbortController = null;
      this.isExecuting = false;
    }
  }

  stopExecution(): void {
    if (!this.isExecuting) {
      return;
    }

    this.executionAbortController?.abort();
  }

  clearChat(): void {
    this.messages = [];
    this.traceEvents = [];
  }

  toggleTrace(): void {
    this.showTrace = !this.showTrace;
  }

  getSelectedOrchestrationName(): string {
    return this.orchestrations.find((o) => o.id === this.selectedOrchestrationId)?.name || 'None';
  }

  get executionContext(): ChatExecutionContext | null {
    const selected = this.orchestrations.find((o) => o.id === this.selectedOrchestrationId);
    if (!selected) return null;
    return {
      id: selected.id,
      label: selected.name,
      type: 'orchestration',
    };
  }

  dismissNotification(): void {
    this.notification = null;
  }
}
