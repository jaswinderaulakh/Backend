# STHIRA Backend Change Log

## Stage 5 — Rules, repair cost, and PDF report

### Created
- `app/rules/engine.py` — Config-driven ordered verdict evaluation, fallback verdict, and IS 456 width-limit explanation.
- `app/costing/estimate.py` — CPWD-rate BoQ estimates, documented quantity assumptions, and cheaper-versus-recommended comparison.
- `app/costing/report.py` — ReportLab inspection PDF with optional images and placeholder-rate warning.
- `app/costing/demo.py` — `python -m app.costing.demo` sample PDF generator for all configured verdicts and fallback.
- `tests/test_stage5_rules_costing.py` — Stage 5 rule, boundary, exposure, estimate, and PDF tests.
- `CHANGELOG.md` — Running record of project file changes.

### Changed
- `.gitignore` — Ignore generated `demo_output/` files.
- `PROGRESS.md` — Mark Stage 4 and Stage 5 complete and set Stage 6 as next.

No existing Stage 1–4 implementation modules, `app/core/schemas.py`, or existing files in `config/` were changed.

### Verification
- Full test suite: `147 passed`.
- `python -m app.costing.demo`: generated six valid one-page PDFs (five configured rules and the inconclusive fallback) under ignored `demo_output/`.
