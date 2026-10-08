import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: 5173,
      // Same-origin proxy in dev so the httpOnly refresh cookie just works.
      proxy: {
        '/api': {
          target: env.VITE_DEV_API_PROXY || 'http://127.0.0.1:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
    preview: { port: 4173 },
    build: {
      target: 'es2022',
      sourcemap: 'hidden',
    },
  };
});
