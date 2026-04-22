import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def parse_telegram_init_data(init_data: str, bot_token: str | None) -> dict:
    if not init_data:
        return {}

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    raw_hash = pairs.pop("hash", None)
    if bot_token and raw_hash:
        data_check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, raw_hash):
            raise ValueError("Telegram WebApp init data signature is invalid")

    user_raw = pairs.get("user")
    if not user_raw:
        return {}
    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        return {}
