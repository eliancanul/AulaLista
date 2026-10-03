import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: { manifest: true },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api/v1': { target: 'http://127.0.0.1:8001', changeOrigin: false },
      '/cms': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/tutor': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
});
