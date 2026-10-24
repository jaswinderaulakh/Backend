# STHIRA Backend

FastAPI and SQLite backend for the STHIRA campus structural-health monitoring app. It processes a marked wall photo and an optional coin-tap recording, then saves an inspection result and PDF report.

## Run on Windows

Open PowerShell in the top-level `Backend` project folder. If you have not created a local settings file yet, copy the safe template:

```powershell
Copy-Item .env.example .env
```

Then start the server:

```powershell
py -3.14 -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` in a browser. Stop the server with **Ctrl+C**. The app creates its SQLite database, `storage/`, and `logs/` automatically. Keep `.env` private; it is ignored by Git.

Run the complete tests from the project folder:

```powershell
py -3.14 -m pytest -q
```

The automated suite in this work was run with Python 3.12.3, which is also the Docker/Render version. Python 3.14 was not available in the build environment, so run the command above on your laptop to confirm your specific Python 3.14 package installation.

## Local admin account

Public registration creates an inspector account only. To create an admin in the local SQLite database, stop the server and run:

```powershell
py -3.14 -m app.core.create_admin
```

This command changes only the database selected by your local `.env`. It does not create an admin account on a separately deployed Render service.

## Run one photo directly

```powershell
py -3.14 -m app.run_one photo.jpg tap.wav --exposure moderate
```

Replace the file names with your own marked JPEG/PNG and optional WAV, and select `mild`, `moderate`, or `severe`. The command prints measurements, verdict, estimate, and PDF location.

## Stage 9 files

- [Render deployment guide](deploy.md) — setup steps, environment values, health check, logs, and free-tier limitations.
- [Mobile API guide](api-for-the-app-developer.md) — authentication, upload, polling, and PDF download.
- [Security checklist](security-checklist.md) — items to check before sharing a link.
- [Plain-English accuracy note](tools/WHAT_THE_NUMBERS_MEAN.md) — what synthetic tests do and do not establish.
