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
}
