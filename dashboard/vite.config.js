import { defineConfig } from 'vite';
export default defineConfig({
  server: { host: '127.0.0.1', port: 8101, strictPort: true, proxy: { '/api': process.env.QUERY_URL || 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom', restoreMocks: true, include: ['tests/**/*.test.jsx'] },
});
