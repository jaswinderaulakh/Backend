# What the numbers mean (and what they do not mean)

## What has actually been checked

The automated tests create their own sample wall photos, ArUco markers, cracks with known pixel widths, and coin-tap sounds. For one generated photo, the known crack width is 2.00 mm and the program measured about 2.25 mm, an absolute difference of about 0.25 mm. That is a useful check that the pieces connect and respond to a simple clean example.

The tests also check that the app handles a missing marker, no visible crack, missing or silent sound, unreadable uploads, and other failures in the intended way. They do not use photos or recordings from actual campus buildings.

## What cannot honestly be claimed yet

There is **no measured real-world accuracy claim** for crack width, crack angle, or solid-versus-hollow tap classification. The generated test pictures are cleaner and more predictable than phone photos of real walls. Camera distance, lighting, paint, stains, plaster texture, marker placement, phone sharpening, microphone differences, room noise, and the way a person taps can all change the answer.

The tap-frequency thresholds, crack decision rules, severity values, health-score deductions, and repair rates are starting settings, not a validated structural-engineering diagnosis. The repair rates are explicitly placeholders; do not use the cost total as a quotation or budget approval. The IS 456 comparison in the report is a configured screening comparison, not a declaration that a building is safe or unsafe.

## How to collect useful real checks

Have a qualified person measure the same crack independently with a suitable crack gauge, and record a clean photo with the STHIRA marker beside it. Record the WAV at the app's expected uncompressed 48 kHz, label the tap as solid or hollow using a documented reference method, and keep notes about the wall, phone, distance, and conditions. Use several different walls and phones; repeated taps on one small patch are not a substitute for independent examples.

Put the file names and independently measured values in `tests/real_data/truth.csv`. The `batch_check`, `tune_audio`, and `tune_width` tools will continue past files that fail. Audio and width tuning only print suggestions; they do not edit `config/thresholds.yaml`. Review every suggested change with a structural engineer and rerun the tests before using it.

## Reading the reports

- `width_error_mm` is measured maximum width minus the provided truth width; `width_error_percent` is the absolute difference divided by truth width. These numbers are meaningful only if the truth measurement itself is trustworthy.
- `smallest_trusted_width_mm` is based on the photo's pixel scale and is a warning about camera resolution. A result below it is not reliable; it does not mean the crack is absent.
- A tap class mismatch is a difference between the app's frequency-based classification and the label supplied in `truth.csv`. It is not an independent diagnosis of the wall.
- Verdict severity and the Building Health Index are rule-based summaries. They are not calibrated probabilities or certified condition ratings.

Until a useful set of independently labelled real photos and recordings is collected and reviewed, treat STHIRA as a prototype screening aid. A qualified engineer must inspect concerning cracks and make all safety decisions.
