import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    host: '127.0.0.1',
    port: 4174,
    strictPort: true,
    watch: { ignored: ['**/src-tauri/**'] },
  },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'] },
});
