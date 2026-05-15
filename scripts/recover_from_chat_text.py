import argparse
from pathlib import Path
import sys
import urllib.parse
import urllib.request
from uuid import uuid4


def post_chat_text(base_url: str, token: str, path: Path, dry_run: bool) -> bytes:
    boundary = f"----bfb-recovery-{uuid4().hex}"
    content = path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                "Content-Type: text/plain\r\n\r\n"
            ).encode("utf-8"),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    query = urllib.parse.urlencode({"token": token, "dry_run": str(dry_run).lower()})
    url = f"{base_url.rstrip('/')}/admin/recover/chat-text?{query}"
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover BBF applications from copied Telegram admin chat text.")
    parser.add_argument("--file", required=True, type=Path, help="Path to the copied Telegram chat .txt file.")
    parser.add_argument("--base-url", default="https://bot-federation-production.up.railway.app")
    parser.add_argument("--token", required=True, help="ADMIN_EXPORT_TOKEN value.")
    parser.add_argument("--apply", action="store_true", help="Import rows. Without this flag the server runs dry-run.")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    try:
        result = post_chat_text(args.base_url, args.token, args.file, dry_run=not args.apply)
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1

    print(result.decode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
