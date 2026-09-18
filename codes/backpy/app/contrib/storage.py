"""Where contributed recordings are kept: a private S3 bucket, or a folder in local development.

Objects are written with server-side encryption and are never public. Keys contain
only random ids, never a name or an email.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.settings import Settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def delete(self, key: str) -> None: ...


class S3Storage:
    def __init__(self, bucket: str, region: str, prefix: str):
        import boto3

        # Credentials come from the standard AWS_* environment variables.
        self.client = boto3.client("s3", region_name=region or None)
        self.bucket = bucket
        self.prefix = prefix

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=self.prefix + key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=self.prefix + key)


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


@lru_cache
def _storage(backend: str, bucket: str, region: str, prefix: str, local_dir: str) -> Storage:
    if backend == "local":
        return LocalStorage(local_dir)
    return S3Storage(bucket, region, prefix)


def get_storage(settings: Settings) -> Storage:
    return _storage(settings.storage_backend, settings.s3_bucket, settings.s3_region, settings.s3_prefix, settings.storage_local_dir)
