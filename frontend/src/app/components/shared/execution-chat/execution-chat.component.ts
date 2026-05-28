import { AfterViewChecked, Component, ElementRef, EventEmitter, Input, Output, SimpleChanges, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule,
  InputModule,
  NotificationModule,
  StructuredListModule,
  TagModule,
  TilesModule,
} from 'carbon-components-angular';
import { TagType } from 'carbon-components-angular/tag';
import {
  ChatExecutionContext,
  PlaygroundMessage,
  TraceEvent,
} from '../../../models/platform.model';

@Component({
  selector: 'app-execution-chat',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    InputModule,
    NotificationModule,
    StructuredListModule,
    TagModule,
    TilesModule,
  ],
  templateUrl: './execution-chat.component.html',
  styleUrls: ['./execution-chat.component.scss'],
})
export class ExecutionChatComponent implements AfterViewChecked {
  @ViewChild('chatContainer') chatContainer!: ElementRef;

  @Input() title = 'Execution Chat';
  @Input() emptyTitle = 'Start a conversation';
  @Input() emptyDescription = 'Type a message to start testing.';
  @Input() placeholder = 'Type a message...';
  @Input() disabled = false;
  @Input() showTrace = true;
  @Input() isExecuting = false;
  @Input() messages: PlaygroundMessage[] = [];
  @Input() traceEvents: TraceEvent[] = [];
  @Input() userInput = '';
  @Input() context: ChatExecutionContext | null = null;

  @Output() userInputChange = new EventEmitter<string>();
  @Output() send = new EventEmitter<void>();
  @Output() clear = new EventEmitter<void>();
  @Output() toggleTrace = new EventEmitter<void>();
  @Output() stop = new EventEmitter<void>();

  expandedMessageIndexes = new Set<number>();
  expandedTraceIndexes = new Set<number>();

  private shouldScrollChat = false;

  ngAfterViewChecked(): void {
    if (this.shouldScrollChat) {
      this.scrollToBottom();
      this.shouldScrollChat = false;
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['messages'] || changes['traceEvents'] || changes['isExecuting']) {
      this.shouldScrollChat = true;
    }
  }

  onInputChange(value: string): void {
    this.userInput = value;
    this.userInputChange.emit(value);
  }

  onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send.emit();
    }
  }

  getTraceIcon(type: string): string {
    switch (type) {
      case 'router':
        return '🔍';
      case 'llm_call':
        return '🧠';
      case 'thought':
        return '💭';
      case 'reasoning':
        return '🧩';
      case 'tool_call':
        return '⚡';
      case 'tool_result':
        return '✅';
      case 'assistant':
        return '💬';
      case 'error':
        return '❌';
      case 'complete':
        return '🏁';
      default:
        return '📌';
    }
  }

  getTraceColor(type: string): TagType {
    switch (type) {
      case 'router':
        return 'blue';
      case 'llm_call':
        return 'purple';
      case 'thought':
        return 'warm-gray';
      case 'reasoning':
        return 'teal';
      case 'tool_call':
        return 'cyan';
      case 'tool_result':
        return 'green';
      case 'assistant':
        return 'cool-gray';
      case 'error':
        return 'red';
      case 'complete':
        return 'gray';
      default:
        return 'high-contrast';
    }
  }

  trackMessage(index: number, message: PlaygroundMessage): string {
    return `${message.role}-${message.timestamp?.toString() || index}-${message.content}`;
  }

  trackTrace(index: number, event: TraceEvent): string {
    return `${event.type}-${event.timestamp}-${index}`;
  }

  formatStructured(value: any): string {
    if (value === null || value === undefined) {
      return '';
    }

    if (typeof value === 'string') {
      return value;
    }

    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  parseStructured(value: string | undefined | null): any | null {
    if (!value) {
      return null;
    }

    const trimmed = value.trim();
    if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) {
      return null;
    }

    try {
      return JSON.parse(trimmed);
    } catch {
      return null;
    }
  }

  getMessageStructuredContent(message: PlaygroundMessage): any | null {
    if (message.metadata && Object.keys(message.metadata).length > 0) {
      return message.metadata;
    }
    return this.parseStructured(message.content);
  }

  getTraceStructuredDetail(event: TraceEvent): any | null {
    if (event.metadata && Object.keys(event.metadata).length > 0) {
      return event.metadata;
    }
    return this.parseStructured(event.detail);
  }

  getObjectEntries(value: Record<string, any> | null | undefined): { key: string; value: any }[] {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return [];
    }
    return Object.entries(value).map(([key, nestedValue]) => ({ key, value: nestedValue }));
  }

  hasStructuredMessage(message: PlaygroundMessage): boolean {
    return !!this.getMessageStructuredContent(message);
  }

  hasStructuredTrace(event: TraceEvent): boolean {
    return !!this.getTraceStructuredDetail(event);
  }

  toggleMessage(index: number): void {
    if (this.expandedMessageIndexes.has(index)) {
      this.expandedMessageIndexes.delete(index);
    } else {
      this.expandedMessageIndexes.add(index);
    }
  }

  toggleTraceEvent(index: number): void {
    if (this.expandedTraceIndexes.has(index)) {
      this.expandedTraceIndexes.delete(index);
    } else {
      this.expandedTraceIndexes.add(index);
    }
  }

  isMessageExpanded(index: number): boolean {
    return this.expandedMessageIndexes.has(index);
  }

  isTraceExpanded(index: number): boolean {
    return this.expandedTraceIndexes.has(index);
  }

  getMessageActionLabel(message: PlaygroundMessage): string {
    if (message.role === 'tool') {
      return `Executing Tool${message.toolName ? `: ${message.toolName}` : ''}`;
    }
    if (message.role === 'system') {
      return message.content || 'Reasoning';
    }
    if (message.role === 'assistant') {
      return 'Agent Output';
    }
    return 'Details';
  }

  getTraceActionLabel(event: TraceEvent): string {
    switch (event.type) {
      case 'thought':
        return 'Thinking';
      case 'reasoning':
        return 'Reasoning';
      case 'router':
        return 'NeuralToolRouter';
      case 'tool_call':
        return 'Executing Tool';
      case 'tool_result':
        return 'Tool Output';
      case 'llm_call':
        return 'Invoking LLM';
      case 'assistant':
        return 'Agent Output';
      case 'error':
        return 'Error Details';
      default:
        return event.label || 'Details';
    }
  }

  getUserVisibleMessageText(message: PlaygroundMessage): string {
    if (message.role === 'assistant' || message.role === 'user') {
      return message.content;
    }

    if (message.role === 'tool') {
      const metadata = this.getMessageStructuredContent(message);
      if (metadata && typeof metadata === 'object') {
        return metadata['tool_name'] || metadata['result_preview'] || message.toolName || 'Tool execution';
      }
      return message.toolName || message.content || 'Tool execution';
    }

    if (message.role === 'system') {
      return '';
    }

    return message.content || this.getMessageActionLabel(message);
  }

  shouldShowCollapsedMessage(message: PlaygroundMessage): boolean {
    return message.role === 'tool' || message.role === 'system';
  }

  shouldShowCollapsedTrace(event: TraceEvent): boolean {
    return !!this.getTraceStructuredDetail(event);
  }

  getMessageDisplayEntries(message: PlaygroundMessage): { key: string; value: any }[] {
    const structured = this.getMessageStructuredContent(message);
    const entries = this.getObjectEntries(structured);
    const hiddenKeys = new Set([
      'llm_config',
      'schema',
      'connection_config',
      'system_prompt',
      'attached_tool_ids',
      'attached_tools',
      'collaborator_ids',
      'collaborators',
      'router_candidates',
    ]);

    return entries.filter((entry) => !hiddenKeys.has(entry.key));
  }

  getTraceDisplayEntries(event: TraceEvent): { key: string; value: any }[] {
    const structured = this.getTraceStructuredDetail(event);
    const entries = this.getObjectEntries(structured);
    const hiddenKeys = new Set([
      'llm_config',
      'schema',
      'connection_config',
      'system_prompt',
      'attached_tool_ids',
      'attached_tools',
      'collaborator_ids',
      'collaborators',
    ]);

    return entries.filter((entry) => !hiddenKeys.has(entry.key));
  }

  isMultiline(value: string | undefined | null): boolean {
    return !!value && value.includes('\n');
  }

  private scrollToBottom(): void {
    if (this.chatContainer) {
      const el = this.chatContainer.nativeElement;
      el.scrollTop = el.scrollHeight;
    }
  }
}

// Made with Bob
