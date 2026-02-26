import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: '../static/react',
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'index.html'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/profile': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/hr': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/statements': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/ai-agent': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/logout': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/approvals': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/marketing': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/dms': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/notifications': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/bilant': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
})
