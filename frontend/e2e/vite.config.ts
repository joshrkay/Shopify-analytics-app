import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'path';

export default defineConfig({
  plugins: [tailwindcss(), react()],
  root: resolve(__dirname),
  resolve: {
    alias: [
      // Package-level alias — matches import '@clerk/clerk-react'
      { find: '@clerk/clerk-react', replacement: resolve(__dirname, 'clerk-mock.ts') },
      // Full-specifier regex aliases — match the entire import path, not just a suffix
      { find: /^.*contexts\/AgencyContext$/, replacement: resolve(__dirname, 'context-mocks.ts') },
      { find: /^.*contexts\/DataHealthContext$/, replacement: resolve(__dirname, 'context-mocks.ts') },
      { find: /^.*services\/apiUtils$/, replacement: resolve(__dirname, 'apiUtils-mock.ts') },
    ],
  },
  server: {
    port: 4174,
  },
});
