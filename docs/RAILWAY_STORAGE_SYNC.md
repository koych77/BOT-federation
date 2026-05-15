# Railway storage and local sync

## Railway storage

Use PostgreSQL for form data and a Railway Volume for uploaded receipts.

Recommended Railway variables:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
STORAGE_BACKEND=local
UPLOAD_DIR=/data/uploads
ADMIN_EXPORT_TOKEN=change-this-long-secret
```

In Railway, add a Volume to the bot service and mount it to:

```text
/data
```

After that, receipt files are stored under `/data/uploads` and survive redeploys.

The bot now refuses to start on Railway if `DATABASE_URL` is empty or points to SQLite.
This protects new applications from being silently saved to temporary container storage.

Every submitted application also gets a JSON safety snapshot under:

```text
/data/uploads/snapshots/applications/
```

These snapshots are a second recovery layer next to PostgreSQL and the admin Telegram chat.

## Admin bot commands

Admins from `ADMIN_TELEGRAM_IDS` can use:

```text
/admin
/export
/backup
/status
```

`/export` sends the Excel file to Telegram.

`/backup` sends a zip archive with:

- Excel export
- uploaded receipt files
- JSON safety snapshots
- `BACKUP_MANIFEST.json` with database/storage counts
- `MISSING_RECEIPTS.txt` if some stored receipt cannot be read

`/status` shows the current database backend, application count, payment count, snapshot count, and latest application id.

The same status is available by URL:

```text
https://bot-federation-production.up.railway.app/admin/storage-status?token=ADMIN_EXPORT_TOKEN
```

## Sync to this PC

Run from the project folder:

```powershell
$env:ADMIN_EXPORT_TOKEN="same-token-as-railway"
powershell -ExecutionPolicy Bypass -File .\scripts\sync_railway_data.ps1
```

Files will be saved to:

```text
.\synced\YYYYMMDD-HHMMSS\
```

You can automate this script with Windows Task Scheduler if you want the PC copy to refresh every hour or every day.

To install hourly automatic sync on this PC:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_railway_sync_task.ps1 -Token "same-token-as-railway"
```

To use a custom folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_railway_sync_task.ps1 -Token "same-token-as-railway" -OutputDir "D:\BBF-sync" -IntervalMinutes 60
```
