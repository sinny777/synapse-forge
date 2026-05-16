/**
 * SynapseForge — Workspace Service
 *
 * Manages global workspace state via a BehaviorSubject.
 * All platform views subscribe to activeWorkspace$ and scope their
 * API calls to the currently selected workspace.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap, catchError, of } from 'rxjs';
import { Workspace, WorkspaceCreate, WorkspaceUpdate } from '../models/platform.model';

const API_BASE = 'http://localhost:8000/api';
const STORAGE_KEY = 'ntr_active_workspace_id';

@Injectable({
  providedIn: 'root',
})
export class WorkspaceService {
  private _workspaces = new BehaviorSubject<Workspace[]>([]);
  private _activeWorkspace = new BehaviorSubject<Workspace | null>(null);
  private _loading = new BehaviorSubject<boolean>(false);

  /** Observable streams for consumers */
  workspaces$ = this._workspaces.asObservable();
  activeWorkspace$ = this._activeWorkspace.asObservable();
  loading$ = this._loading.asObservable();

  constructor(private http: HttpClient) {}

  // ─── Workspace CRUD ────────────────────────────────────────────

  loadWorkspaces(): void {
    this._loading.next(true);
    this.http
      .get<Workspace[]>(`${API_BASE}/workspaces`)
      .pipe(
        tap((ws) => {
          this._workspaces.next(ws);
          // Auto-select persisted workspace or first in list
          if (!this._activeWorkspace.value && ws.length > 0) {
            const savedId = localStorage.getItem(STORAGE_KEY);
            const match = ws.find((w) => w.id === savedId);
            this.setActiveWorkspace(match || ws[0]);
          }
          this._loading.next(false);
        }),
        catchError((err) => {
          console.warn('Failed to load workspaces:', err);
          this._loading.next(false);
          return of([]);
        })
      )
      .subscribe();
  }

  createWorkspace(body: WorkspaceCreate): Observable<Workspace> {
    return this.http.post<Workspace>(`${API_BASE}/workspaces`, body).pipe(
      tap((ws) => {
        this._workspaces.next([ws, ...this._workspaces.value]);
        this.setActiveWorkspace(ws);
      })
    );
  }

  updateWorkspace(id: string, body: WorkspaceUpdate): Observable<Workspace> {
    return this.http.put<Workspace>(`${API_BASE}/workspaces/${id}`, body).pipe(
      tap((updated) => {
        const list = this._workspaces.value.map((w) =>
          w.id === id ? updated : w
        );
        this._workspaces.next(list);
        if (this._activeWorkspace.value?.id === id) {
          this._activeWorkspace.next(updated);
        }
      })
    );
  }

  deleteWorkspace(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE}/workspaces/${id}`).pipe(
      tap(() => {
        const remaining = this._workspaces.value.filter((w) => w.id !== id);
        this._workspaces.next(remaining);
        if (this._activeWorkspace.value?.id === id) {
          this.setActiveWorkspace(remaining[0] || null);
        }
      })
    );
  }

  // ─── Active Workspace Management ───────────────────────────────

  setActiveWorkspace(ws: Workspace | null): void {
    this._activeWorkspace.next(ws);
    if (ws) {
      localStorage.setItem(STORAGE_KEY, ws.id);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  getActiveWorkspaceId(): string | null {
    return this._activeWorkspace.value?.id || null;
  }

  getActiveWorkspace(): Workspace | null {
    return this._activeWorkspace.value;
  }
}
