import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.GLYPH_BACKEND_PORT ?? '8000'
if (!/^\d{1,5}$/.test(backendPort) || Number(backendPort) < 1 || Number(backendPort) > 65535) {
  throw new Error('GLYPH_BACKEND_PORT must be an integer from 1 to 65535.')
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`
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
