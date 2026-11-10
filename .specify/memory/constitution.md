<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0 (MINOR: Principle II materially expanded)
Modified: Principle II. `source` gains `gate`; the agent timeout is configurable through
`AGENT_TIMEOUT_SECONDS` (default 60 seconds) instead of a fixed 10 seconds.
Rationale: spec 011 (action gate), plan.md Complexity Tracking row 1 and the "In this branch" note.
Flagged for the agent owner's review.
-->

# Conversational AI Constitution

## Core Principles

### I. Contract-First Interfaces

The system has two contracts: frontend ↔ backend (`POST /api/chat`, `GET /api/health`,
`GET /api/chat/{session_id}/history`) and backend ↔ agent (`{"prompt", "session_id"}` in,
`{"reply", "intent"}` out).

- Every contract change MUST be written into a spec before any code changes.
- Existing request and response fields MUST NOT be renamed, removed or retyped without
  a spec that names every affected consumer (frontend, backend, agent) and updates them
  together.
- New fields MUST be additive and nullable or optional, so older clients keep working.
- `README.md` MUST describe the current contracts at all times.

Rationale: three components have different owners (frontend, backend, agent). Silent
contract drift is the main way this system breaks.

### II. Graceful Agent Degradation

The agent is an external dependency that may be absent or unhealthy.

- An agent failure MUST NOT reach the user as an error. Failures include an unset
  `AGENT_URL`, a timeout, a connection error, a non-2xx response and a malformed body.
- On failure the backend MUST return a mock reply with HTTP 200.
- Each fallback MUST be logged as a warning that states the reason.
- Each assistant message MUST record its `source` (`agent`, `mock` or `gate`). Agent replies MUST
  also record `latency_ms`.
- Outbound agent calls MUST have an explicit timeout, configurable through
  `AGENT_TIMEOUT_SECONDS` (default 60 seconds).

Rationale: the frontend and backend have to stay usable and demoable before AgentCore
access exists, and while it is down. Recording the source keeps mock data separable from
real agent data. `gate` marks text written by the action gate in code, which is neither
model output nor a mock.

### III. Persistence Through Alembic Only

- Database schema changes MUST be made only through Alembic migrations in
  `backend/alembic/`. Do not use `create_all` and do not apply manual DDL to shared
  databases.
- Migrations MUST be forward-applicable with `alembic upgrade head`, which runs on
  container start.
- Constraint and index names MUST follow the naming convention in `app/db.py`.
- Writes that belong together MUST be committed in one transaction. For example, a user
  message and its reply are committed together, so a failed request leaves no orphaned
  rows.
- Read endpoints MUST NOT create records as a side effect.

Rationale: reproducible schema across laptops, Docker and future environments, and no
partial conversation state.

### IV. Tests Run Without External Services

- Backend tests MUST run with `pytest` and nothing else: no Postgres, AWS or network.
  They use in-memory SQLite and a mocked agent.
- Each behavior and error case in a spec MUST have at least one automated test. This
  includes status codes, the fallback paths and empty-input handling.
- The test suite MUST pass before a change is merged.
- A bug fix MUST include a test that fails without the fix.

Rationale: every contributor, and CI, can verify a change in seconds, whether or not
they have Docker or cloud access.

### V. POC Simplicity

This is a proof of concept. Prefer the smallest design that meets the spec.

- Use sync SQLAlchemy, plain FastAPI handlers and a single-page React app.
- Each new runtime dependency, service or abstraction layer MUST be justified in the
  feature's `plan.md`.
- Do not add speculative features (auth, multi-tenancy, queues, caching) unless a spec
  asks for them.

Rationale: speed of iteration matters more than generality at this stage. Complexity
has to earn its place.

## Technology & Architecture Constraints

- **Frontend:** React with Vite and TypeScript in `frontend/`. It calls the backend only
  through the relative `/api` path, which the Vite dev server proxies to `:8000`.
- **Backend:** FastAPI on Python 3.12 in `backend/`. It uses SQLAlchemy 2.x (sync) with
  the `psycopg` v3 driver, `httpx` for outbound calls and Alembic for the schema.
- **Database:** PostgreSQL. Migrations MUST work on Postgres 14 (local Homebrew) and
  Postgres 17 (Docker).
- **Agent:** AWS Bedrock AgentCore runtime in `agent/`. The backend reaches it only
  through `AGENT_URL`, which is the full invocation URL.
- **Configuration:** settings come from environment variables (`DATABASE_URL`,
  `AGENT_URL`). `.env.example` MUST list every variable.
- **Secrets:** secrets, credentials and `.env` files MUST NOT be committed.
- **API errors:** invalid client input returns 400 with `{"detail": "<message>"}`, not
  FastAPI's default 422.

## Development Workflow

- Features follow the Spec Kit flow: `/speckit-specify`, then `/speckit-clarify` (optional),
  `/speckit-plan`, `/speckit-tasks` and `/speckit-implement`. Artifacts live under `specs/`.
- `plan.md` MUST include a Constitution Check against Principles I–V. Each violation MUST be
  listed in its Complexity Tracking table with a justification.
- Each change goes through a pull request reviewed by the owner of the component it
  touches. When a contract changes, both sides of the contract MUST review.
- `README.md` MUST stay current with run and test instructions and the API contract. A
  change to either MUST update the README in the same PR.

## Governance

This constitution overrides informal conventions and earlier docs where they conflict.
`docs/backend-spec.md` was written before this constitution and stays valid as the record
of the persistence and history feature.

Amendment process:

1. Propose an amendment by PR to `.specify/memory/constitution.md` (for example with
   `/speckit-constitution`).
2. Record the rationale for the amendment in the PR.
3. Get approval from at least one component owner.

Versioning:

- **MAJOR:** a principle is removed or redefined.
- **MINOR:** a principle or section is added or materially expanded.
- **PATCH:** clarifications and wording.

Compliance: reviewers check each PR against the principles. `/speckit-analyze` flags
constitution conflicts in specs, plans and tasks, and those conflicts MUST be resolved
before implementation.

**Version**: 1.1.0 | **Ratified**: 2026-11-04 | **Last Amended**: 2026-11-10
