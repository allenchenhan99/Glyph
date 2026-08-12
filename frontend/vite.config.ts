import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: false,
    coverage: {
      provider: 'v8',
      reporter: ['text'],
      thresholds: {
        statements: 60,
        branches: 40,
        functions: 60,
        lines: 60
      }
    }
  }
})
