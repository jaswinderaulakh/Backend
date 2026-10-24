# STHIRA Backend: Specification

STHIRA (Structural Health Inspector & Risk Assessment) is a campus building
crack-checking system. This backend is the "brain" behind the mobile app.
Source: `docs/TechElevate_Final_Pitch-5.pptx`.

## 1. What the backend does

A person photographs a wall crack with a printed 5 cm ArUco marker stuck next
to it, and records a 3-second coin tap on the wall (WAV, 48 kHz). The backend
then runs this pipeline:

1. **Scale.** Find the marker, straighten the tilted photo, and work out how
   many millimetres one pixel covers (mm per pixel).
2. **Crack measurement.** Find the crack and measure its width (widest and
   average), length and angle, in real millimetres and degrees.
3. **Tap-sound check.** Find the loudest frequency of the coin tap. Low means
   hollow (void), high means solid concrete.
4. **Verdict.** Combine crack and sound using the rule table in
   `config/rules.yaml` (for example "Shear risk: inspect first").
5. **Health score.** Turn the verdict's severity into a 0-100 score for the
   inspection. Scores roll up into a Building Health Index for the campus map.
6. **Repair cost.** Build a repair estimate in rupees from CPWD rates and
   produce a PDF report.

If the marker is not found, the inspection is saved with status `failed` and a
plain message asking the user to retake the photo. No guessing.

## 2. Tech choices

| Purpose | Choice |
| --- | --- |
| Language | Python 3.10 or newer |
| Web API | FastAPI |
| Database | SQLite, accessed through SQLAlchemy |
| Image work | OpenCV (marker, tilt correction), scikit-image (crack thinning) |
| Audio and maths | SciPy |
| PDF report | ReportLab |
| Tests | pytest |

The pitch deck mentions Streamlit and YOLOv8. This backend uses FastAPI
instead (a mobile app needs an API), and starts with a classical (non-AI)
crack mask. YOLOv8 can be added later behind the same module interface.

## 3. Folder structure

```
app/
  api/        web endpoints (thin: they only call other modules)
  db/         database tables and saving/loading
  core/       shared data shapes (schemas.py), settings, config loading
  audio/      coin-tap sound analysis
  vision/     marker detection, tilt correction, mm per pixel
  crack/      crack width, length and angle
  rules/      verdict rule engine
  costing/    repair estimate and PDF report
  campus/     building health index and campus map GeoJSON
config/       thresholds.yaml, rules.yaml, cpwd_rates.json
tests/
  fixtures/   small fake test files made for the tests
  real_data/  real campus photos and recordings (Stage 8)
docs/         the pitch deck and other documents
```

Stage 1 will also add `app/main.py` (the file that starts the server).

## 4. API endpoints

All endpoints except health check, register and login need a login token.

| What | Method and path |
| --- | --- |
| Health check | `GET /health` |
| Register | `POST /auth/register` |
| Login (returns a token) | `POST /auth/login` |
| Create a building | `POST /buildings` |
| List buildings | `GET /buildings` |
| Create an inspection (uploads photo + WAV + building + floor + location + exposure class) | `POST /inspections` |
| Get one inspection's result | `GET /inspections/{id}` |
| Download the PDF report | `GET /inspections/{id}/report.pdf` |
| Inspection history of one building | `GET /buildings/{id}/inspections` |
| Campus map as GeoJSON, with health index | `GET /campus/map` |

Exposure class is one of `mild`, `moderate`, `severe` (IS 456 crack limits).
For now, creating an inspection processes everything immediately and returns
the finished result.

## 5. Data shapes

Modules pass results to each other using only the classes in
`app/core/schemas.py`: `ScaleResult`, `CrackResult`, `AudioResult`,
`Verdict`, `CostItem`, `CostEstimate`, `InspectionResult`.

## 6. Rules for all future work

1. **Thresholds live only in `config/`.** No number such as 900 Hz, 0.3 mm or
   600 Hz may be typed into Python code. Code reads it from config.
2. **No logic inside API route files.** Files in `app/api/` only receive the
   request, call the right module, and return the answer.
3. **Every module has tests.** No module is finished until its tests pass.
4. **Shared files are not changed without asking the project owner.** Shared
   files: `SPEC.md`, `app/core/schemas.py`, everything in `config/`,
   `requirements.txt`, `.env.example`, `.gitignore`. (`PROGRESS.md` is updated
   as stages finish.)
5. Thresholds in `config/` are **starting values** and will be tuned on real
   campus data.
6. `config/cpwd_rates.json` holds **placeholder** rates until the project owner
   replaces them with real CPWD DSR values. Reports must say so while that is true.
