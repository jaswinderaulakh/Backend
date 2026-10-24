# STHIRA API guide for the mobile-app developer

The backend exposes an OpenAPI test page at `/docs`. Use the Render URL in production and `http://127.0.0.1:8000` when it is running on a development computer. `GET /openapi.json` returns the machine-readable API description, and `GET /redoc` provides a second documentation view. Except for the health check and account registration/login, API endpoints require a login token.

## Sign up and sign in

`POST /auth/register` accepts JSON. New public registrations always receive the `inspector` role; the request cannot grant admin access.

```json
{"username":"inspector01","password":"choose-a-private-password"}
```

`POST /auth/login` is a form submission, not JSON. Send `username` and `password` as `application/x-www-form-urlencoded`. The response contains `access_token` and `token_type: "bearer"`. Send the token on later requests in this header:

```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

The API uses bcrypt password hashes, token expiry, and a configured limit on repeated failed login attempts. Public registration cannot make an admin. An admin must be created against the same database the service uses; running `python -m app.core.create_admin` on a laptop creates an admin only in that laptop's database.

## Buildings and campus map

| Method and path | Who can use it | What it does |
| --- | --- | --- |
| `GET /health` | Public | Confirms the app and database respond. |
| `POST /auth/register` | Public | Creates an inspector account. |
| `POST /auth/login` | Public | Returns a bearer token. |
| `GET /buildings` | Signed-in user | Lists buildings. |
| `POST /buildings` | Admin | Creates a building. Latitude and longitude can be omitted, but buildings without them do not appear as map points. |
| `GET /buildings/{building_id}` | Signed-in user | Building detail, inspection history visible to that user, and health-index trend. |
| `GET /buildings/{building_id}/inspections` | Signed-in user | Inspection history, newest first; inspectors see their own records and admins see all. |
| `GET /campus/map` | Signed-in user | GeoJSON campus map. Each located building has a point at `[longitude, latitude]`. The feature properties include building name, health index, colour, inspection count, worst verdict, and last inspection date. Buildings without coordinates are listed in `missing_location`. |

A building can be created by an admin with a request such as:

```json
{"name":"Engineering Block A","latitude":18.5204,"longitude":73.8567}
```

## Upload an inspection

`POST /inspections` is a `multipart/form-data` request. The required fields are:

- `photo`: JPEG or PNG showing the STHIRA ArUco marker and wall area.
- `building_id`: an existing building's numeric ID.
- `floor`: a short floor label such as `Ground` or `2`.
- `location`: a useful description such as `North wall near stairwell`.
- `exposure_class`: exactly `mild`, `moderate`, or `severe`.
- `wav`: optional coin-tap WAV recording.

The current per-file upload limits are in `config/uploads.yaml` (15 MB for a photo and 10 MB for a WAV). Send the bearer token with the upload. A successful request returns **HTTP 202**, which means the app accepted the job and is processing it; it does not mean the analysis is finished.

The phone app must record the tap as an **uncompressed 48 kHz WAV**. The recording should contain one clear coin tap, with minimal background noise. Here is a Windows PowerShell example; replace the URL, token, paths, and building ID with your own values:

```powershell
$token = "YOUR_ACCESS_TOKEN"
curl.exe -X POST "http://127.0.0.1:8000/inspections" `
  -H "Authorization: Bearer $token" `
  -F "photo=@C:\sthira\wall.jpg" `
  -F "wav=@C:\sthira\tap.wav;type=audio/wav" `
  -F "building_id=1" `
  -F "floor=Ground" `
  -F "location=North wall near stairwell" `
  -F "exposure_class=moderate"
```

Poll `GET /inspections/{inspection_id}` until `status` becomes `completed` or `failed`. The possible statuses are `pending`, `processing`, `completed`, and `failed`. On success, the response includes the inspection details and available `scale`, `crack`, `audio`, `verdict`, `exceeds_is456_limit`, `health_score`, and `cost` values. If processing fails, display the plain-English `error_message` and allow the inspector to correct the photo or recording and submit a new inspection.

Keep polling at a modest interval (for example, every 2–3 seconds) and stop as soon as the status is final. `GET /inspections/{inspection_id}/report.pdf` downloads the PDF report; include the same bearer-token header and save the response as a `.pdf` file. Inspectors can read their own inspection records; admins can read all records.

## Important result wording

The verdict, severity, health index, tap class, and cost are screening outputs based on configured rules. CPWD rates are marked as placeholders. They are not a certified structural assessment, a safety guarantee, or a repair quotation. The app should tell users to seek a qualified structural engineer for concerning damage. An `exceeds_is456_limit` result means the measured width exceeded the configured comparison value for the selected exposure class; it does not itself certify that a structure is safe or unsafe.
