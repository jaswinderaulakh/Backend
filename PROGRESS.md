# STHIRA Backend: Progress

- [x] Stage 0: Planning and shared files (spec, folders, schemas, config, requirements)
- [ ] Stage 1: API skeleton with fake data
- [ ] Stage 2: Audio module
- [ ] Stage 3: Marker + scale
- [ ] Stage 4: Crack measurement
- [ ] Stage 5: Rules + cost + PDF
- [ ] Stage 6: Campus map + login
- [ ] Stage 7: Connect everything
- [ ] Stage 8: Real-data check
- [ ] Stage 9: Deployment

## Next step

Stage 1: build the API skeleton (`app/main.py`, database tables, all endpoints
returning fake data that follows `app/core/schemas.py`), with tests.

## Notes

- Replace the placeholder rates in `config/cpwd_rates.json` with real CPWD DSR values (project owner).
- Confirm the severity numbers in `config/rules.yaml` and the severity-to-score table in `config/thresholds.yaml`.
- Open question: exact formula for the Building Health Index (the deck does not give one).
- The deck's rule table has gaps (for example a tap sound between 900 and 1400 Hz); a fallback verdict "Inconclusive" was added.
- Tests so far: `python -m pytest` (schemas and config files).
