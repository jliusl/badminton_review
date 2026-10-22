import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 6_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "edge",
      use: { channel: "msedge", viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "chrome",
      use: { channel: "chrome", viewport: { width: 1440, height: 1000 } },
    },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
