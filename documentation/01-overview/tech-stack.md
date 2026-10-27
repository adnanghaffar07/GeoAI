# 02: Technology Stack

Constraints: one developer, free and open-source software. Choose the simplest option that is still secure and production-suitable.

## 1. Frontend

| Technology | Why we use it |
|-----------|---------------|
| React + Vite + TypeScript | Component-based responsive app. Vite gives fast development; TypeScript catches type errors early. |
| Tailwind CSS + shadcn/ui | Consistent, accessible forms, navigation, and dialogs without designing from scratch. |
| React Router | Page navigation (overview, projects, map, review, reports, settings). |
| TanStack Query | API calls, caching, loading and error states, and polling job status. |
| React Hook Form + Zod | Project and review forms with clear validation messages. |
| MapLibre GL JS | Interactive map, finding pins, and map/list selection kept in sync. |
| Terra Draw | Drawing the survey boundary. GeoJSON file upload is also supported. |
| Base map tiles | OpenFreeMap or self-hosted Protomaps. **Check terms before the pilot.** Do not use the public OpenStreetMap tile servers. |

## 2. Backend

| Technology | Why we use it |
|-----------|---------------|
| Python + FastAPI | REST API. Same language as the AI code. |
| Pydantic | Validates request data and shapes responses. |
| SQLAlchemy (**sync**) | Database models and queries, shared by the API and the workers. Sync is chosen because Celery is sync and async adds complexity with no pilot-scale benefit. |
| GeoAlchemy2 | PostGIS geometry and geography columns and spatial functions in SQLAlchemy. |
| Alembic | Versioned, reviewable database migrations. |
| Session-cookie auth | Random session token stored in a `sessions` table and sent as an `httpOnly`, `Secure`, `SameSite=Lax` cookie. Deleting the row ends access **immediately**, which meets the "removed users lose access" requirement. |
| pwdlib (Argon2) | Password hashing. |
| Custom RBAC | Organization and project role checks in **one central permission dependency** used by every route. |
| Celery + Valkey | Background jobs (quality checks, inference, reports) with retries. **PostgreSQL is the source of truth for job state.** Celery's result backend is not used for anything the user sees. |
| Pillow + OpenCV | EXIF and GPS reading, image validation, previews, blur and darkness checks, preprocessing. |
| WeasyPrint | PDF reports rendered from HTML templates. |

## 3. Data

| Technology | Why we use it |
|-----------|---------------|
| PostgreSQL | Organizations, users, projects, images, findings, reviews, jobs, inspections, audit events. |
| PostGIS | Project boundaries, observation points, distance and containment queries. SRID 4326 for storage; geography type or an appropriate projected CRS for distances in meters. |
| Private disk storage | Original photos, previews, and exports on a private volume behind `storage.py` (`save` / `open` / `delete`). Files are never served directly, only through the API after a permission check. We can switch to S3-compatible storage later by changing only that module. |

## 4. AI / ML (separate `ml/` folder with its own dependencies)

| Technology | Why we use it |
|-----------|---------------|
| PyTorch + torchvision Faster R-CNN | Baseline object detector. BSD license; no proprietary API. |
| NumPy, pandas | Dataset and annotation work. |
| TorchMetrics, scikit-learn | Per-class precision and recall on held-out test images. |
| Label Studio | Labeling tool, set up only once authorized images exist. |
| Kaggle Notebooks / Colab free tier | Free GPU for training (with weekly limits). |
| RDD2022 (optional) | Public road-damage dataset for early experiments. **Verify its license and its fit to partner roads.** |

The platform is built against a **stand-in detector** that follows the model output contract. The real model is plugged in only after it has been evaluated.

## 5. Tooling

- Docker Compose: PostGIS, Valkey, API, worker. The frontend runs outside Docker with `npm run dev` (faster file watching on Windows); Vite forwards `/api` to the API, so no CORS setup is needed.
- Backend: pytest, Ruff, mypy (strict)
- Frontend: Vitest + Testing Library, **oxlint** (the linter that ships with the current official Vite template; it replaces ESLint with the same React hooks rules and no extra configuration)
- Git for version control

Installed at setup (2026-10-14): FastAPI 0.143, SQLAlchemy 2.1, Alembic 1.20, GeoAlchemy2 0.20, psycopg 3.3, Celery 5.6, Pillow 12, OpenCV 4.14, React 19, Vite 8, TypeScript 6, Tailwind CSS 4, React Router 8, TanStack Query 5, React Hook Form 7, Zod 4, MapLibre GL 6. Python 3.13 in Docker. Exact frontend versions are locked in `package-lock.json`.

Added later, when first needed: Recharts 3.10.1 (Overview dashboard charts, MIT licence; loaded only on the Overview pages), WeasyPrint (P7, needs extra system libraries in Docker), Terra Draw (P4), shadcn/ui components (added one at a time with `npx shadcn add <name>`; `components.json` is already configured).

## 6. Deferred (not in V1 unless a real need appears)

| Item | Reason |
|------|--------|
| SeaweedFS / object storage | Local private storage is enough at pilot volume. |
| RetinaNet comparison | Evaluate one baseline first. |
| CVAT | Heavy to self-host. Label Studio is lighter. |

## 7. Rejected options and why

| Option | Why not |
|--------|---------|
| JWT login tokens | A token stays valid after a user is removed. Revoking it needs a blocklist, which removes JWT's benefit. |
| Async SQLAlchemy | Extra complexity. Workers are sync anyway. |
| Ultralytics YOLO | AGPL-3.0 license can force open-sourcing the platform or buying a commercial license. |
| Public OSM tile servers | Their usage policy forbids heavy app usage. |
| Celery result backend for job status | Status must live in PostgreSQL so retries and idempotency are reliable. |

## 8. Licensing and cost notes

- OpenStreetMap data is ODbL: it requires attribution and has share-alike obligations for derived databases.
- Check the license of every pretrained weight, dataset, and map layer before commercial use. Record the source, date, and license for each layer.
- The software is free. **Pilot hosting is not:** plan for a small VPS or a verified free tier that meets the partner's privacy and retention rules.

## 9. Proposed repository structure

```
GeoInfraLens AI/
  documentation/          project docs (this folder)
  frontend/               React app
  backend/
    app/
      api/                route modules
      core/               config, security, permissions
      models/             SQLAlchemy models
      schemas/            Pydantic schemas
      services/           business logic
      workers/            Celery tasks
      storage.py          file storage module
    alembic/              migrations
    tests/
  ml/                     training, evaluation, model output contract
  docker-compose.yml
  .env.example            no real secrets in git
```
