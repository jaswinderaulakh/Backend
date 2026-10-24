# STHIRA Backend

The server behind the STHIRA mobile app. It checks wall cracks from a photo and a coin-tap sound.

**Status: Stage 1.** Every endpoint works, but the analysis results are FAKE until later stages replace them.

## 1. Install the Python libraries (Windows)

Open a terminal (PowerShell or Command Prompt) in this folder, then:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

The first line makes a private box for the libraries. The second turns it on (you will see `(.venv)` at the start of the line). The third installs everything. The last one makes your settings file `.env` (never share it).

Mac or Linux: use `python3 -m venv .venv`, `source .venv/bin/activate` and `cp .env.example .env` instead.

## 2. Start the server

Every time you come back, open a terminal in this folder and run:

```
.venv\Scripts\activate
uvicorn app.main:app --reload
```

The first start creates the database file (`sthira.db`) and the `storage` folder by itself. Stop the server with Ctrl+C.

## 3. Open the test page

With the server running, open this in your web browser:

http://127.0.0.1:8000/docs

It lists every endpoint and lets you try each one with a button. No coding needed.

## 4. Try an upload on the test page

1. Open `POST /auth/register`, click **Try it out**, type a username and a password (6+ characters), click **Execute**.
2. Click the green **Authorize** button (top right). Type the same username and password, click **Authorize**, then **Close**. Leave the other boxes empty.
3. Open `POST /buildings`, click **Try it out**, give it a name, latitude and longitude, click **Execute**. Note the `id` in the answer (the first one is 1).
4. Open `POST /inspections`, click **Try it out**. Fill in `building_id`, `floor`, `location`, pick an `exposure_class`.
5. For `photo` click **Choose File** and pick `tests\fixtures\sample_crack.jpg`. For `wav` pick `tests\fixtures\sample_tap.wav`. Click **Execute**.
6. The (fake) result appears below. To get the PDF: open `GET /inspections/{inspection_id}/report.pdf`, enter the inspection id, click **Execute**, then **Download file**.
7. Try `GET /campus/map` to see the building as GeoJSON with its health index.

## Run the tests

```
python -m pytest
```
