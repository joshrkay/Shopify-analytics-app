import React from 'react';
import ReactDOM from 'react-dom/client';
import { FronteggProvider } from '@frontegg/react';
import App from './App';

const fronteggConfig = {
  contextOptions: {
    baseUrl: import.meta.env.VITE_FRONTEGG_BASE_URL,
    clientId: import.meta.env.VITE_FRONTEGG_CLIENT_ID,
    tokenStorageKey: 'jwt_token',
  },
  hostedLoginBox: false, // Embedded login - no external redirect
  authOptions: {
    keepSessionAlive: true,
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <FronteggProvider {...fronteggConfig}>
      <App />
    </FronteggProvider>
  </React.StrictMode>
);
