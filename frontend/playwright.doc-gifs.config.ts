import { defineConfig, devices } from '@playwright/test';
import baseConfig from './playwright.config';

export default defineConfig({
  ...baseConfig,
  retries: 0,
  workers: 1,
  testMatch: '**/doc-gifs/**/*.spec.ts',
  testIgnore: [],
  use: {
    ...baseConfig.use,
    // Video is managed per-context inside each spec (recordVideo on browser.newContext)
    // so we disable the global recorder here to avoid double-recording.
    video: 'off',
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  outputDir: 'test-results/',
});
