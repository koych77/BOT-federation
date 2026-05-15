from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path

from app.config import Settings
from app.models import MemberApplication, Payment


def _json_value(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _model_to_dict(model: object) -> dict[str, object]:
    return {
        column.name: _json_value(getattr(model, column.name))
        for column in model.__table__.columns  # type: ignore[attr-defined]
    }


def write_application_snapshot(settings: Settings, application: MemberApplication, payment: Payment) -> Path | None:
    if settings.storage_backend != "local":
        return None

    snapshot_dir = settings.upload_dir / "snapshots" / "applications"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    target = snapshot_dir / f"application_{application.id}.json"
    temp_target = target.with_suffix(".tmp")
    payload = {
        "schema": "bfb_application_snapshot_v1",
        "saved_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "application": _model_to_dict(application),
        "payment": _model_to_dict(payment),
    }

    temp_target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_target.replace(target)
    return target


def iter_snapshot_files(settings: Settings) -> list[Path]:
    if settings.storage_backend != "local":
        return []
    snapshot_root = settings.upload_dir / "snapshots"
    if not snapshot_root.exists():
        return []
    return sorted(path for path in snapshot_root.rglob("*.json") if path.is_file())
