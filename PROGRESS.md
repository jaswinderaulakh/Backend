# STHIRA Backend: Progress

- [x] Stage 0: Planning and shared files (spec, folders, schemas, config, requirements)
- [x] Stage 1: API skeleton with fake data
- [ ] Stage 2: Audio module
- [ ] Stage 3: Marker + scale
- [ ] Stage 4: Crack measurement
- [ ] Stage 5: Rules + cost + PDF
- [ ] Stage 6: Campus map + login
- [ ] Stage 7: Connect everything
- [ ] Stage 8: Real-data check
- [ ] Stage 9: Deployment

## Next step

Stage 2: build the audio module in `app/audio/`: a function `analyze_tap(wav_path)` that returns an `AudioResult`. It reads the 48 kHz WAV, applies the 600 Hz high-pass filter, finds the loudest tap, takes the 50 ms window around it, runs the FFT, and classifies solid / void / uncertain using the limits in `config/thresholds.yaml`. It also saves the spectrum picture. Write tests using `tests/fixtures/sample_tap.wav` plus generated low and high test tones. Then swap the fake audio block in `app/pipeline.py` for the real function.

## Notes

- Replace the placeholder rates in `config/cpwd_rates.json` with real CPWD DSR values (project owner).
- Confirm the severity numbers in `config/rules.yaml` and the severity-to-score table in `config/thresholds.yaml`.
- Open question: exact formula for the Building Health Index (the deck does not give one). Stage 1 uses the average of a building's inspection scores.
- The deck's rule table has gaps (for example a tap sound between 900 and 1400 Hz); a fallback verdict "Inconclusive" exists in `config/rules.yaml` but is not used by the fake pipeline yet.
- Stage 1 decisions: login is a standard username + password form (so the Authorize button on the test page works); register takes JSON. Building and login shapes live in `app/core/api_schemas.py` because `schemas.py` is shared and was not changed.
- `app/pipeline.py` returns placeholder identity fields (inspection id 0, empty building name); `app/core/inspection_service.py` fills them in. `SPEC.md` does not mention `app/pipeline.py` yet; add it if you want the spec to match (shared file, not changed).
- All results and the sample PDF are FAKE. Only the PDF file is really created; the picture paths in the result (warped, heatmap, mask, spectrum) point to files that do not exist yet.
- Uploads must be JPEG/PNG photos and real WAV files, 15 MB each at most (`MAX_UPLOAD_MB` in `.env`).
- `.env` has a development-only secret key by default. Set a real one before Stage 9.
- Requirements pinned for Python 3.14. A harmless warning about `httpx` may appear when running tests.
- Tests: `python -m pytest` (59 tests: schemas, config files, helpers, pipeline, every endpoint).
