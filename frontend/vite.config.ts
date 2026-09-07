import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// dev: backend 默认 :8765, 前端默认 :5173 —— /ws 由 vite 代理转发。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8765',
        ws: true,
      },
    },
  },
});
