import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendUrl = process.env.BACKEND_URL || 'http://backend:8099';

// https://vitejs.dev/config/
export default defineConfig({
  base: '',
  plugins: [
    vue(),
  ],
  build: {
    outDir: '../dist', // Output to a dist folder in the root
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': backendUrl,
      '/ws': {
        target: backendUrl.replace(/^http/, 'ws'),
        ws: true
      }
    }
  }
})
