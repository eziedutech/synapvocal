"""AssemblyAI streaming settings shared by the product and the benchmark.

Kept free of imports on purpose: scripts/benchmark loads this file directly so a
benchmark run streams with exactly the configuration the Speaker gets.
"""

WS_URL = "wss://streaming.assemblyai.com/v3/ws"

# Dysarthric speech has longer pauses inside a sentence than typical speech, so
# turn detection starts from the "patient" end of AssemblyAI's presets and goes
# further. These numbers are a starting assumption, not a measured optimum. The
# Speaker can also end a turn explicitly (ForceEndpoint), so a long silence
# window costs waiting time, not correctness.
STREAM_PARAMS = {
    # 20 Sep 2026: 3.6 Pro replaced 3.5 Pro after a full pilot run. On all 682 unique
    # dysarthric sentences it lowered WER from 0.317 to 0.301, split fewer sentences at a
    # pause (119 against 128), and with Gemini on top raised exact best choices 418 to 426.
    "speech_model": "universal-3-6-pro",
    # The product is English only. Without this the model auto-detects language and
    # read one unclear dysarthric utterance as Mandarin. It biases strongly toward
    # English but does not guarantee it, per AssemblyAI's docs.
    "language_codes": "en",
    "sample_rate": 16000,
    "encoding": "pcm_s16le",
    "min_turn_silence": 400,
    "max_turn_silence": 3000,
    "inactivity_timeout": 120,
}
