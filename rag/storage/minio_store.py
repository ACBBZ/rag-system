import io

from minio import Minio

from rag.config import Settings


class MinioObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

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

    def remove_prefix(self, prefix: str) -> None:
        for item in self.client.list_objects(self.bucket, prefix=prefix, recursive=True):
            self.client.remove_object(self.bucket, item.object_name)
