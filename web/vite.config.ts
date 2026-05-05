import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:2456',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:2456',
        ws: true,
      },
      '/login': {
        target: 'http://localhost:2456',
        changeOrigin: true,
      },
      '/logout': {
        target: 'http://localhost:2456',
        changeOrigin: true,
      },
      '/callback': {
        target: 'http://localhost:2456',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
