# Prepare and deploy STHIRA on Render

This project includes `Dockerfile`, `.dockerignore`, and `render.yaml`. The Blueprint file describes one Python 3.12 Docker web service, points Render at `/health`, asks Render to generate the private `SECRET_KEY`, and asks you for the app's allowed web origin. Render's Blueprint format supports Docker services, health-check paths, generated secrets, and prompted environment variables.[1] [2]

## Before opening Render

Put the project files at the top level of your GitHub repository named **Backend**. Keep `render.yaml` in that same top-level folder. Do **not** upload your real `.env`, database, `storage/`, log files, private campus photos, or recordings. The included `.env.example` is safe to share because it contains only a warning placeholder, not a real secret.

## Create the Render service

1. Create or sign in to your Render account at the Render Dashboard. Choose **New → Blueprint**.
2. Connect your GitHub account if asked. Choose the **Backend** repository and the branch containing the project. If Render asks for the Blueprint path, keep `render.yaml` at the repository root. The Dashboard displays the planned service before it is created.[1]
3. Review the proposed service. The supplied file chooses the **Free** plan for a demo only, selects the Dockerfile, and sets `/health` as the health check.
4. Render generates `SECRET_KEY` automatically. When prompted for `CORS_ALLOWED_ORIGINS`, enter the exact origin of the app's browser-based front end, for example `https://campus-app.example.org` (replace that example with your actual domain; do not include a page path or use `*`). If you are building only a native phone app and do not know its origin, ask the app developer what its WebView sends. The server deliberately refuses a wildcard origin.
5. Click **Deploy Blueprint**. Watch the service's **Events** or **Logs** page until the deploy is live.
6. Open `https://YOUR-SERVICE.onrender.com/health`. A ready service returns JSON with `"status": "ok"` and `"database": "ok"`. Then open `https://YOUR-SERVICE.onrender.com/docs` to see the API's interactive test page. Render routes traffic to a web service only after its configured HTTP health check receives a successful response.[3]

If the service says production startup is blocked, read the environment-variable names in the service logs. Open the service's **Environment** page, set the missing values, and save/deploy. Do not paste the private `SECRET_KEY` into GitHub, a chat, or this guide. Render keeps environment values in the service configuration rather than in your repository.[4]

## Important: the free plan is not safe for real campus records

Render's Free web services go idle after 15 minutes without a request and can take about a minute to start again. More importantly, their local files are temporary: a sleep, restart, or redeploy can remove the SQLite database, uploaded photos, recordings, and generated PDFs. Free web services cannot attach a persistent disk, and Render itself says Free instances are for testing or hobby projects rather than production.[5] Do not use this free configuration for important or safety-critical inspections.

There is also an admin-setup gap to resolve before using the deployed API. Public registration creates inspector accounts only, while creating a building requires an admin. Running `python -m app.core.create_admin` on your Windows laptop changes the laptop's database, **not** the Render database. Render Free does not provide shell access or one-off commands, so this free Blueprint does not include a safe way to create the first remote admin.[5] Do not share the link for real use until you choose a secure way to create an admin against the server's actual database and provide durable storage. A paid service with access to its runtime shell is one option; it still needs persistent storage.

For a single-instance paid demo, a persistent disk can be mounted at `/var/data`; set `DATABASE_URL=sqlite:////var/data/sthira.db` and `STORAGE_DIR=/var/data/storage` so both the database and uploaded files live under that mount. Persistent disks are not available on the Free plan.[6] For a multi-instance production service, use a managed database and a separate persistent file store; changing the database alone does not preserve uploaded photos or reports.

## Later switch from SQLite to PostgreSQL

The application already gets its database address from `DATABASE_URL`, and its tables use SQLAlchemy. A new PostgreSQL installation therefore needs no rewrite of the inspection or campus services. You would add a PostgreSQL driver such as `psycopg[binary]` to `requirements.txt`, set `DATABASE_URL` to the private connection URL supplied by your database provider, and redeploy. This project does not include that optional driver yet. Moving existing SQLite users and inspection records is a separate data-migration step; changing the URL alone does not copy them.

## If the deploy fails

Check the first error in Render's **Logs**. Common causes are a missing environment value, a CORS origin left at the local-development default, a Docker dependency build error, or a health endpoint that cannot reach its database. The app binds to Render's `PORT` on `0.0.0.0`, as required for Render web services.[7]

## References

[1]: https://render.com/docs/infrastructure-as-code "Render Blueprints setup"
[2]: https://render.com/docs/blueprint-spec "Render Blueprint YAML reference"
[3]: https://render.com/docs/health-checks "Render health checks"
[4]: https://render.com/docs/configure-environment-variables "Render environment variables and secrets"
[5]: https://render.com/docs/free "Render Free plan limitations"
[6]: https://render.com/docs/disks "Render persistent disks"
[7]: https://render.com/docs/web-services "Render web services and port binding"
