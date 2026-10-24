
## Stage 6 — Campus health, map, building detail, and login roles

### Created
- `config/campus.yaml` — Configurable starting score, severity deductions, minimum score, and colour bands.
- `config/security.yaml` — Configurable failed-login attempt and temporary lockout limits.
- `app/campus/health.py` — Health-index calculation using only the latest completed inspection per floor/location, colours, and trends.
- `app/campus/detail.py` — Building history and health-trend response.
- `app/campus/seed_demo.py` — Idempotent seeder for six fictional Pune-area buildings and sample inspections.
- `app/core/create_admin.py` — Local interactive command for creating an administrator; public signup cannot assign admin.
- `tests/test_stage6_campus_roles.py` — Formula, latest-location, colour boundary, missing-coordinate, detail, roles, rate-limit, expiry, seed, and migration tests.

### Changed
- `app/core/config.py` loads the new campus and security settings.
- `app/db/models.py`, `app/db/session.py`, and `app/db/repository.py` persist roles, allow unknown coordinates, and upgrade existing SQLite databases.
- `app/core/accounts.py`, `app/api/auth.py`, `app/api/deps.py`, and `app/core/errors.py` add inspector defaults, local-admin roles, configurable throttling, and clear 403/429 errors.
- `app/core/api_schemas.py` exposes user roles and optional map coordinates.
- `app/core/inspection_service.py` and `app/api/inspections.py` restrict inspectors to their own inspection records while admins can access all.
- `app/api/buildings.py` makes building creation admin-only and adds `GET /buildings/{id}` with history and trend.
- `app/campus/geojson.py` returns the requested health-coloured map summaries and lists buildings without coordinates.
- `tests/conftest.py` and `tests/test_api_campus.py` adapt existing tests to the admin fixture and new health formula.
- `PROGRESS.md` marks Stage 6 complete and Stage 7 next.

### Verification
- Full suite after Stage 6: `160 passed`.
- Stage 6 demo seeder test confirms six buildings and twelve fake inspections, without duplicating them on a second run.
- The protected `app/core/schemas.py` and existing files in `config/` were not modified; Stage 6 settings use new config files.
