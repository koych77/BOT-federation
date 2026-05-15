from datetime import datetime
from io import BytesIO
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings
from app.models import MemberApplication, Payment
from app.services.export import build_members_export
from app.services.snapshots import iter_snapshot_files
from app.services.storage import read_receipt_bytes


def _safe_filename(value: str | None, fallback: str) -> str:
    name = (value or fallback).strip() or fallback
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
    return name[:140]


def build_backup_archive(settings: Settings, db: Session) -> bytes:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    missing_receipts: list[str] = []
    payments = db.scalars(
        select(Payment)
        .options(joinedload(Payment.application))
        .order_by(Payment.created_at.desc())
    ).all()

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(f"bfb_members_{timestamp}.xlsx", build_members_export(db))
        archive.writestr(
            "BACKUP_MANIFEST.json",
            json.dumps(
                {
                    "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "applications_count": db.scalar(select(func.count()).select_from(MemberApplication)) or 0,
                    "payments_count": db.scalar(select(func.count()).select_from(Payment)) or 0,
                    "storage_backend": settings.storage_backend,
                    "upload_dir": str(settings.upload_dir),
                    "snapshots_count": len(iter_snapshot_files(settings)),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        for payment in payments:
            app = payment.application
            member_name = _safe_filename(app.full_name if app else None, "member")
            receipt_name = _safe_filename(payment.receipt_original_name, "receipt")
            archive_name = f"receipts/application_{payment.application_id}_{member_name}_{receipt_name}"
            try:
                archive.writestr(archive_name, read_receipt_bytes(settings, payment.receipt_path))
            except Exception as exc:
                missing_receipts.append(
                    f"application #{payment.application_id}: {payment.receipt_original_name} ({payment.receipt_path}) - {exc}"
                )

        if missing_receipts:
            archive.writestr("MISSING_RECEIPTS.txt", "\n".join(missing_receipts))

        for snapshot_path in iter_snapshot_files(settings):
            archive.write(snapshot_path, f"snapshots/{snapshot_path.relative_to(settings.upload_dir / 'snapshots')}")

    return output.getvalue()
