import hashlib
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import boto3
from fastapi import UploadFile

from app.config import Settings


def _s3_client(settings: Settings):
    if not all([settings.storage_bucket, settings.storage_access_key, settings.storage_secret_key]):
        raise RuntimeError("S3 storage is selected, but bucket/access keys are not configured")
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url,
        region_name=settings.storage_region,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
    )


async def save_upload(settings: Settings, file: UploadFile) -> tuple[str, int, str]:
    suffix = Path(file.filename or "receipt").suffix.lower()
    safe_name = f"receipts/{uuid4().hex}{suffix}"

    digest = hashlib.sha256()
    content = await file.read()
    size = len(content)
    digest.update(content)

    await file.seek(0)

    if settings.storage_backend == "s3":
        client = _s3_client(settings)
        client.upload_fileobj(
            BytesIO(content),
            settings.storage_bucket,
            safe_name,
            ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
        )
        return f"s3://{settings.storage_bucket}/{safe_name}", size, digest.hexdigest()

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = settings.upload_dir / Path(safe_name).name
    target.write_bytes(content)
    return str(target), size, digest.hexdigest()


def read_receipt_bytes(settings: Settings, receipt_path: str) -> bytes:
    if receipt_path.startswith("s3://"):
        _, rest = receipt_path.split("s3://", 1)
        bucket, key = rest.split("/", 1)
        client = _s3_client(settings)
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    return Path(receipt_path).read_bytes()
