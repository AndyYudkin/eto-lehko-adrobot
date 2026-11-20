import { resolve } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

process.loadEnvFile(resolve(import.meta.dirname, '../.env'));

for (const name of ['APP_LOGIN', 'APP_PASSWORD']) {
  if (!process.env[name]) {
    throw new Error(`${name} is missing: set it in the root .env file`);
  }
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
  },
});
