import math
import re
from datetime import date, datetime, time

MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)


def text_value(value, label, minimum=1, maximum=100):
    value = value.strip()
    if not minimum <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise ValueError(
            f"{label}: informe entre {minimum} e {maximum} caracteres válidos."
        )
    return value


def email_value(value, required=False):
    value = value.strip().lower()
    if not value and not required:
        return ""
    if len(value) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
        raise ValueError("Informe um e-mail válido.")
    return value


def number_value(value, label, minimum, maximum, integer=False):
    try:
        result = int(value) if integer else float(value)
    except ValueError, TypeError, OverflowError:
        raise ValueError(f"{label}: informe um número válido.") from None
    if not minimum <= result <= maximum or not math.isfinite(result):
        raise ValueError(f"{label}: use um valor entre {minimum} e {maximum}.")
    return result


def date_value(value, *, minimum=MIN_DATE, maximum=MAX_DATE):
    try:
        result = date.fromisoformat(value)
        if not minimum <= result <= maximum:
            raise ValueError
        return result
    except ValueError, TypeError:
        raise ValueError(
            f"Informe uma data válida entre {minimum:%d/%m/%Y} e {maximum:%d/%m/%Y}."
        ) from None


def time_value(value):
    if not re.fullmatch(r"\d{2}:\d{2}", value or ""):
        raise ValueError("Informe um horário válido no formato HH:MM.")
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ValueError("Informe um horário válido.") from None


def datetime_value(value):
    try:
        result = datetime.fromisoformat(value)
        date_value(result.date().isoformat())
        if result.tzinfo is not None or result.second or result.microsecond:
            raise ValueError
        return result
    except ValueError, TypeError:
        raise ValueError(
            "Informe uma data e hora local válida, com precisão de minutos."
        ) from None
