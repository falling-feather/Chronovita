import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const staticPreview = mode === 'pages' || env.VITE_STATIC_PREVIEW === 'true';
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';
  const proxy = {
    '/api': apiTarget,
    '/ws': {
      target: apiTarget.replace(/^http/, 'ws'),
      ws: true,
    },
  };

  return {
    base: staticPreview ? './' : '/',
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy,
    },
    preview: {
      port: 5173,
      strictPort: true,
      proxy,
    },
    test: {
      include: ['src/**/*.test.{ts,tsx}'],
    },
  };
});
