// frontend/playwright.integration.config.ts
//
// Runs the FULL integration test suite:
//   Playwright → Vite (port 3001) → Backend (FastAPI, port 8099) → Mosquitto (port 18883) → Simulator
//
// Prerequisites (handled by globalSetup):
//   - Mosquitto installed (e.g. `brew install mosquitto`)
//   - Python venv at ../.venv with project deps installed
//
// Run with:
//   npm run test:e2e:integration

import { defineConfig, devices } from '@playwright/test';
import { join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  testDir: './e2e/integration',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  // Integration tests are slower — give them more retries on CI
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report-integration' }], ['line']],

  use: {
    baseURL: 'http://localhost:3001',
    trace: 'on-first-retry',
    // Integration tests touch real async infra — be generous with timeouts
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },

  timeout: 60_000,

  globalSetup: join(__dirname, 'e2e/integration/global.setup.ts'),
  globalTeardown: join(__dirname, 'e2e/integration/global.teardown.ts'),

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Start Vite proxying to our test backend on port 8099
  webServer: {
    command: 'BACKEND_URL=http://localhost:8099 npx vite --port 3001 --host',
    port: 3001,
    reuseExistingServer: false,
    timeout: 60_000,
    // stdout: 'pipe', // uncomment to see vite logs
  },
});
