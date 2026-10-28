# GeoInfraLens AI

AI GIS Road and Sidewalk Assessment Platform: turns geotagged photos into **candidate** defect
findings that qualified reviewers verify before they are used for inspection planning.

Project documentation: [`documentation/`](documentation/README.md). Start with `CURRENT_PHASE.md`.

## Project layout

```
backend/        FastAPI API + Celery workers (Python)
frontend/       React + Vite + TypeScript app
ml/             model training and evaluation (separate dependencies)
scripts/        helper scripts
documentation/  requirements, design, phases, conventions
```

## Prerequisites (Windows)

1. **Docker Desktop** (runs the database, queue, API, and worker): https://www.docker.com/products/docker-desktop/
2. **Node.js 22 LTS** (runs the frontend): https://nodejs.org/
3. **Git**: https://git-scm.com/

Python does **not** need to be installed on Windows; the backend runs inside Docker.

## First-time setup

From the project folder, in PowerShell:

```powershell
git init                          # once
copy .env.example .env            # then edit .env if you want different local passwords
docker compose up --build         # starts db, queue, api, worker; applies migrations

# in a second terminal
cd frontend
npm install
npm run dev
```

Create your organization and first admin (asks for a password twice):

```powershell
docker compose exec api python -m app.cli create-organization --name "Your Organization" --admin-email you@example.com --admin-name "Your Name"
```

Open http://localhost:5173 and sign in. The Overview page shows **System status** (database `ok`, queue `ok`).
API docs (development only): http://localhost:8000/api/docs

## Everyday commands

| Task | Command |
|------|---------|
| Start backend services | `docker compose up` |
| Stop backend services | `docker compose down` |
| Start frontend | `cd frontend` then `npm run dev` |
| Backend tests | `docker compose exec api pytest` |
| Backend lint + format check | `docker compose exec api ruff check .` and `docker compose exec api ruff format --check .` |
| Backend type check | `docker compose exec api mypy app` |
| New migration | `docker compose exec api alembic revision --autogenerate --rev-id 000N -m "short description"` (N = next number) |
| Apply migrations | `docker compose exec api alembic upgrade head` |
| Frontend tests | `npm run test` (in `frontend/`) |
| Frontend lint | `npm run lint` |
| Frontend type check + build | `npm run build` |
| Restart worker after task changes | `docker compose restart worker` |
| Create an organization + first admin | `docker compose exec api python -m app.cli create-organization --name "…" --admin-email … --admin-name "…"` |
| Make an existing account a platform admin (add `--remove` to undo) | `docker compose exec api python -m app.cli make-platform-admin --email …` |

## AI model (trial)

The app analyses photos with the **TEST DETECTOR** (made-up results) unless you switch on the trained **trial model** `frcnn-rdd2022-0.1`. That model did **not** pass its final accuracy test (it misses most potholes on unseen roads), so everything it finds is labelled **"TRIAL MODEL: accuracy not approved"** and must be checked by a reviewer (decision CR-003).

**Switch it on**
1. Copy `best.pt` from Google Drive (`GeoInfraLens/runs/frcnn-rdd2022-0.1/`) to `ml/models/` and rename it to `frcnn-rdd2022-0.1.pt`. The app accepts only the exact tested file (it checks the file's fingerprint).
2. In `.env` set `ANALYSIS_MODEL_VERSION=frcnn-rdd2022-0.1`
3. `docker compose up --build` the first time (downloads PyTorch, about 10-15 minutes), afterwards `docker compose restart api worker`
4. In a project: **Photos → Check new photos**. Photos already checked by the test detector are checked again by the trial model; earlier results stay, labelled with the model that made them.

**Switch it off:** set `ANALYSIS_MODEL_VERSION=stand-in-0.1` in `.env`, then `docker compose restart api worker`. Nothing is deleted.

Notes: about 3-4 seconds per photo on a normal PC; one photo at a time; the worker needs about 2 GB of memory (Docker Desktop → Settings → Resources: give Docker at least 6 GB). If the model file is missing or wrong, "Check new photos" says so and nothing is queued.

## Troubleshooting

- **`Set POSTGRES_USER in .env`**: you have not created `.env`. Run `copy .env.example .env`.
- **Port 5432/6379/8000 already in use**: another PostgreSQL/Redis/app is running. Stop it, or change the left-hand port in `docker-compose.yml`.
- **System status shows "Cannot reach the server"**: the backend is not running. Start it with `docker compose up`.
- **System status shows database `unavailable`**: check `docker compose logs db`.
- **Database tests are skipped**: add the `TEST_DATABASE_URL` line from `.env.example` to your `.env`, then run `docker compose up -d` again.
- **Signed out immediately after signing in**: the address in your browser must match `PUBLIC_APP_URL` (default `http://localhost:5173`).
- **Map shows a plain grey background with "Street map could not load"**: the street-map tiles could not be reached (offline or blocked network). Drawing areas and picking points still work. To use another map provider, set `VITE_MAP_STYLE_URL` in `frontend/.env` and restart `npm run dev`.
- **Frontend error about `terra-draw` or a missing package after an update**: run `npm install` in the `frontend` folder, then `npm run dev` again.
- **"Something went wrong on our side" right after an update** (for example when signing in): the backend picked up new code but the database was not updated yet. Database updates run only when the backend starts. Stop it (Ctrl + C) and run `docker compose up --build`, or run `docker compose exec api alembic upgrade head`.
- **After every update from a new phase, restart both parts:** backend with `docker compose up --build`, frontend with `npm install` then `npm run dev` (stop `npm run dev` first; on Windows `npm install` can fail while the app is running).
- Errors shown in the app include a **Reference** ID. Search the API logs for it: `docker compose logs api | findstr <id>`.
