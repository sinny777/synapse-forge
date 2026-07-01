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
    return this.http.get(`${this.apiUrl}/me`, { withCredentials: true }).pipe(
      tap((res: any) => {
        this.authState.next({ isAuthenticated: true, user: res });
      }),
      catchError(() => {
        this.authState.next({ isAuthenticated: false, user: null });
        return of(null);
      })
    );
  }

  loginWithCredentials(email: string, password: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/login/demo`, { email, password }, { withCredentials: true }).pipe(
      tap(() => {
        this.checkAuth().subscribe();
      })
    );
  }

  getProviders(): Observable<{ google: boolean; github: boolean }> {
    return this.http.get<{ google: boolean; github: boolean }>(`${this.apiUrl}/providers`);
  }

  logout(): Observable<any> {
    return this.http.post(`${this.apiUrl}/logout`, {}, { withCredentials: true }).pipe(
      tap(() => {
        this.clearLocalSession();
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

  /** Clear all client-side session state (auth state, localStorage, sessionStorage). */
  clearLocalSession(): void {
    this.authState.next({ isAuthenticated: false, user: null });
    localStorage.clear();
    sessionStorage.clear();
  }
}
