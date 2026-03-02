import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'path';

export default defineConfig({
  plugins: [tailwindcss(), react()],
  root: resolve(__dirname),
  resolve: {
    alias: {
      '@clerk/clerk-react': resolve(__dirname, 'clerk-mock.ts'),
    },
  },
  server: {
    port: 4174,
  },
});
