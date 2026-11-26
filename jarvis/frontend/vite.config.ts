import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import fs from 'node:fs'

// One id per build, baked into the bundle (`__APP_BUILD__`) AND written to
// `version.json` so a running tab can poll the latter and compare — see
// src/lib/versionCheck.ts + the stale-tab "new version" banner. Both come from
// this single constant, so the served file and the baked value can never drift.
const BUILD_ID = String(Date.now())

export default defineConfig({
  define: {
    __APP_BUILD__: JSON.stringify(BUILD_ID),
  },
  plugins: [
    react(),
    tailwindcss(),
    {
      // Emit version.json into the build output so /version.json can serve it.
      // closeBundle runs after emptyOutDir + the bundle write, so the file survives.
      name: 'emit-version-json',
      apply: 'build',
      closeBundle() {
        const out = path.resolve(__dirname, '../static/react/version.json')
        fs.writeFileSync(out, JSON.stringify({ build: BUILD_ID }))
      },
    },
  ],
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
      '/biostar': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/carbackground': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/mobile-checkin': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/efactura': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/facturare': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/settings': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/connectors': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/forms': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/controlling': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/connecteam': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/vouchers': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/sincron': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
})
