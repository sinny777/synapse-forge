import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, catchError, of, tap } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = 'http://localhost:8000/api/auth';
  
  private authState = new BehaviorSubject<{isAuthenticated: boolean, user: any}>({
    isAuthenticated: false,
    user: null
  });

  public authState$ = this.authState.asObservable();

  constructor(private http: HttpClient) {}

  checkAuth(): Observable<any> {
    // TODO: Add dev mode header for automatic authentication
    const headers = { 'X-Dev-Mode': 'true' };
    return this.http.get(`${this.apiUrl}/me`, { withCredentials: true, headers }).pipe(
      tap((res: any) => {
        this.authState.next({ isAuthenticated: true, user: res });
      }),
      catchError((err) => {
        this.authState.next({ isAuthenticated: false, user: null });
        return of(null);
      })
    );
  }

  logout() {
    return this.http.post(`${this.apiUrl}/logout`, {}, { withCredentials: true }).pipe(
      tap(() => {
        this.logoutLocally();
      })
    );
  }

  refreshToken(): Observable<any> {
    return this.http.post(`${this.apiUrl}/refresh`, {}, { withCredentials: true }).pipe(
      tap(() => {
        this.checkAuth().subscribe();
      })
    );
  }

  logoutLocally() {
    this.authState.next({ isAuthenticated: false, user: null });
  }
}
