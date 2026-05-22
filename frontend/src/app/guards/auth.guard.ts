import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { map, switchMap, of } from 'rxjs';

export const authGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  // First check the auth status from the server
  return authService.checkAuth().pipe(
    switchMap(() => authService.authState$),
    map(authState => {
      if (authState.isAuthenticated) {
        return true;
      } else {
        // Redirect to login page
        router.navigate(['/login']);
        return false;
      }
    })
  );
};

// Made with Bob
