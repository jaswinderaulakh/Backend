# STHIRA security checklist before sharing the link

## Before sharing a test link

- [ ] I confirmed the link is only for a disposable demo. The Render Free plan can lose the database, photos, recordings, and reports when it sleeps, restarts, or redeploys.
- [ ] I confirmed a safe way to create the first **admin on the same database as the deployed service**. Running the admin command on my laptop does not create a remote account.
- [ ] The deployed app has `DEBUG=false`.
- [ ] Render generated a private `SECRET_KEY`, or I entered a private random value of at least 32 characters. It is not the value from `.env.example`.
- [ ] `CORS_ALLOWED_ORIGINS` contains only the exact website origin that needs browser access. It is not `*`.
- [ ] The API link uses HTTPS. I have not put a password or bearer token in a URL, screenshot, shared document, or support message.
- [ ] I tested registration as an inspector, login, the role restrictions, `/health`, and `/docs`. I did not share an admin password with inspectors.
- [ ] I know where the Render service logs are, and I will not paste logs publicly without checking them for private information.

## Before using campus data

- [ ] The SQLite database and uploaded files are stored durably, not only on a temporary Free service filesystem.
- [ ] I have a backup and restore plan for the database, original photos, audio files, and PDF reports.
- [ ] Campus photos and recordings are collected and retained only with the required permissions. Test data contains no student names, faces, or other unnecessary personal details.
- [ ] I replaced placeholder CPWD rates with verified rates before anyone relies on a repair estimate.
- [ ] A qualified structural engineer reviews concerning damage. The app's verdict and health score are screening summaries, not a safety certification.

## Never commit or share

- [ ] I checked that `.env`, databases, `storage/`, `logs/`, real recordings, and real campus photos are not in the GitHub repository.
- [ ] I checked that `.env.example` still contains only placeholders.
- [ ] I understand that a bearer token works like a temporary password. If one is exposed, I will revoke/replace it and notify the affected user.
