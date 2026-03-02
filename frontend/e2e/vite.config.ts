import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  root: resolve(__dir),
  resolve: {
    alias: [
      // Package-level alias — matches import '@clerk/clerk-react'
      { find: '@clerk/clerk-react', replacement: resolve(__dir, 'clerk-mock.ts') },
      // Full-specifier regex aliases — match the entire import path, not just a suffix
      { find: /^.*contexts\/AgencyContext$/, replacement: resolve(__dir, 'context-mocks.ts') },
      { find: /^.*contexts\/DataHealthContext$/, replacement: resolve(__dir, 'context-mocks.ts') },
      { find: /^.*services\/apiUtils$/, replacement: resolve(__dir, 'apiUtils-mock.ts') },
    ],
  },
  server: {
    port: 4174,
  },
});
