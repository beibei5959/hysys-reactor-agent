import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 40_000,
  use: {
    baseURL: process.env.WEB_TEST_URL ?? "http://127.0.0.1:8765",
    channel: process.env.WEB_TEST_BROWSER ?? "chrome",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
