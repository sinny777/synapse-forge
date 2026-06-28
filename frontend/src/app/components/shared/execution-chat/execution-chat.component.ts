import { AfterViewChecked, Component, ElementRef, EventEmitter, Input, NgZone, Output, SimpleChanges, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ButtonModule,
  InputModule,
  NotificationModule,
  TagModule,
  TilesModule,
  IconModule,
} from 'carbon-components-angular';
import { TagType } from 'carbon-components-angular/tag';
import { IconService } from 'carbon-components-angular/icon';
import {
  ChatExecutionContext,
  PlaygroundMessage,
  TraceEvent,
} from '../../../models/platform.model';
import { MarkdownPipe } from '../../../pipes/markdown.pipe';

// Icons
import Bot16 from '@carbon/icons/es/bot/16';
import Bot20 from '@carbon/icons/es/bot/20';
import Time16 from '@carbon/icons/es/time/16';
import Network_316 from '@carbon/icons/es/network--3/16';
import Idea16 from '@carbon/icons/es/idea/16';
import Chat16 from '@carbon/icons/es/chat/16';
import Document16 from '@carbon/icons/es/document/16';
import List16 from '@carbon/icons/es/list/16';
import PlayFilled16 from '@carbon/icons/es/play--filled/16';
import ChevronDown16 from '@carbon/icons/es/chevron--down/16';
import User16 from '@carbon/icons/es/user/16';
import CheckmarkFilled20 from '@carbon/icons/es/checkmark--filled/20';
import ChartLine20 from '@carbon/icons/es/chart--line/20';
import Collaborate16 from '@carbon/icons/es/collaborate/16';
import DataVis_416 from '@carbon/icons/es/data-vis--4/16';

/**
 * Agent Step interface matching run.component pattern
 */
interface AgentStep {
  agentName: string;
  agentRole: string;
  framework: string;
  status: 'activated' | 'retrieving_tools' | 'executing_tools' | 'thinking' | 'complete';
  reasoningStream?: string;
  latestToolOutput?: string;
  toolsRetrieved: Array<{
    name: string;
    score: number;
    type?: string;
    args?: any;
    id?: string;
    description?: string;
    server_name?: string;
    parameters?: any;
    input_schema?: any;
    output_format?: string;
  }>;
  reasoning: string;
  toolExecutions: Array<{
    tool: string;
    args: any;
    result: any;
    time: number;
    success: boolean;
    expanded?: boolean;
  }>;
  input?: string;
  routerQuery?: string;
  updates?: string[];
  rawEvents?: Array<{
    type: string;
    label: string;
    detail?: string;
    status?: string;
    timestamp: string | number;
    latency_ms?: number;
    metadata?: Record<string, any>;
  }>;
  response: string;
  timestamp: number;
  startTime?: number;
  endTime?: number;
  executionTime?: number;
  expanded: boolean;
  toolsExpanded: boolean;
  executionsExpanded: boolean;
  planningExpanded: boolean;
  eventsExpanded?: boolean;
}

/**
 * Agent Execution Data interface
 */
interface AgentExecutionData {
  agentId?: string;
  agentName?: string;
  userQuery?: string;
  executionMode?: string;
  finalResponse?: string;
  steps: AgentStep[];
  metrics: {
    execution_time?: number;
    agents_executed?: number;
    tools_retrieved?: number;
    tools_executed?: number;
    context_reduction?: number;
  };
  isExecuting: boolean;
  startTime?: number | null;
  endTime?: number | null;
}

@Component({
  selector: 'app-execution-chat',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    InputModule,
    NotificationModule,
    TagModule,
    TilesModule,
    IconModule,
    MarkdownPipe,
  ],
  templateUrl: './execution-chat.component.html',
  styleUrls: ['./execution-chat.component.scss'],
})
export class ExecutionChatComponent implements AfterViewChecked {
  @ViewChild('chatContainer') chatContainer!: ElementRef;

  @Input() title = 'Agent Execution';
  @Input() emptyTitle = 'Start a conversation';
  @Input() emptyDescription = 'Type a message to start testing the agent.';
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
  @Output() stop = new EventEmitter<void>();

  // Agent execution data
  agentExecutionData: AgentExecutionData = {
    isExecuting: false,
    startTime: null,
    endTime: null,
    steps: [],
    metrics: {
      execution_time: 0,
      agents_executed: 0,
      tools_retrieved: 0,
      tools_executed: 0,
      context_reduction: 0,
    },
  };

  currentAgentStep: AgentStep | null = null;
  private shouldScrollChat = false;
  private agentToolsMap = new Map<string, AgentStep['toolsRetrieved']>();
  private agentRouterQueryMap = new Map<string, string>();

  constructor(
    private iconService: IconService,
    private ngZone: NgZone
  ) {
    this.iconService.registerAll([
      Bot16, Bot20, Time16, Network_316, Idea16, Chat16, Document16,
      List16, PlayFilled16, ChevronDown16, User16, CheckmarkFilled20,
      ChartLine20, Collaborate16, DataVis_416,
    ]);
  }

  ngAfterViewChecked(): void {
    if (this.shouldScrollChat) {
      this.scrollToBottom();
      this.shouldScrollChat = false;
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    // Initialize execution data when execution starts
    if (changes['isExecuting'] && this.isExecuting && !this.agentExecutionData.startTime) {
      // Clear maps for new execution
      this.agentToolsMap.clear();
      this.agentRouterQueryMap.clear();
      
      // Find user message to get the query
      const userMessage = this.messages.find(m => m.role === 'user');
      this.agentExecutionData = {
        agentId: this.context?.id,
        agentName: this.context?.label || 'Agent',
        userQuery: userMessage?.content || '',
        finalResponse: '',
        steps: [],
        metrics: {
          execution_time: 0,
          agents_executed: 0,
          tools_retrieved: 0,
          tools_executed: 0,
          context_reduction: 0,
        },
        isExecuting: true,
        startTime: Date.now(),
        endTime: null,
      };
      this.currentAgentStep = null;
      console.log('✅ Initialized execution data:', this.agentExecutionData);
    }

    if (changes['traceEvents'] && this.traceEvents) {
      // Process only new events
      const previousLength = changes['traceEvents'].previousValue?.length || 0;
      const currentLength = this.traceEvents.length;
      
      console.log('📊 Trace events changed:', {
        previousLength,
        currentLength,
        newEvents: currentLength - previousLength,
        allEvents: this.traceEvents
      });
      
      if (currentLength > previousLength) {
        // Process only the new events
        for (let i = previousLength; i < currentLength; i++) {
          console.log(`Processing event ${i + 1}/${currentLength}:`, this.traceEvents[i]);
          this.handleAgentEvent(this.traceEvents[i]);
        }
      }
    }
    
    if (changes['isExecuting']) {
      this.agentExecutionData.isExecuting = this.isExecuting;
    }
    
    if (changes['messages'] || changes['traceEvents'] || changes['isExecuting']) {
      this.shouldScrollChat = true;
    }
  }

  /**
   * Handle agent execution events (matching run.component pattern)
   */
  private handleAgentEvent(event: TraceEvent): void {
    const eventType = event.type;
    const eventData = event.metadata || {};
    const eventDetail = this.extractAgentResponseText(event.detail);

    console.log('🔍 handleAgentEvent called:', {
      type: eventType,
      label: event.label,
      detail: event.detail,
      metadata: eventData,
      currentStep: this.currentAgentStep?.agentName,
      stepsCount: this.agentExecutionData.steps.length
    });

    switch (eventType) {
      case 'router':
      case 'tool_retrieval': {
        // Tools retrieved by router
        const routerAgentName = eventData['agent_name'] || this.context?.label || 'Agent';
        const tools = eventData['selected_tools'] || eventData['tools'] || eventData['retrieved_tools'] || [];
        const normalizedTools = this.normalizeToolList(tools);
        const query = eventData['query'] || '';
        
        // Persist tools retrieved for this agent name
        this.agentToolsMap.set(routerAgentName, normalizedTools);
        if (query) {
          this.agentRouterQueryMap.set(routerAgentName, query);
        }
        
        // Mark previous step as complete if it's not already complete
        if (this.currentAgentStep && this.currentAgentStep.status !== 'complete') {
          this.currentAgentStep.status = 'complete';
        }
        
        // Collapse previous step if exists and has no error
        if (this.currentAgentStep && !this.hasStepError(this.currentAgentStep)) {
          this.currentAgentStep.expanded = false;
        }

        // Create new step representing tool retrieval
        this.currentAgentStep = {
          agentName: routerAgentName,
          agentRole: eventData['agent_role'] || eventData['role'] || (routerAgentName === this.context?.label ? 'Primary Agent' : 'Collaborator'),
          framework: eventData['framework'] || eventData['model'] || this.context?.config?.framework || 'langgraph',
          status: 'retrieving_tools',
          toolsRetrieved: normalizedTools,
          routerQuery: query,
          reasoning: '',
          reasoningStream: '',
          toolExecutions: [],
          updates: [],
          latestToolOutput: '',
          response: '',
          timestamp: typeof event.timestamp === 'number' ? event.timestamp : Date.now(),
          startTime: Date.now(),
          expanded: true,
          toolsExpanded: false,
          executionsExpanded: false,
          planningExpanded: false,
          rawEvents: [],
          eventsExpanded: false,
        };
        this.agentExecutionData.steps.push(this.currentAgentStep);
        this.pushAgentUpdate(this.currentAgentStep, `🔍 NeuralToolRouter selected ${normalizedTools.length} tools`);
        
        this.agentExecutionData.metrics.tools_retrieved =
          (this.agentExecutionData.metrics.tools_retrieved || 0) + tools.length;
        break;
      }

      case 'thought':
      case 'llm_call': {
        const agentName = eventData['agent_name'] || this.context?.label || 'Agent';
        const inputPrompt = eventData['input'] ? this.extractAgentResponseText(eventData['input']) : '';
        const thoughtText = eventDetail || this.extractAgentResponseText(eventData['reasoning'] || eventData['thought'] || eventData['message']);
        const parsedThoughtToolCall = this.tryExtractStructuredToolCall(thoughtText);

        // If the current step was created by a router event for this agent and is waiting, reuse it
        if (this.currentAgentStep && 
            this.currentAgentStep.agentName === agentName && 
            this.currentAgentStep.status === 'retrieving_tools') {
          this.currentAgentStep.status = 'thinking';
          if (inputPrompt) {
            this.currentAgentStep.input = inputPrompt;
          }
          if (thoughtText) {
            this.currentAgentStep.reasoning = parsedThoughtToolCall || thoughtText;
          }
          this.pushAgentUpdate(this.currentAgentStep, this.getThinkingUpdateText(thoughtText) || `🤔 Agent started thinking...`);
        } else {
          // Collapse previous step if exists and has no error
          if (this.currentAgentStep && !this.hasStepError(this.currentAgentStep)) {
            this.currentAgentStep.expanded = false;
          }

          // Create new agent step
          this.currentAgentStep = {
            agentName: agentName,
            agentRole: eventData['agent_role'] || eventData['role'] || (agentName === this.context?.label ? 'Primary Agent' : 'Collaborator'),
            framework: eventData['framework'] || eventData['model'] || this.context?.config?.framework || 'langgraph',
            status: 'thinking',
            toolsRetrieved: this.agentToolsMap.get(agentName) || [],
            routerQuery: this.agentRouterQueryMap.get(agentName) || undefined,
            reasoning: parsedThoughtToolCall || thoughtText,
            reasoningStream: '',
            toolExecutions: [],
            updates: [],
            latestToolOutput: '',
            response: '',
            timestamp: typeof event.timestamp === 'number' ? event.timestamp : Date.now(),
            startTime: Date.now(),
            expanded: true,
            toolsExpanded: false,
            executionsExpanded: false,
            planningExpanded: false,
            rawEvents: [],
            eventsExpanded: false,
          };
          if (inputPrompt) {
            this.currentAgentStep.input = inputPrompt;
          }
          this.pushAgentUpdate(this.currentAgentStep, this.getThinkingUpdateText(thoughtText) || `🤔 Agent started thinking...`);
          this.agentExecutionData.steps.push(this.currentAgentStep);
        }
        break;
      }

      case 'reasoning': {
        const agentName = eventData['agent_name'] || this.context?.label || 'Agent';
        const reasoning = eventDetail || this.extractAgentResponseText(eventData['reasoning'] || eventData['thought'] || eventData['message']);
        const parsedReasoningToolCall = this.tryExtractStructuredToolCall(reasoning);
        
        if (this.currentAgentStep && this.currentAgentStep.agentName === agentName) {
          if (this.currentAgentStep.status === 'retrieving_tools') {
            this.currentAgentStep.status = 'thinking';
          }
          this.currentAgentStep.reasoning = parsedReasoningToolCall || reasoning;
          this.currentAgentStep.reasoningStream = reasoning;
          this.pushAgentUpdate(this.currentAgentStep, this.getThinkingUpdateText(reasoning));
          // Auto-expand reasoning/thinking section while agent is thinking
          this.currentAgentStep.planningExpanded = true;
        }
        break;
      }

      case 'tool_call':
        // Tool call initiated
        if (this.currentAgentStep) {
          this.currentAgentStep.status = 'executing_tools';
          const toolName = eventData['tool_name'] || event.label?.replace('Calling ', '') || 'Unknown Tool';
          const toolArgs = eventData['tool_args'] || eventData['args'] || eventData['arguments'] || {};

          this.currentAgentStep.toolExecutions.push({
            tool: toolName,
            args: toolArgs,
            result: 'Executing...',
            time: 0,
            success: true,
            expanded: true,
          });
          
          this.currentAgentStep.reasoning = this.buildToolCallSummary(toolName, toolArgs);
          this.currentAgentStep.latestToolOutput = '';
          this.pushAgentUpdate(this.currentAgentStep, `🔧 Executing tool: ${toolName}`);
        }
        break;

      case 'tool_result': {
        // Tool execution completed
        const toolResultName = eventData['tool_name'] || event.label?.replace(' Result', '')?.replace(' Error', '') || '';
        
        // Find the step that has this tool execution in progress
        let targetStep = this.currentAgentStep;
        if (targetStep && (!targetStep.toolExecutions.length || !targetStep.toolExecutions.some(e => e.tool === toolResultName && e.result === 'Executing...'))) {
          // Search backwards for the step that called this tool
          for (let j = this.agentExecutionData.steps.length - 1; j >= 0; j--) {
            const step = this.agentExecutionData.steps[j];
            if (step.toolExecutions.some(e => e.tool === toolResultName && e.result === 'Executing...')) {
              targetStep = step;
              break;
            }
          }
        }

        if (targetStep && targetStep.toolExecutions.length > 0) {
          const matchingExec = targetStep.toolExecutions.find(e => e.tool === toolResultName && e.result === 'Executing...');
          const lastExecution = matchingExec || targetStep.toolExecutions[targetStep.toolExecutions.length - 1];
          const toolResult = eventData['result'] ?? eventData['output'] ?? eventDetail;
          const executionTime = event.latency_ms || eventData['execution_time'] || 0;
          const success = eventData['success'] !== false && event.status !== 'error';

          const normalizedToolResult = this.normalizeToolResult(toolResult);
          const toolOutputText = this.extractAgentResponseText(normalizedToolResult);
          lastExecution.result = normalizedToolResult;
          lastExecution.time = executionTime / 1000;
          lastExecution.success = success;
          
          targetStep.latestToolOutput = toolOutputText;
          this.pushAgentUpdate(
            targetStep,
            success
              ? `✅ Tool ${toolResultName} succeeded\n\n${toolOutputText}`
              : `❌ Tool ${toolResultName} failed\n\n${toolOutputText}`
          );
          
          this.agentExecutionData.metrics.tools_executed =
            (this.agentExecutionData.metrics.tools_executed || 0) + 1;

          // Check if any tool calls are still executing in this step
          const stillRunning = targetStep.toolExecutions.some(e => e.result === 'Executing...');
          if (!stillRunning) {
            targetStep.status = 'complete';
          }
        }
        break;
      }

      case 'assistant':
        // Agent final response
        if (this.currentAgentStep) {
          this.currentAgentStep.status = 'complete';
          const response = eventData['response'] ?? eventData['output'] ?? eventDetail;
          const responseText = this.extractAgentResponseText(response);
          this.currentAgentStep.response = responseText || this.currentAgentStep.latestToolOutput || this.currentAgentStep.reasoningStream || this.currentAgentStep.reasoning;
          
          if (eventData['input']) {
            this.currentAgentStep.input = this.extractAgentResponseText(eventData['input']);
          }
          
          this.currentAgentStep.endTime = Date.now();
          if (this.currentAgentStep.startTime) {
            this.currentAgentStep.executionTime =
              (this.currentAgentStep.endTime - this.currentAgentStep.startTime) / 1000;
          }
          
          this.pushAgentUpdate(this.currentAgentStep, `🏁 Agent response generated\n\n${this.currentAgentStep.response}`);
          
          // Collapse on completion if no error
          if (!this.hasStepError(this.currentAgentStep)) {
            this.currentAgentStep.expanded = false;
          }
          
          // Store as final response
          this.agentExecutionData.finalResponse = this.currentAgentStep.response;
          this.agentExecutionData.metrics.agents_executed =
            (this.agentExecutionData.metrics.agents_executed || 0) + 1;
        }
        break;

      case 'collaborator':
        // Agent-to-agent communication
        if (this.currentAgentStep) {
          const collabDetail = event.detail || eventData['message'] || 'Agent collaboration';
          this.pushAgentUpdate(this.currentAgentStep, `🤝 Collaboration: ${collabDetail}`);
        }
        break;

      case 'complete':
        // Execution completed
        if (this.agentExecutionData.startTime) {
          this.agentExecutionData.endTime = Date.now();
          this.agentExecutionData.metrics.execution_time =
            (this.agentExecutionData.endTime - this.agentExecutionData.startTime) / 1000;
        }
        this.agentExecutionData.isExecuting = false;
        
        // Mark all steps as complete and clean up any pending executions
        this.agentExecutionData.steps.forEach(step => {
          step.status = 'complete';
          if (step.toolExecutions) {
            step.toolExecutions.forEach(exec => {
              if (exec.result === 'Executing...') {
                exec.result = 'Completed';
              }
            });
          }
          
          if (this.hasStepError(step)) {
            step.expanded = true;
          } else {
            step.expanded = false;
          }
        });
        break;

      case 'error':
        // Error occurred
        const errorAgentName = eventData['agent_name'] || this.context?.label || 'Agent';
        if (!this.currentAgentStep) {
          this.currentAgentStep = {
            agentName: errorAgentName,
            agentRole: 'Primary Agent',
            framework: 'langgraph',
            status: 'complete',
            toolsRetrieved: [],
            reasoning: '',
            reasoningStream: '',
            toolExecutions: [],
            updates: [],
            latestToolOutput: '',
            response: '',
            timestamp: Date.now(),
            expanded: true,
            toolsExpanded: false,
            executionsExpanded: false,
            planningExpanded: false,
            rawEvents: [],
            eventsExpanded: false,
          };
          this.agentExecutionData.steps.push(this.currentAgentStep);
        }
        this.currentAgentStep.status = 'complete';
        const errorMsg = event.detail || eventData['error'] || 'An error occurred';
        this.pushAgentUpdate(this.currentAgentStep, `❌ Error: ${errorMsg}`);
        // Keep expanded to let user see error details
        this.currentAgentStep.expanded = true;
        break;
    }

    const targetStep = this.resolveEventStep(event, eventData);
    if (targetStep) {
      this.appendRawEvent(targetStep, event);
    }
  }

  private extractAgentResponseText(response: any): string {
    if (response == null) return '';
    if (typeof response === 'string') {
      const trimmed = response.trim();
      if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
        try {
          const parsed = JSON.parse(trimmed);
          if (parsed && typeof parsed === 'object') {
            return this.extractAgentResponseText(parsed);
          }
        } catch {}
      }
      return response;
    }
    if (Array.isArray(response)) {
      return response.map((item) => this.extractAgentResponseText(item)).filter(Boolean).join('\n\n');
    }
    if (typeof response === 'object') {
      const prioritizedKeys = ['text', 'content', 'message', 'result', 'output', 'response'];
      for (const key of prioritizedKeys) {
        if (key in response) {
          const extracted = this.extractAgentResponseText((response as any)[key]);
          if (extracted) return extracted;
        }
      }
      try {
        return JSON.stringify(response, null, 2);
      } catch {
        return String(response);
      }
    }
    return String(response);
  }

  private normalizeToolResult(result: any): any {
    if (result == null) return 'Success';
    if (typeof result === 'string') return result;
    if (typeof result === 'object' && Array.isArray(result.content)) {
      const textContent = result.content
        .filter((item: any) => item?.type === 'text' && item?.text)
        .map((item: any) => item.text)
        .join('\n\n');
      if (textContent) return textContent;
    }
    return result;
  }

  private normalizeToolList(tools: any[] = []): AgentStep['toolsRetrieved'] {
    return tools.map((tool) => ({
      ...tool,
      score: typeof tool?.score === 'number' ? tool.score : Number(tool?.score || 0),
    }));
  }

  private pushAgentUpdate(step: AgentStep, updateText: string): void {
    const normalized = updateText?.trim();
    if (!normalized) return;
    if (!step.updates) step.updates = [];

    const lastIndex = step.updates.length - 1;
    const lastUpdate = lastIndex >= 0 ? step.updates[lastIndex] : undefined;
    if (lastUpdate) {
      const lastNormalized = lastUpdate.trim();
      if (normalized === lastNormalized) return;
      if (normalized.startsWith(lastNormalized) && normalized.length > lastNormalized.length) {
        step.updates[lastIndex] = normalized;
        return;
      }
    }

    const condensed = normalized.replace(/\s+/g, ' ').trim();
    const lastCondensed = lastUpdate?.replace(/\s+/g, ' ').trim();
    if (lastCondensed === condensed) return;

    step.updates.push(normalized);
  }

  private tryExtractStructuredToolCall(value: string): string {
    const normalized = value?.trim();
    if (!normalized) {
      return '';
    }

    const parsed = this.extractToolCallObject(normalized);
    if (!parsed) {
      return '';
    }

    const toolName = parsed['name'] || parsed['tool'] || parsed['action'] || 'Tool';
    const args = parsed['arguments'] || parsed['args'] || parsed['parameters'] || {};
    return this.buildToolCallSummary(toolName, args);
  }

  private getThinkingUpdateText(value: string): string {
    const normalized = value?.trim();
    if (!normalized) {
      return '';
    }

    const structuredToolCall = this.tryExtractStructuredToolCall(normalized);
    if (structuredToolCall) {
      return structuredToolCall;
    }

    const compact = normalized.replace(/\s+/g, ' ').trim();
    if (compact.startsWith('{"name"') || compact === '{' || compact === '[{') {
      return '';
    }

    return normalized;
  }

  private buildToolCallSummary(toolName: string, toolArgs: any): string {
    const argsText = this.extractAgentResponseText(toolArgs);
    return argsText
      ? `Planned tool call: ${toolName}\n\nArguments:\n${argsText}`
      : `Planned tool call: ${toolName}`;
  }

  private extractToolCallObject(value: string): Record<string, any> | null {
    const normalized = value?.trim();
    if (!normalized) {
      return null;
    }

    const tryParse = (candidate: string): Record<string, any> | null => {
      try {
        const parsed = JSON.parse(candidate);
        if (
          parsed &&
          typeof parsed === 'object' &&
          !Array.isArray(parsed) &&
          (parsed['name'] || parsed['tool'] || parsed['action'])
        ) {
          return parsed as Record<string, any>;
        }
      } catch {}
      return null;
    };

    const direct = tryParse(normalized);
    if (direct) {
      return direct;
    }

    const matches = normalized.match(/\{[\s\S]*\}/g) || [];
    for (let index = matches.length - 1; index >= 0; index--) {
      const parsed = tryParse(matches[index]);
      if (parsed) {
        return parsed;
      }
    }

    return null;
  }

  private appendRawEvent(step: AgentStep, event: TraceEvent): void {
    if (!step.rawEvents) {
      step.rawEvents = [];
    }

    const lastEvent = step.rawEvents[step.rawEvents.length - 1];
    if (
      lastEvent &&
      lastEvent.type === event.type &&
      lastEvent.label === event.label &&
      lastEvent.detail === event.detail
    ) {
      return;
    }

    step.rawEvents.push({
      type: event.type,
      label: event.label,
      detail: event.detail,
      status: event.status,
      timestamp: event.timestamp,
      latency_ms: event.latency_ms,
      metadata: event.metadata,
    });
  }

  private resolveEventStep(event: TraceEvent, eventData: Record<string, any>): AgentStep | null {
    const agentName = eventData['agent_name'];
    const toolName = eventData['tool_name'];

    if (toolName) {
      for (let index = this.agentExecutionData.steps.length - 1; index >= 0; index--) {
        const step = this.agentExecutionData.steps[index];
        if (step.toolExecutions.some((execution) => execution.tool === toolName)) {
          return step;
        }
      }
    }

    if (agentName) {
      for (let index = this.agentExecutionData.steps.length - 1; index >= 0; index--) {
        const step = this.agentExecutionData.steps[index];
        if (step.agentName === agentName) {
          return step;
        }
      }
    }

    if (this.currentAgentStep) {
      return this.currentAgentStep;
    }

    if (this.agentExecutionData.steps.length > 0) {
      return this.agentExecutionData.steps[this.agentExecutionData.steps.length - 1];
    }

    return null;
  }

  getEventTagType(type: string, status?: string): TagType {
    if (status === 'error' || type === 'error') {
      return 'red';
    }

    switch (type) {
      case 'assistant':
      case 'complete':
        return 'green';
      case 'tool_call':
      case 'tool_result':
        return 'blue';
      case 'reasoning':
      case 'thought':
      case 'llm_call':
        return 'purple';
      case 'router':
      case 'tool_retrieval':
        return 'teal';
      case 'collaborator':
        return 'cyan';
      default:
        return 'gray';
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

  onSend(): void {
    if (!this.userInput.trim() || this.disabled || this.isExecuting) return;
    
    // Clear maps for new execution
    this.agentToolsMap.clear();
    this.agentRouterQueryMap.clear();
    
    // Initialize execution data
    this.agentExecutionData = {
      agentId: this.context?.id,
      agentName: this.context?.label || 'Agent',
      userQuery: this.userInput,
      finalResponse: '',
      steps: [],
      metrics: {
        execution_time: 0,
        agents_executed: 0,
        tools_retrieved: 0,
        tools_executed: 0,
        context_reduction: 0,
      },
      isExecuting: true,
      startTime: Date.now(),
      endTime: null,
    };
    this.currentAgentStep = null;
    
    this.send.emit();
  }

  onClear(): void {
    this.agentToolsMap.clear();
    this.agentRouterQueryMap.clear();
    
    this.agentExecutionData = {
      isExecuting: false,
      startTime: null,
      endTime: null,
      steps: [],
      metrics: {
        execution_time: 0,
        agents_executed: 0,
        tools_retrieved: 0,
        tools_executed: 0,
        context_reduction: 0,
      },
    };
    this.currentAgentStep = null;
    this.clear.emit();
  }

  toggleAgentStep(step: AgentStep): void {
    step.expanded = !step.expanded;
  }

  getFrameworkBadgeType(framework: string): TagType {
    return framework === 'beeai' ? 'blue' : 'purple';
  }

  getToolStatusType(success: boolean): TagType {
    return success ? 'green' : 'red';
  }

  getConfigSummary(): string[] {
    if (!this.context?.config) return [];
    const config = this.context.config;
    const summary: string[] = [];

    if (config.llm_model) summary.push(`Model: ${config.llm_model}`);
    if (config.use_neural_router !== undefined) {
      summary.push(`Router: ${config.use_neural_router ? 'Enabled' : 'Disabled'}`);
    }
    if (config.router_top_k) summary.push(`Top-K: ${config.router_top_k}`);
    if (config.tool_count !== undefined) summary.push(`Tools: ${config.tool_count}`);
    if (config.collaborator_count !== undefined && config.collaborator_count > 0) {
      summary.push(`Collaborators: ${config.collaborator_count}`);
    }
    if (config.memory_type) summary.push(`Memory: ${config.memory_type}`);
    if (config.max_iterations) summary.push(`Max Iterations: ${config.max_iterations}`);

    return summary;
  }

  hasConfig(): boolean {
    return !!this.context?.config && Object.keys(this.context.config).length > 0;
  }

  formatStructured(value: any): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') {
      try {
        const parsed = JSON.parse(value);
        if (parsed && typeof parsed === 'object') {
          return JSON.stringify(parsed, null, 2);
        }
      } catch {}
      return value;
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  hasRecursionLimitError(step: AgentStep): boolean {
    return !!step.updates && step.updates.some(u => 
      u.toLowerCase().includes('recursion limit') || 
      u.toLowerCase().includes('recursion_limit')
    );
  }

  hasStepError(step: AgentStep): boolean {
    const hasAgentErr = !!step.updates && step.updates.some(u => 
      u.includes('❌ Error') || 
      u.includes('Error:') || 
      u.toLowerCase().includes('error') || 
      u.toLowerCase().includes('recursion limit') || 
      u.toLowerCase().includes('recursion_limit')
    );
    const hasToolErr = !!step.toolExecutions && step.toolExecutions.some(e => !e.success);
    return hasAgentErr || hasToolErr;
  }

  private scrollToBottom(): void {
    if (this.chatContainer) {
      const el = this.chatContainer.nativeElement;
      el.scrollTop = el.scrollHeight;
    }
  }
}

// Made with Bob
