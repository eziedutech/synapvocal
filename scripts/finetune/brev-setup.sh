#!/usr/bin/env bash
# Set up a rented GPU box for the ezidysarthric run and fetch the data there.
#
# Nothing is uploaded from home: the repository is public, the split manifest is in it,
# and TORGO comes from Hugging Face over the datacenter's own link. About 1.5 GB in,
# which on these machines is a couple of minutes.
#
#   bash brev-setup.sh
#
# TORGO is academic and non-profit use only. It stays on this machine, is never
# redistributed, and is deleted when the box is destroyed.
set -euo pipefail

REPO=https://github.com/eziedutech/synapvocal.git
WORK=${WORK:-$HOME/synapvocal}

echo "== GPU =="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

echo "== repository =="
[ -d "$WORK" ] || git clone --depth 1 "$REPO" "$WORK"
cd "$WORK"

echo "== python packages =="
# A CPU build of torch trains for days while looking like it is working, so this stops
# here rather than letting the run start on one.
python - <<'CHECK'
import sys
try:
    import torch
except ModuleNotFoundError:
    sys.exit("torch is not installed. Pick an image that ships PyTorch with CUDA, or install "
             "the CUDA build for this box from pytorch.org before running this again.")
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
if not torch.cuda.is_available():
    sys.exit("torch cannot see the GPU. Do not train on this: install the CUDA build.")
CHECK
pip install --quiet -r scripts/finetune/requirements.txt huggingface_hub

echo "== TORGO, straight from Hugging Face =="
# The shards land in scripts/benchmark/data/, which is where torgo.py looks for them.
hf download abnerh/TORGO-database --repo-type dataset \
  --include "data/train-*.parquet" --local-dir scripts/benchmark
ls -la scripts/benchmark/data/

echo "== build the training splits =="
# Texts are disjoint between train and test by hash, and F03, M02 and M04 are held out
# entirely, so the unseen-speaker split measures generalisation rather than memorisation.
cd scripts/finetune
python prepare_data.py
du -sh data/v1

cat <<'NEXT'

== ready ==

Smoke test first, on the real GPU, about ten minutes. It catches an environment
problem now instead of six hours from now:

    python train.py --data-dir data/v1 --output-dir out-smoke --limit 200 --epochs 1

Then the full run. Keep it in tmux so a dropped connection does not kill it:

    tmux new -s train
    python train.py --data-dir data/v1 --output-dir out 2>&1 | tee train.log

When it finishes, these are what matter:

    out/report.json                every number, baseline and fine-tuned
    out/predictions-*.jsonl        per utterance, to score it the way the benchmark does
    out/ezidysarthric-adapter/     the LoRA weights, small
    out/ezidysarthric/             the merged model, several GB

Take the first three home and leave the merged model unless you mean to serve it:

    tar czf ezidysarthric.tgz out/report.json out/predictions-*.jsonl out/ezidysarthric-adapter

Then DESTROY THE INSTANCE. On the cheapest Brev options there is no stop/start,
so an idle box bills until it is deleted, and a forgotten weekend is the whole
credit.
NEXT
