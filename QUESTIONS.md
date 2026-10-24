# Questions before real Render use

## How should the first remote admin account be created?

Stage 6 deliberately creates the first admin with the local command `python -m app.core.create_admin`; public signup cannot grant an admin role. That command writes to the database selected by the computer where it runs. On Render Free, the SQLite file is private to the running service, and Free services do not provide a shell or one-off command. Therefore running the command on the Windows laptop does **not** create the Render admin. The included free Blueprint is a disposable demo configuration, not ready for real campus inspections.

Before real use, choose one safe option: run the local setup command inside a paid Render service that has durable storage; use a managed database with a secure connection and run the command against that same database; or design a deliberately temporary, one-time admin-bootstrap process with a secret, expiry, and automatic disable. I did not add a public admin-creation route because it could expose administrator access.
