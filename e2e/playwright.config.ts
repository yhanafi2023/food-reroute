import { defineConfig } from "@playwright/test";

// Starts the backend (demo mode, offline routing) and the built frontend unless they are already running.
export default defineConfig({
  testDir: ".",
  testIgnore: process.env.SCREENSHOTS ? [] : ["screenshots.spec.ts"],
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3000", viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure" },
  webServer: [
    {
      command: "cd ../backend && DEMO_MODE=true .venv/bin/uvicorn app.main:app --port 8000",
      url: "http://localhost:8000/",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "cd ../frontend && npm run build && npm run start",
      url: "http://localhost:3000/",
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
