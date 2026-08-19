import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../../packages/veloctra-api/veloctra_api/ui/dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-xyflow': ['@xyflow/react'],
          'vendor-lucide': ['lucide-react'],
        },
      },
    },
  },

  server: {
    port: 3000,
    proxy: {
      '/auth': 'http://localhost:8000',
      '/configs': 'http://localhost:8000',
      '/pipelines': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
      '/reports': 'http://localhost:8000',
      '/data': 'http://localhost:8000',
      '/rbac': 'http://localhost:8000',
      '/projects': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
