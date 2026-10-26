from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app


def local_now():
    return datetime.now(ZoneInfo(current_app.config["APP_TIMEZONE"]))
