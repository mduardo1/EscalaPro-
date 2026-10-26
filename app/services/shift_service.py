import re
from datetime import date, datetime, timedelta

from app.services.validation import number_value, text_value, time_value


def validate_shift(form):
    start = time_value(form.get("start_time"))
    end = time_value(form.get("end_time"))
    if start == end:
        raise ValueError(
            "Início e fim devem ser diferentes; turnos de 24h não são aceitos."
        )
    duration = datetime.combine(date.today(), end) - datetime.combine(
        date.today(), start
    )
    if end < start:
        duration += timedelta(days=1)
    interval = number_value(
        form.get("break_minutes"), "Intervalo", 0, 1439, integer=True
    )
    if interval >= duration.total_seconds() / 60:
        raise ValueError("O intervalo deve ser menor que a duração do turno.")
    color = form.get("color", "")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("Selecione uma cor válida.")
    return {
        "name": text_value(form.get("name", ""), "Nome do turno", 2, 80),
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
        "break_minutes": interval,
        "color": color,
    }
