# STHIRA Backend

The server behind the STHIRA mobile app. It checks wall cracks from a photo and a coin-tap sound.

## 1. Install the Python libraries

You need Python 3.10 or newer. Open a terminal in this folder, then:

**Windows**
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Mac or Linux**
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The first command makes a private box for the libraries. The second turns it on. The third installs everything. Next, copy `.env.example` to a new file called `.env` (settings go there; never share it).

## 2. Start the server

```
uvicorn app.main:app --reload
```

This works from Stage 1 onwards; the file `app/main.py` does not exist yet. Stop the server with Ctrl+C.

## 3. Open the test page

With the server running, open this in your web browser:

http://127.0.0.1:8000/docs

This page lists every endpoint and lets you try each one with a button. No coding needed.

## Run the tests

```
python -m pytest
```
