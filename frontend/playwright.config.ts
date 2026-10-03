import { defineConfig } from "@playwright/test";
import os from "node:os";
import path from "node:path";
const artifacts =
  process.env.SHAPELOOP_BROWSER_ARTIFACTS ||
  path.join(os.homedir(), ".local/share/shapeloop/browser-tests");
export default defineConfig({
  testDir: "tests",
  timeout: 180000,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  outputDir: artifacts,
  use: {
    baseURL: process.env.SHAPELOOP_URL || "http://127.0.0.1:8765",
    viewport: { width: 1440, height: 960 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      args: [
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
      ],
    },
  },
});
