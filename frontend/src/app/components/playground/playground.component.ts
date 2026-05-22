/**
 * Playground Component
 *
 * Phase 7 — Chat interface (left 70%) with tracing panel (right 30%).
 * Connects to backend SSE endpoint for real-time orchestration execution
 * and trace event visualization.
 */

import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule, NotificationModule, IconModule,
  TagModule, DropdownModule,
} from 'carbon-components-angular';
import { IconService } from 'carbon-components-angular/icon';
import { Subscription } from 'rxjs';
import { TagType } from 'carbon-components-angular/tag';
import { WorkspaceService } from '../../services/workspace.service';
import { PlatformApiService } from '../../services/platform-api.service';
import {
  Workspace, Orchestration, PlaygroundMessage, TraceEvent,
} from '../../models/platform.model';
import { PageHeaderComponent } from '../shared/page-header/page-header.component';
import { PageWrapperComponent } from '../shared/page-wrapper/page-wrapper.component';

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
    TagModule, DropdownModule,
    PageHeaderComponent, PageWrapperComponent,
  ],
  templateUrl: './playground.component.html',
  styleUrls: ['./playground.component.scss'],
})
export class PlaygroundComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('chatContainer') chatContainer!: ElementRef;
  @ViewChild('messageInput') messageInput!: ElementRef;

  messages: PlaygroundMessage[] = [];
  traceEvents: TraceEvent[] = [];
  orchestrations: Orchestration[] = [];
  selectedOrchestrationId: string | null = null;
  userInput = '';
  isExecuting = false;
  showTrace = true;
  notification: any = null;

  activeWorkspace: Workspace | null = null;
  private subs: Subscription[] = [];
  private shouldScrollChat = false;

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
    this.subs.forEach((s) => s.unsubscribe());
  }

  ngAfterViewChecked(): void {
    if (this.shouldScrollChat) {
      this.scrollToBottom();
      this.shouldScrollChat = false;
    }
  }

  // ─── Data Loading ──────────────────────────────────────────────

  loadOrchestrations(): void {
    if (!this.activeWorkspace) return;
    this.platformApi.listOrchestrations(this.activeWorkspace.id).subscribe({
      next: (orchs) => {
        this.orchestrations = orchs;
        if (orchs.length > 0 && !this.selectedOrchestrationId) {
          this.selectedOrchestrationId = orchs[0].id;
        }
      },
      error: () => {},
    });
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
    this.shouldScrollChat = true;

    // Clear previous trace
    this.traceEvents = [];
    this.isExecuting = true;

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
          });

          // If it's an assistant response, add to chat
          if (event.type === 'assistant') {
            this.messages.push({
              role: 'assistant',
              content: event.detail || event.label,
              timestamp: new Date(),
            });
            this.shouldScrollChat = true;
          }

          // If complete or error, stop executing
          if (event.type === 'complete' || event.type === 'error') {
            this.isExecuting = false;
          }
        }
      );
    } catch (err: any) {
      this.messages.push({
        role: 'system',
        content: `Error: ${err.message}`,
        timestamp: new Date(),
      });
      this.isExecuting = false;
      this.shouldScrollChat = true;
    }
  }

  onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
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

  getTraceIcon(type: string): string {
    switch (type) {
      case 'router': return '🔍';
      case 'llm_call': return '🧠';
      case 'tool_call': return '⚡';
      case 'tool_result': return '✅';
      case 'assistant': return '💬';
      case 'error': return '❌';
      case 'complete': return '🏁';
      default: return '📌';
    }
  }

  getTraceColor(type: string): TagType {
    switch (type) {
      case 'router': return 'blue';
      case 'llm_call': return 'purple';
      case 'tool_call': return 'teal';
      case 'tool_result': return 'green';
      case 'assistant': return 'cyan';
      case 'error': return 'red';
      case 'complete': return 'cool-gray';
      default: return 'gray';
    }
  }

  private scrollToBottom(): void {
    if (this.chatContainer) {
      const el = this.chatContainer.nativeElement;
      el.scrollTop = el.scrollHeight;
    }
  }

  dismissNotification(): void {
    this.notification = null;
  }
}
