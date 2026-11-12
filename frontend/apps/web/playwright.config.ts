import os from "node:os";

import { defineConfig } from "@playwright/test";

// E2E suite (RTM Phase P4, spec 008/009). Playwright starts THREE servers:
//   - backend: uvicorn on :8000 with a throwaway SQLite file (tables via create_all;
//     Alembic-on-Postgres parity remains gate G4 / docker compose up). OIDC settings
//     enable the sign-in check; keys are fetched from the stand-in below.
//   - stand-in IdP: devtools.stand_in_idp on :8090 (dev-only fake Okta, any user works)
//   - frontend: vite dev on :5173 (proxies /api to :8000; login at /)
// On a dev laptop, already-running servers are reused (reuseExistingServer).

const dbPath = `${os.tmpdir()}/convai-e2e.db`;
// apps/web -> ../../.. is the repo root; backend lives at repo-root/backend.
const backend = process.cwd() + "/../../../backend";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://localhost:5173",
    viewport: { width: 1280, height: 800 },
  },
  webServer: [
    {
      command: `cd '${backend}' && rm -f '${dbPath}' && export DATABASE_URL='sqlite:///${dbPath}' && export OIDC_ISSUER='http://localhost:8090/default' && export OIDC_AUDIENCE='convai-api' && export OIDC_JWKS_URL='http://localhost:8090/default/jwks' && .venv/bin/python -c 'import app.db, app.models; app.models.Base.metadata.create_all(app.db.get_engine())' && exec .venv/bin/uvicorn app.main:app --port 8000`,
      url: "http://localhost:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `cd '${backend}' && exec .venv/bin/python -m devtools.stand_in_idp`,
      port: 8090,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
