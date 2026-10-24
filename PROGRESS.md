# STHIRA Backend: Progress

- [x] Stage 0: Planning and shared files
- [x] Stage 1: API skeleton
- [x] Stage 2: Audio analysis
- [x] Stage 3: ArUco marker and scale
- [x] Stage 4: Crack measurement
- [x] Stage 5: Rules, repair costing, and PDF report
- [x] Stage 6: Campus map, health index, login roles
- [x] Stage 7: Real pipeline and asynchronous uploads
- [x] Stage 8: Real-data check and tuning tools
- [x] Stage 9: Deployment preparation (not deployed)

## Stage 7 notes

`POST /inspections` validates file contents and configured size limits, saves uploads under safe generated names, and returns HTTP 202 with status `processing`. Analysis runs in a FastAPI background task; poll `GET /inspections/{id}` until status changes. The protected response schema uses `completed` to mean finished successfully (rather than the word `done`). The real pipeline runs scale detection, ignores the marker region, measures the crack, analyses audio, decides a verdict, estimates cost, and creates a PDF. Missing/silent audio yields an uncertain tap result; missing markers and unexpected errors are saved with user-friendly messages.

A generated end-to-end test exposed that CLAHE slightly changes the perspective-warp border colour, causing Stage 4 to label the border as a long crack. Stage 4's fill detection was narrowly corrected using a tolerance in new `config/image_processing.yaml`; a regression test proves the issue and fix. Upload limits are in new `config/uploads.yaml` (15 MB photo, 10 MB WAV). The protected `app/core/schemas.py` and pre-existing files in `config/` were not changed.

## Stage 8 notes

`tools/batch_check.py`, `tools/tune_audio.py`, and `tools/tune_width.py` read only rows provided in `tests/real_data/truth.csv`. `tools/WHAT_THE_NUMBERS_MEAN.md` explains the limits of synthetic testing and the evidence still needed. The supplied truth CSV is only a header template; no campus data or real accuracy results were invented. Generated results are excluded from GitHub.

## Stage 9 notes

Added a Python 3.12 slim Docker setup, Render Blueprint, production environment checks, exact-origin CORS, storage/log directory creation, beginner deployment steps, mobile API guide, and security checklist. No deployment was performed. The dependency set resolved on Python 3.12.3 with `pip check` reporting no broken requirements. No dependency versions failed, so `requirements.txt` was not changed. The sandbox has no Docker or Podman executable, so an actual image build could not be run here.

`QUESTIONS.md` records the unresolved safe way to create the first admin on a remote Render database. Running the existing setup command on a laptop changes only its local SQLite database; Render Free has no shell and its local files are temporary. The included free Render Blueprint is therefore for a disposable demo, not real campus data.

Stage 7 full-suite verification: **164 passed**. Stage 8 full-suite verification: **167 passed**. Stage 9 full-suite verification: **171 passed**.

## Project notes

CPWD repair rates remain placeholders and should be replaced with verified project rates before using estimates for budgeting. No real campus photos or tap recordings have been supplied, so quality claims are limited to generated test images and sounds. Keep `.env` private; only `.env.example` belongs in GitHub.
