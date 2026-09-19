Runs 1 and 2 of round A (17 Sep 2026, 02:03 to 02:07) are not measurements.
673 of 695 and 60 of 60 utterances were refused by AssemblyAI: error 1008 'Too many concurrent sessions' at 5 workers.
Kept only as a record of the failure. Never score or quote them.
Run 3 smoke (8 utterances, 1 worker, 02:08): the first 5 sessions succeeded, the next 3 were refused with 1008 within about 35 s. Points to a limit of about 5 new sessions per minute, not to parallelism.
Run 4 smoke (10 utterances, 4 sessions/min, 02:20): all 10 succeeded, no refusal. Not a measurement: it ran without language_codes=en, and one utterance came back in Mandarin. Kept as the record that pacing works.
Round C0 smoke run0 (3 calls, 07:35): prompt said 'first person', which turned 'he slowly takes' into 'I slowly take'. Prompt fixed; not a measurement.
Round C0 smoke run1 (3 calls, 07:35): prompt fix confirmed ('He slowly takes' kept). Smoke only, not a measurement.
Round C0 gemini-3.1-flash-lite run2 (07:35 to 07:36): aborted by design at call 24 on 429 RESOURCE_EXHAUSTED at 20 calls/min. 23 results exist but the run is incomplete; never quote it.
Round C0 gemini-3.7-flash LOW run1 smoke (07:42): first call refused 429 RESOURCE_EXHAUSTED at 10 calls/min, about 6 minutes after the Flash-Lite 429. Aborted, not a measurement.
Round C0 gemini-3.7-flash LOW run2 smoke (07:46): 3 of 3 ok, 0 retries, after adding logged backoff. Smoke only.
Round C0 gemini-3.8-flash LOW run1 smoke (08:21): 3 of 3 ok, 0 retries, 0 thought tokens reported. Smoke only.
Round B run1 smoke (08:22): 3 of 3 ok, prompt present in params, word confidences stored. Smoke only.
Round B run3 smoke (10:21): 12 of 12 sessions at 30 per minute succeeded, proving the pay-as-you-go upgrade is active (free plan refused after 5). Smoke only.
Round A run0 smoke (first script test, 3 utterances, before language_codes=en): smoke only.
Round C1 gemini-3.7-flash LOW with audio run1 smoke (10:53): 3 of 3 ok. Smoke only.
Round C1 gemini-3.5-flash-lite with audio run1 smoke (11:57): 3 of 3 ok, 1.7 to 2.7 s. Smoke only.
Round C2 gemini-3.7-flash LOW audio + history 5 run1 smoke on pilot (15:12): 3 of 3 ok. Smoke only.
Round C2 gemini-3.7-flash LOW audio + history 5 run1 on pilot (15:13 to 15:14): aborted at item 6 by an httpx ReadError (dropped connection), which the backoff loop did not yet treat as transient. Fixed in interpret.py; rerun as run2. Never quote run1.
Prompt v2 smoke (3 items, 18 Sep): checks the runner only. Never quote.
Round E smoke (2 items, 19 Sep): checks universal-3-6-pro is accepted. Never quote.
