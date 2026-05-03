import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import electron from 'vite-plugin-electron/simple';
import path from 'node:path';

// Set VITE_WEB_ONLY=1 to run the renderer in a plain browser (for preview/testing)
// without launching the Electron main process.
const webOnly = process.env.VITE_WEB_ONLY === '1';

export default defineConfig({
  plugins: [
    react(),
    ...(webOnly
      ? []
      : [
          electron({
            main: {
              entry: 'electron/main.ts',
            },
            preload: {
              input: 'electron/preload.ts',
              vite: {
                build: {
                  rollupOptions: {
                    output: {
                      format: 'cjs',
                      entryFileNames: '[name].cjs',
                    },
                  },
                },
              },
            },
            renderer: {},
          }),
        ]),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    ...(webOnly
      ? {
          proxy: {
            '/api': {
              target: process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8765',
              changeOrigin: true,
              ws: true,
            },
          },
        }
      : {}),
  },
  clearScreen: false,
});
