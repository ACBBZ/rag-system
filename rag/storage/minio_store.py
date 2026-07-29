from __future__ import annotations

import io
from pathlib import PurePath

from minio import Minio

from rag.config import Settings


class MinioObjectStore:
    def __init__(self, settings: Settings, *, client: Minio | None = None) -> None:
        self.bucket = settings.minio_bucket
        self.client = client or Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    @staticmethod
    def safe_filename(filename: str) -> str:
        return PurePath(filename.replace("\\", "/")).name or "upload.bin"

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_bytes(self, object_key: str, content: bytes, content_type: str) -> None:
        self.ensure_bucket()
        self.client.put_object(
            self.bucket,
            object_key,
            io.BytesIO(content),
            length=len(content),
            content_type=content_type,
        )

    def get_bytes(self, object_key: str) -> bytes:
        response = self.client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def object_exists(self, object_key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, object_key)
            return True
        except Exception:
            return False

    def remove_prefix(self, prefix: str) -> None:
        for item in self.client.list_objects(self.bucket, prefix=prefix, recursive=True):
            self.client.remove_object(self.bucket, item.object_name)
