from datetime import datetime


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()

