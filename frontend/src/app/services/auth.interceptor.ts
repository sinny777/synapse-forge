import { HttpInterceptorFn, HttpRequest, HttpHandlerFn, HttpEvent, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';
import { Observable, throwError, BehaviorSubject, catchError, filter, switchMap, take } from 'rxjs';

let isRefreshing = false;
const refreshTokenSubject = new BehaviorSubject<any>(null);

export const authInterceptor: HttpInterceptorFn = (req: HttpRequest<any>, next: HttpHandlerFn): Observable<HttpEvent<any>> => {
  const authService = inject(AuthService);

  // Add withCredentials: true to all requests to the backend API
  const authReq = req.clone({
    withCredentials: true
  });

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      // If error is 401 and it's not the refresh endpoint itself
      if (error.status === 401 && !req.url.includes('/api/auth/refresh') && !req.url.includes('/api/auth/login')) {
        return handle401Error(req, next, authService);
      }
      return throwError(() => error);
    })
  );
};

function handle401Error(req: HttpRequest<any>, next: HttpHandlerFn, authService: AuthService) {
  if (!isRefreshing) {
    isRefreshing = true;
    refreshTokenSubject.next(null);

    return authService.refreshToken().pipe(
      switchMap((response: any) => {
        isRefreshing = false;
        // Notify any waiting requests that the token was refreshed
        refreshTokenSubject.next(true);
        // Since we rely on HTTP-only cookies, the browser automatically attaches the new cookies
        return next(req);
      }),
      catchError((err) => {
        isRefreshing = false;
        authService.logoutLocally();
        return throwError(() => err);
      })
    );
  } else {
    // Wait until the token refresh is complete
    return refreshTokenSubject.pipe(
      filter(token => token !== null),
      take(1),
      switchMap(() => {
        return next(req);
      })
    );
  }
}
