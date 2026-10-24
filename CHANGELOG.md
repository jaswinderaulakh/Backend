# STHIRA Backend — Change Log

## Stage 5 — Rules, repair costing, and PDF report

### Created
- `app/rules/engine.py` — ordered verdict rules loaded from configuration, an inconclusive fallback, and an IS 456 width-limit comparison.
- `app/costing/estimate.py` — placeholder-rate estimate and line-item Bill of Quantities with a cheaper/recommended comparison.
- `app/costing/report.py` — one- or two-page ReportLab inspection PDF with graceful handling of missing images.
- `app/costing/demo.py` — `python -m app.costing.demo` sample report generator.
- `tests/test_stage5_rules_costing.py` — verdict, fallback, boundary, cost, report-creation, and missing-image tests.

### Changed
- `.gitignore` — excludes generated `demo_output/` reports.
- `PROGRESS.md` — marks Stage 5 complete and identifies Stage 6 as next.
- `CHANGELOG.md` — starts this running file-by-file history.

### Verification
- Full suite after Stage 5: `147 passed`.
- Demo generated six sample PDFs; generated PDFs are not source data.
- Protected `app/core/schemas.py` and existing configuration files were not changed.

## Stage 6 — Campus health, map, building detail, and login roles

### Created
- `config/campus.yaml` — configurable starting score, severity deductions, minimum score, and colour bands.
- `config/security.yaml` — configurable failed-login attempt and temporary lockout limits.
- `app/campus/health.py` — health-index calculation using only the latest completed inspection per floor/location, colours, and trends.
- `app/campus/detail.py` — building history and health-trend response.
- `app/campus/seed_demo.py` — idempotent seeder for six fictional Pune-area buildings and sample inspections.
- `app/core/create_admin.py` — local interactive command for creating an administrator; public signup cannot assign admin.
- `tests/test_stage6_campus_roles.py` — formula, latest-location, colour boundary, missing-coordinate, detail, roles, rate-limit, expiry, seed, and migration tests.

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

## Stage 7 — Real pipeline and asynchronous uploads

### Created
- `config/uploads.yaml` — separate 15 MB photo and 10 MB WAV limits.
- `config/image_processing.yaml` — configured tolerance for the grey border after image shadow correction.
- `app/run_one.py` — command-line runner for one local photo and optional WAV, printing measurements, verdict, cost, and PDF path.
- `tests/helpers.py` — generated known-width ArUco crack photos and coin-tap WAVs for tests.
- `tests/test_end_to_end.py` — upload/poll/report/health test plus missing marker, no crack, missing/silent WAV, unexpected failure, and configured upload-limit checks.

### Changed
- `app/pipeline.py` — replaced fake data with the real scale → crack → audio → verdict → estimate → PDF chain; the marker is re-detected in the warped photo and passed as the crack-ignore region.
- `app/core/inspection_service.py` and `app/api/inspections.py` — content-checked uploads, safe generated filenames, configured per-type limits, optional WAV, HTTP 202, processing state, and background-task persistence.
- `app/main.py` — writes full unexpected-error details to ignored `logs/sthira.log`.
- `app/core/config.py` — added loaders for new Stage 7 config files.
- `app/costing/estimate.py` — inconclusive and no-crack outcomes receive no invented repair item or cost.
- `app/crack/measure.py` — narrowly fixed the warp-fill border bug proven by the generated full-pipeline test; CLAHE changes the grey border, so the former exact-colour check misread the border as a crack. The tolerance now comes from the new config file.
- `tests/test_crack.py` — regression test for a one-pixel warp-fill border.
- `tests/test_pipeline.py` — replaced assertions about fake analysis with real pipeline outcomes.
- `tests/conftest.py`, `tests/test_api_inspections.py`, and `tests/test_stage6_campus_roles.py` — adapt existing tests for generated valid photos, HTTP 202/background completion, optional audio, and safe generic error messages.
- `.gitignore` — added `logs/`.
- `PROGRESS.md` — marked Stage 7 complete and Stage 8 next.

### Verification
- Targeted Stage 7/API/Stage 4 tests: `69 passed`.
- Full suite after Stage 7: `164 passed`.
- The generated 12-pixel crack test measured about 2.25 mm against a known 2.00 mm width (about 0.25 mm absolute error). This is a synthetic check, not a real-world accuracy claim.
- Protected `app/core/schemas.py` and all pre-existing config files were left unchanged.

## Stage 8 — Real-data check tools

### Created
- `tools/__init__.py` — package marker for `python -m tools...` commands.
- `tools/batch_check.py` — reads truth-labelled pairs, runs the real pipeline, continues after individual errors, and writes CSV/HTML results.
- `tools/tune_audio.py` — prints per-file tap frequency/class, warns about small labelled groups, plots solid versus hollow samples, and suggests (but never applies) frequency limits.
- `tools/tune_width.py` — reports measured-versus-true widths, signed average bias, and the scale-based smallest trusted width; does not edit config.
- `tools/WHAT_THE_NUMBERS_MEAN.md` — plain-English explanation of synthetic testing and accuracy limitations.
- `tests/real_data/truth.csv` — empty header-only template; no real examples were added.
- `tests/test_stage8_tools.py` — generated fake data tests for batch output/error continuation, audio plot/suggestions, and width bias.

### Changed
- `.gitignore` — keeps generated tool output and future real recordings out of GitHub while retaining the empty truth template.
- `PROGRESS.md` — marks Stage 8 complete and Stage 9 next.

### Verification
- Stage 8 tool tests: `3 passed`.
- All three command-line tools were run on the empty truth template; they reported zero labelled rows and made no claims about real data.
- Full suite after Stage 8: `167 passed`.

## Stage 9 — Deployment preparation (no deployment performed)

### Created
- `Dockerfile` — Python 3.12 slim, OpenCV/Matplotlib runtime libraries, requirements install, and Uvicorn binding to `0.0.0.0:$PORT`.
- `.dockerignore` — excludes `.env`, runtime storage/logs, Python caches, local databases, real recordings, and generated tool results from image builds.
- `render.yaml` — Render Docker web service Blueprint with `/health`, a generated secret, prompted exact CORS origin, and SQLite demo settings.
- `deploy.md` — beginner Render account, GitHub repository `Backend`, root folder, Blueprint, environment, deployment, health/docs testing, and log troubleshooting steps. It warns that Render Free data is temporary, services sleep, and the initial remote-admin path is unresolved.
- `api-for-the-app-developer.md` — all app API routes, login and bearer token, Windows multipart sample, HTTP 202 polling, PDF download, and uncompressed 48 kHz WAV requirement.
- `security-checklist.md` — pre-sharing and real-data safety checks.
- `QUESTIONS.md` — documents the safe first-admin-on-Render decision needed before real use.
- `tests/test_stage9_deploy.py` — tests database-backed `/health`, missing production secret error, wildcard-CORS rejection, and development-origin rejection.

### Changed
- `app/core/settings.py` — environment-backed CORS values and SQLite URL resolution; retained SQLAlchemy URL pass-through.
- `app/main.py` — production startup checks, explicit CORS middleware, and automatic `storage/`/`logs/` creation.
- `.env.example` — added secret placeholder, database/storage paths, exact local CORS origins, and development mode.
- `README.md` — current Windows commands, Python-version test note, local admin command, CLI example, and docs links.
- `PROGRESS.md` — marked Stage 9 complete, with the remote-admin limitation and verification history.
- `CHANGELOG.md` — consolidated the chronological Stage 5–9 file history.

### Verification
- Python 3.12.3 dependency resolution and `pip check`: no broken requirements; no package versions failed, so `requirements.txt` was left unchanged.
- Stage 9 checks: `4 passed`; `render.yaml` parsed and its Docker runtime, Free demo plan, and `/health` were checked; `python -m app.run_one --help` succeeded.
- Full suite after Stage 9: `171 passed`.
- No Docker or Podman binary is installed in the sandbox, so the container image itself could not be built locally. The Docker configuration was not deployed.
- Protected `app/core/schemas.py` and existing configuration files were left unchanged.
