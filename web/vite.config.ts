/* global process */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: `npm run dev` proxies /api to the FastAPI server on :8000
// (override with SHADOWBOX_API=http://host:port npm run dev).
// Prod: `npm run build` writes web/dist, which FastAPI serves at "/".
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.SHADOWBOX_API || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
