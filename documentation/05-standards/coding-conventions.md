# 07: Coding Conventions

One rule per language, applied everywhere. When in doubt, copy the pattern of an existing file.

## 1. File and folder naming

| Where | Convention | Example | Why |
|-------|-----------|---------|-----|
| Folders (all) | `kebab-case` | `source-documents/`, `review-workspace/` | Readable, URL-safe, no case problems on Windows |
| Documentation | `kebab-case.md`, numbered | `02-process/build-order.md` | Already used in `documentation/` |
| Python files (backend, ml) | `snake_case.py` | `celery_app.py`, `test_health.py` | **Required by Python:** a file named `celery-app.py` cannot be imported |
| Python packages (folders inside `app/`) | `snake_case` single words | `app/core/`, `app/workers/` | Same import rule; we keep them one word so they are also valid kebab-case |
| Frontend files | `kebab-case.ts` / `kebab-case.tsx` | `api-client.ts`, `error-boundary.tsx`, `home-page.tsx` | Matches shadcn/ui, which generates `dropdown-menu.tsx`; avoids Windows case-sensitivity bugs |
| Frontend tests | next to the file, `.test.ts(x)` | `api-client.test.ts` | Easy to find |
| Migrations | `YYYYMMDD_NNNN_short_description.py` | `20261014_0001_enable_postgis.py` | Sorted by date |

Summary: **kebab-case for folders and frontend files, snake_case for Python files** (Python forces this).

## 2. Names inside code

| Thing | Python | TypeScript |
|-------|--------|-----------|
| Variables, functions | `snake_case` | `camelCase` |
| Classes, types, React components | `PascalCase` | `PascalCase` |
| Constants | `UPPER_SNAKE_CASE` | `UPPER_SNAKE_CASE` |
| Database tables, columns | `snake_case`, plural tables (`findings`) | n/a |
| API URLs | `kebab-case`, plural nouns: `/api/projects/{project_id}/analysis-jobs` | same |
| API JSON fields | `snake_case` (`review_status`) | `snake_case` in API types; no automatic conversion layer |

JSON stays `snake_case` end to end so field names match the database and Python. This avoids a conversion layer and the bugs it causes.

## 3. Standard API error format

Every error response from the backend has this shape:

```json
{
  "error": {
    "code": "not_found",
    "message": "Project not found.",
    "details": null,
    "request_id": "7f3c..."
  }
}
```

- `code`: stable, machine-readable, `snake_case`. The frontend branches on this, never on `message`.
- `message`: safe for users to read. **Never** contains stack traces, SQL, or internal paths.
- `details`: optional extra data (for example the list of invalid fields).
- `request_id`: also sent as the `X-Request-ID` header and written in server logs, so a user-reported error can be found in the logs.

| HTTP | `code` | When |
|------|--------|------|
| 400 | `bad_request` | Malformed request |
| 401 | `not_authenticated` | Not logged in or session expired |
| 403 | `permission_denied` | Logged in but not allowed |
| 404 | `not_found` | Missing **or belongs to another organization** (do not reveal which) |
| 409 | `conflict` | Duplicate, or stale version (optimistic locking) |
| 410 | `link_invalid` | Invitation or reset link expired, used, cancelled, or unknown; `details.reason` says which |
| 413 | `payload_too_large` | Uploaded file is larger than the limit (`MAX_UPLOAD_MB`) (CR-002) |
| 415 | `unsupported_media_type` | Uploaded file is not a readable JPEG or PNG photo (CR-002) |
| 422 | `validation_error` | Input failed validation; `details` lists the fields |
| 429 | `too_many_requests` | Too many failed sign-in attempts; wait and retry |
| 503 | `service_unavailable` | Database or queue unreachable |
| 500 | `internal_error` | Unexpected bug; details only in server logs |

## 4. Error handling rules

**Backend**
- Raise the error classes from `app/core/errors.py` (`NotFoundError`, `PermissionDeniedError`, ...). Do not build error JSON by hand.
- Never use a bare `except:` or `except Exception: pass`. Catch the specific exception, then log it, convert it, or re-raise it.
- Unexpected exceptions are caught once, by the global handler, which logs the full traceback and returns `internal_error`.
- Database sessions roll back automatically when a request fails (`get_db` in `app/core/database.py`).
- Background tasks record failures in PostgreSQL (job status and reason). They do not fail silently.

**Frontend**
- All API calls go through `src/lib/api-client.ts`, which turns error responses into an `ApiError` with `status`, `code`, `message`, and `requestId`.
- Every screen that loads data handles four states: loading, empty, error, and success.
- Errors shown to users use `message`. Include the `request_id` where it helps with support.
- `ErrorBoundary` catches rendering crashes, so one broken component shows a message instead of a blank page.

## 5. Documentation in code

- Every Python module starts with a docstring saying what it is for.
- Public functions and classes have a short docstring: what, inputs, errors raised.
- TypeScript modules and exported functions get a short `/** ... */` comment when the purpose isn't obvious from the name.
- Comments explain **why**, not what the code literally does.

## 6. Configuration and secrets

- All settings come from environment variables, loaded and validated in `app/core/config.py`.
- `.env` is never committed. `.env.example` lists every variable with safe local-only values.
- The app refuses to start with a clear message if a required setting is missing or invalid.

## 7. Quality checks (must pass before a step is done)

| Area | Command |
|------|---------|
| Backend lint | `ruff check .` and `ruff format --check .` |
| Backend types | `mypy app` |
| Backend tests | `pytest` |
| Frontend lint | `npm run lint` |
| Frontend types and build | `npm run build` |
| Frontend tests | `npm run test` |
