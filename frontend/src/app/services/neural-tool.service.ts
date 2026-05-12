import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class NeuralToolService {
  private apiUrl = 'http://localhost:8000/api';

  constructor(private http: HttpClient) {}

  generate(config: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/generate`, config);
  }

  train(config: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/train`, config);
  }

  run(config: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/run`, config);
  }

  async runStream(config: any, onChunk: (data: any) => void): Promise<void> {
    const response = await fetch(`${this.apiUrl}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });

    if (!response.body) {
      throw new Error('ReadableStream not supported.');
    }
    
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || 'Streaming failed');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.trim()) {
          onChunk(JSON.parse(line));
        }
      }
    }
    if (buffer.trim()) {
      onChunk(JSON.parse(buffer));
    }
  }

  evaluate(query: string, top_k: number = 5, model_path?: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/evaluate`, { query, top_k, model_path });
  }

  getStatus(): Observable<any> {
    return this.http.get(`${this.apiUrl}/status`);
  }

  getSyntheticData(): Observable<any> {
    return this.http.get(`${this.apiUrl}/data/synthetic`);
  }

  getCachedTools(): Observable<any> {
    return this.http.get(`${this.apiUrl}/data/tools`);
  }

  saveSyntheticData(data: any[]): Observable<any> {
    return this.http.post(`${this.apiUrl}/data/synthetic`, { data });
  }

  getModels(): Observable<any> {
    return this.http.get(`${this.apiUrl}/models`);
  }

  archiveModel(name: string, version: string, sourceDir: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/models/archive`, { name, version, source_dir: sourceDir });
  }

  deleteModel(modelName: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/models/${modelName}`);
  }

  // ============================================================================
  // Dataset Management Methods
  // ============================================================================

  /**
   * Get list of available datasets
   */
  getDatasets(): Observable<any> {
    return this.http.get(`${this.apiUrl}/datasets`);
  }

  /**
   * Archive a dataset with name and version
   */
  archiveDataset(name: string, version: string, sourceFile: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/datasets/archive`, { name, version, source_file: sourceFile });
  }

  /**
   * Delete a dataset
   */
  deleteDataset(datasetName: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/datasets/${datasetName}`);
  }

  /**
   * Load a specific dataset for editing/training
   */
  loadDataset(datasetPath: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/datasets/load`, { dataset_path: datasetPath });
  }

  // ============================================================================
  // Agent Orchestration Methods
  // ============================================================================

  /**
   * Get list of available agent scenarios
   */
  getAgentScenarios(): Observable<any> {
    return this.http.get(`${this.apiUrl}/agents/scenarios`);
  }

  /**
   * Get detailed information about a specific agent scenario
   */
  getAgentScenario(scenarioId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/agents/scenarios/${scenarioId}`);
  }

  /**
   * Execute an agent scenario with Server-Sent Events streaming
   * @param scenarioId - ID of the scenario to execute
   * @param llmConfig - LLM configuration
   * @param runtimeConfig - Runtime configuration
   * @param onEvent - Callback for each event
   */
  async executeAgentScenario(
    scenarioId: string,
    llmConfig: any,
    runtimeConfig: any,
    onEvent: (event: any) => void
  ): Promise<void> {
    const response = await fetch(`${this.apiUrl}/agents/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario_id: scenarioId,
        llm_config: llmConfig,
        runtime_config: runtimeConfig
      })
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || 'Agent execution failed');
    }

    if (!response.body) {
      throw new Error('ReadableStream not supported');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      // Process SSE format: "data: {...}\n\n"
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const jsonStr = line.substring(6); // Remove "data: " prefix
          if (jsonStr.trim()) {
            try {
              const event = JSON.parse(jsonStr);
              onEvent(event);
            } catch (e) {
              console.error('Failed to parse SSE event:', e, jsonStr);
            }
          }
        }
      }
    }
  }
}
