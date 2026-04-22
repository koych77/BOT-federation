import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


async def save_upload(upload_dir: Path, file: UploadFile) -> tuple[str, int, str]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "receipt").suffix.lower()
    safe_name = f"{uuid4().hex}{suffix}"
    target = upload_dir / safe_name

    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
            out.write(chunk)

    await file.seek(0)
    return str(target), size, digest.hexdigest()
