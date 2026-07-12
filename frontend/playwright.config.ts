import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
  },
  webServer: [
    {
      command: 'cd ../backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      port: 8000,
      timeout: 10000,
      reuseExistingServer: true,
    },
    {
      command: 'npx vite --host',
      port: 5173,
      timeout: 10000,
      reuseExistingServer: true,
    },
  ],
})
