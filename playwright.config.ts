import { defineConfig, devices } from '@playwright/test';
import { defineBddConfig, cucumberReporter } from 'playwright-bdd';

const testDir = defineBddConfig({
  features: 'features/**/*.feature',
  steps: ['steps/**/*.ts', 'support/**/*.ts'],
  outputDir: '.features-gen',
});

export default defineConfig({
  testDir,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false, // shared Mailosaur inbox and demo-app in-memory state - runs stay serial
  workers: 1, // the demo app's clock offset is a single process-wide value (see demo-app/lib/clock.js);
              // concurrent workers hitting the same server would race on it
  retries: 0,
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
    cucumberReporter('html', { outputFile: 'evidence-runs/cucumber-report.html' }),
  ],
  use: {
    baseURL: process.env.SUT_BASE_URL || 'http://localhost:4000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'node demo-app/server.js',
    url: process.env.SUT_BASE_URL || 'http://localhost:4000',
    reuseExistingServer: !process.env.CI,
    timeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
