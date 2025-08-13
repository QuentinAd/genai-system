import react from '@vitejs/plugin-react'
import { defineConfig, configDefaults } from 'vitest/config'

const target = process.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/chat': target,
      '/health': target,
    },
  },
  test: {
    environment: 'jsdom',
    css: true,
    exclude: [...configDefaults.exclude, 'e2e/**'],
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
  },
})
