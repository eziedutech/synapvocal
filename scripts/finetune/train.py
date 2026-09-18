"""Fine-tune Whisper with LoRA on the TORGO split, then score it on the held-out tests.

Runs unchanged inside a SageMaker training job (paths come from SM_* variables) and
locally for a smoke test on CPU with a tiny model:

    uv run --project scripts/finetune python scripts/finetune/train.py \
        --model openai/whisper-tiny --data-dir scripts/finetune/data/v1-smoke8 \
        --output-dir scripts/finetune/out/smoke --max-steps 2 --batch-size 4

One job does the whole honest comparison:
1. the base model, untouched, transcribes both test views (the baseline);
2. LoRA training, with a checkpoint per epoch so a spot interruption resumes;
3. the best adapter (lowest validation loss) transcribes the same test views.
Both are scored with the benchmark's own normalisation, and the merged model is
saved for hosting.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import jiwer
import numpy as np
import pyarrow.parquet as pq
import torch
from peft import LoraConfig, get_peft_model
from transformers import (
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    WhisperForConditionalGeneration,
    WhisperProcessor,
)
from transformers.trainer_utils import get_last_checkpoint

TEST_VIEWS = ("test_seen_speakers", "test_unseen_speakers")

# Same normalisation as scripts/benchmark/score.py, copied because the training
# container only receives this folder. Change both together.
DIGITS = "zero one two three four five six seven eight nine".split()
SPELLING = {"grey": "gray", "aluminium": "aluminum", "colour": "color", "honour": "honor", "humour": "humor"}


def normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b(\d)\b", lambda m: DIGITS[int(m.group(1))], text)
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = text.replace("'", "")
    return " ".join(SPELLING.get(word, word) for word in text.split())


def decode_wav(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError("expected 16 kHz mono 16-bit audio")
        pcm = wav.readframes(wav.getnframes())
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def load_split(data_dir: Path, name: str, limit: int) -> list[dict]:
    rows = pq.read_table(data_dir / f"{name}.parquet").to_pylist()
    return rows[:limit] if limit else rows


class AudioDataset(torch.utils.data.Dataset):
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict:
        row = self.rows[i]
        return {"audio": decode_wav(row["wav"]), "text": row["text"]}


@dataclass
class Collator:
    processor: WhisperProcessor
    decoder_start_token_id: int

    def __call__(self, batch: list[dict]) -> dict:
        features = self.processor.feature_extractor(
            [b["audio"] for b in batch], sampling_rate=16000, return_tensors="pt"
        )
        labels = self.processor.tokenizer([b["text"] for b in batch], padding=True, return_tensors="pt")
        ids = labels["input_ids"].masked_fill(labels["attention_mask"].ne(1), -100)
        # The model prepends the start token itself; drop it when the tokenizer added it too.
        if (ids[:, 0] == self.decoder_start_token_id).all():
            ids = ids[:, 1:]
        return {"input_features": features["input_features"], "labels": ids}


def transcribe(model, processor, rows: list[dict], batch_size: int, device: str, dtype) -> tuple[list[str], float]:
    model.eval()
    texts: list[str] = []
    started = time.perf_counter()
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        features = processor.feature_extractor(
            [decode_wav(r["wav"]) for r in chunk], sampling_rate=16000, return_tensors="pt"
        )["input_features"].to(device, dtype=dtype)
        with torch.no_grad():
            out = model.generate(input_features=features, language="en", task="transcribe", max_new_tokens=128)
        texts.extend(processor.batch_decode(out, skip_special_tokens=True))
    return texts, time.perf_counter() - started


def score(rows: list[dict], texts: list[str]) -> dict:
    def corpus(pairs: list[tuple[str, str]]) -> float | None:
        pairs = [(r, h) for r, h in pairs if r]
        if not pairs:
            return None
        return round(jiwer.wer([r for r, _ in pairs], [h if h else "<empty>" for _, h in pairs]), 4)

    pairs = [(normalise(r["text"]), normalise(t)) for r, t in zip(rows, texts)]
    by_speaker: dict[str, list] = {}
    for row, pair in zip(rows, pairs):
        by_speaker.setdefault(row["speaker"], []).append(pair)
    return {
        "n": len(rows),
        "wer": corpus(pairs),
        "wer_sentences": corpus([p for r, p in zip(rows, pairs) if r["kind"] == "sentence"]),
        "exact": sum(r == h for r, h in pairs),
        "wer_by_speaker": {s: corpus(p) for s, p in sorted(by_speaker.items())},
    }


def evaluate(label: str, model, processor, tests: dict, args, device: str, dtype, out_dir: Path) -> dict:
    results = {}
    for view, rows in tests.items():
        texts, seconds = transcribe(model, processor, rows, args.eval_batch_size, device, dtype)
        results[view] = {**score(rows, texts), "seconds": round(seconds, 1)}
        with (out_dir / f"predictions-{label}-{view}.jsonl").open("w", encoding="utf-8") as f:
            for row, text in zip(rows, texts):
                record = {k: row[k] for k in ("id", "speaker", "kind", "text")} | {"hypothesis": text}
                f.write(json.dumps(record) + "\n")
        print(f"[{label}] {view}: {results[view]}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="openai/whisper-large-v3")
    parser.add_argument("--data-dir", default=os.environ.get("SM_CHANNEL_DATA", "data"))
    parser.add_argument("--output-dir", default=os.environ.get("SM_MODEL_DIR", "out"))
    parser.add_argument("--checkpoint-dir", default="/opt/ml/checkpoints" if "SM_MODEL_DIR" in os.environ else "")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=16)
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0, help="rows per split, for a smoke test")
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--model-name", default="ezidysarthric", help="folder name of the saved model")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    data_dir, out_dir = Path(args.data_dir), Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else out_dir / "checkpoints"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    bf16 = device == "cuda" and torch.cuda.is_bf16_supported()
    dtype = torch.bfloat16 if bf16 else torch.float32

    processor = WhisperProcessor.from_pretrained(args.model, language="en", task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(args.model, torch_dtype=dtype).to(device)
    model.generation_config.forced_decoder_ids = None
    model.config.forced_decoder_ids = None

    train_rows = load_split(data_dir, "train", args.limit)
    validation_rows = load_split(data_dir, "validation", args.limit)
    tests = {view: load_split(data_dir, view, args.limit) for view in TEST_VIEWS}
    report: dict = {"args": vars(args), "device": device, "dtype": str(dtype)}

    if not args.skip_baseline:
        report["baseline"] = evaluate("baseline", model, processor, tests, args, device, dtype, out_dir)

    model.config.use_cache = False
    model.enable_input_require_grads()
    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "out_proj", "fc1", "fc2"],
        bias="none",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    training_args = Seq2SeqTrainingArguments(
        output_dir=str(work_dir),
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        learning_rate=args.learning_rate,
        warmup_steps=0.05,  # a float below 1 is a fraction of all steps
        lr_scheduler_type="linear",
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        gradient_checkpointing=device == "cuda",
        gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=bf16,
        eval_strategy="epoch" if args.max_steps < 0 else "steps",
        save_strategy="epoch" if args.max_steps < 0 else "steps",
        eval_steps=None if args.max_steps < 0 else args.max_steps,
        save_steps=500 if args.max_steps < 0 else args.max_steps,  # ignored when saving per epoch
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=10 if args.max_steps < 0 else 1,
        dataloader_num_workers=4 if device == "cuda" else 0,
        remove_unused_columns=False,
        label_names=["labels"],
        report_to=[],
        seed=args.seed,
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=AudioDataset(train_rows),
        eval_dataset=AudioDataset(validation_rows),
        data_collator=Collator(processor, model.config.decoder_start_token_id),
    )
    last = get_last_checkpoint(str(work_dir)) if work_dir.exists() else None
    if last:
        print(f"resuming from {last}", flush=True)
    started = time.perf_counter()
    trainer.train(resume_from_checkpoint=last)
    report["train_seconds"] = round(time.perf_counter() - started, 1)
    report["log_history"] = trainer.state.log_history
    model.save_pretrained(out_dir / f"{args.model_name}-adapter")

    merged = model.merge_and_unload()
    merged.config.use_cache = True
    report["finetuned"] = evaluate("finetuned", merged, processor, tests, args, device, dtype, out_dir)

    merged.save_pretrained(out_dir / args.model_name, safe_serialization=True)
    processor.save_pretrained(out_dir / args.model_name)
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("done", flush=True)


if __name__ == "__main__":
    main()
