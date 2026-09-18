"""Start the ezidysarthric training job on SageMaker, or show what it would start.

Dry run by default: prints the job request and touches nothing. With --go it uploads
the split (skipping files already in S3 with the same size), packs train.py with
requirements.txt, and creates one managed spot training job. The job stops itself
when training ends, and MaxRuntime caps the bill if something hangs.

    uv run --project scripts/finetune python scripts/finetune/launch.py            # dry run
    uv run --project scripts/finetune python scripts/finetune/launch.py --go       # spends credit
    uv run --project scripts/finetune python scripts/finetune/launch.py --status NAME

Uses the AWS profile `synapvocal` (user synapvocal-train, us-east-1).
"""

from __future__ import annotations

import argparse
import io
import json
import tarfile
import time
from pathlib import Path

import boto3

HERE = Path(__file__).parent
PROFILE = "synapvocal"
REGION = "us-east-1"
ACCOUNT = "350553112293"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/service-role/AmazonSageMaker-ExecutionRole-20260917T191905"
BUCKET = f"sagemaker-{REGION}-{ACCOUNT}"
PREFIX = "synapvocal"
IMAGE = f"763104351884.dkr.ecr.{REGION}.amazonaws.com/pytorch-training:2.10.0-gpu-py313-cu130-ubuntu22.04-sagemaker"
INSTANCE = "ml.g6e.2xlarge"
MAX_RUNTIME_H = 8
MAX_WAIT_H = 16


def upload_split(s3, data_dir: Path, version: str) -> str:
    prefix = f"{PREFIX}/data/{version}/"
    existing = {o["Key"]: o["Size"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])}
    for path in sorted(data_dir.glob("*.parquet")):
        key = prefix + path.name
        if existing.get(key) == path.stat().st_size:
            print(f"already in S3: {key}")
            continue
        print(f"uploading {path.name} ({path.stat().st_size / 1e6:.0f} MB)")
        s3.upload_file(str(path), BUCKET, key, ExtraArgs={"ServerSideEncryption": "AES256"})
    return f"s3://{BUCKET}/{prefix}"


def upload_source(s3, job: str) -> str:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name in ("train.py", "requirements.txt"):
            tar.add(HERE / name, arcname=name)
    key = f"{PREFIX}/jobs/{job}/source/sourcedir.tar.gz"
    s3.put_object(Bucket=BUCKET, Key=key, Body=buffer.getvalue(), ServerSideEncryption="AES256")
    return f"s3://{BUCKET}/{key}"


def request(job: str, data_uri: str, source_uri: str, args) -> dict:
    hyperparameters = {
        "model": args.model,
        "model-name": args.model_name,
        "epochs": str(args.epochs),
        "learning-rate": str(args.learning_rate),
        "batch-size": str(args.batch_size),
        "lora-r": str(args.lora_r),
        "lora-alpha": str(args.lora_r * 2),
    }
    # SageMaker script mode: these two keys tell the container what to run.
    hyperparameters |= {"sagemaker_program": "train.py", "sagemaker_submit_directory": source_uri}
    return {
        "TrainingJobName": job,
        "RoleArn": ROLE,
        "AlgorithmSpecification": {"TrainingImage": IMAGE, "TrainingInputMode": "File"},
        "HyperParameters": {k: json.dumps(v) for k, v in hyperparameters.items()},  # the toolkit JSON-decodes each value
        "InputDataConfig": [
            {
                "ChannelName": "data",
                "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix", "S3Uri": data_uri, "S3DataDistributionType": "FullyReplicated"}},
            }
        ],
        "OutputDataConfig": {"S3OutputPath": f"s3://{BUCKET}/{PREFIX}/jobs/"},
        "CheckpointConfig": {"S3Uri": f"s3://{BUCKET}/{PREFIX}/jobs/{job}/checkpoints", "LocalPath": "/opt/ml/checkpoints"},
        "ResourceConfig": {"InstanceType": INSTANCE, "InstanceCount": 1, "VolumeSizeInGB": 100},
        "EnableManagedSpotTraining": not args.on_demand,
        "StoppingCondition": {"MaxRuntimeInSeconds": MAX_RUNTIME_H * 3600}
        | ({} if args.on_demand else {"MaxWaitTimeInSeconds": MAX_WAIT_H * 3600}),
        "Tags": [{"Key": "project", "Value": "synapvocal"}],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--go", action="store_true", help="actually upload and start the job")
    parser.add_argument("--status", metavar="JOB")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--model", default="openai/whisper-large-v3")
    parser.add_argument("--model-name", default="ezidysarthric")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--on-demand", action="store_true", help="skip spot (faster start, about 3x the price)")
    args = parser.parse_args()

    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    sagemaker = session.client("sagemaker")

    if args.status:
        job = sagemaker.describe_training_job(TrainingJobName=args.status)
        keys = ("TrainingJobStatus", "SecondaryStatus", "FailureReason", "TrainingTimeInSeconds", "BillableTimeInSeconds")
        print(json.dumps({k: job.get(k) for k in keys}, indent=1, default=str))
        for transition in job.get("SecondaryStatusTransitions", [])[-5:]:
            print(transition.get("Status"), "-", transition.get("StatusMessage"))
        return

    job = f"{args.model_name}-{args.version}-{time.strftime('%Y%m%d-%H%M%S')}"
    data_dir = HERE / "data" / args.version
    if not args.go:
        preview = request(job, f"s3://{BUCKET}/{PREFIX}/data/{args.version}/", "s3://<uploaded on --go>", args)
        print(json.dumps(preview, indent=1))
        print("\ndry run: nothing uploaded, no job created. Add --go to start it.")
        return

    s3 = session.client("s3")
    data_uri = upload_split(s3, data_dir, args.version)
    source_uri = upload_source(s3, job)
    sagemaker.create_training_job(**request(job, data_uri, source_uri, args))
    print(f"started {job}")
    print(f"check: uv run --project scripts/finetune python scripts/finetune/launch.py --status {job}")


if __name__ == "__main__":
    main()
