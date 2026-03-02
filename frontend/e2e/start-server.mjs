/**
 * E2E Test Harness Server — Starts Vite programmatically.
 *
 * Bypasses Vite's config-file-through-esbuild loading entirely,
 * which avoids "Could not resolve" errors on some Node/esbuild combos.
 *
 * Usage:
 *   node e2e/start-server.mjs
 */
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dir = dirname(fileURLToPath(import.meta.url));

const server = await createServer({
  configFile: false,
  plugins: [react()],
  root: resolve(__dir),
  resolve: {
    alias: [
      { find: '@clerk/clerk-react', replacement: resolve(__dir, 'clerk-mock.ts') },
      { find: /^.*contexts\/AgencyContext$/, replacement: resolve(__dir, 'context-mocks.ts') },
      { find: /^.*contexts\/DataHealthContext$/, replacement: resolve(__dir, 'context-mocks.ts') },
      { find: /^.*services\/apiUtils$/, replacement: resolve(__dir, 'apiUtils-mock.ts') },
    ],
  },
  server: {
    port: 4174,
  },
});

await server.listen();
server.printUrls();
