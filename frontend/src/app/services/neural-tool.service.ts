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
}
