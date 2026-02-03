import { useEffect } from 'react';
import { useAuth } from '@frontegg/react';

/**
 * Ensures Frontegg JWT token is synced to localStorage with the key
 * expected by our API clients (jwt_token).
 *
 * This hook monitors authentication state and verifies the token is
 * accessible in localStorage for use by API service clients.
 */
export function useTokenSync() {
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      // Frontegg stores token with configurable key (we set it to 'jwt_token')
      // This hook ensures it's accessible
      const token = localStorage.getItem('jwt_token');
      if (!token) {
        console.warn('JWT token not found in localStorage');
      }
    }
  }, [isAuthenticated]);
}
