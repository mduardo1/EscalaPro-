"""Intervalos semiabertos: um turno pode começar no instante em que outro termina."""

from datetime import datetime, time, timedelta


def shift_period(work_date, shift):
    start = datetime.combine(work_date, time.fromisoformat(shift["start_time"]))
    end = datetime.combine(work_date, time.fromisoformat(shift["end_time"]))
    if end <= start:
        end += timedelta(days=1)
    return start, end


def overlaps(start, end, other_start, other_end):
    return start < other_end and end > other_start


def net_hours(row, window_start=None, window_end=None):
    start = datetime.fromisoformat(row["start_at"])
    end = datetime.fromisoformat(row["end_at"])
    seconds = (end - start).total_seconds()
    # Intervalo não tem horário próprio no MVP: rateio proporcional nas bordas da semana.
    clipped_start = max(start, window_start) if window_start else start
    clipped_end = min(end, window_end) if window_end else end
    fraction = max(0, (clipped_end - clipped_start).total_seconds()) / seconds
    return (seconds / 3600 - row["break_minutes"] / 60) * fraction


def validate_conflicts(start, end, schedules, unavailable):
    for row in schedules:
        if overlaps(
            start,
            end,
            datetime.fromisoformat(row["start_at"]),
            datetime.fromisoformat(row["end_at"]),
        ):
            raise ValueError(
                "Conflito: o funcionário já possui uma atribuição nesse horário."
            )
    for row in unavailable:
        if overlaps(
            start,
            end,
            datetime.fromisoformat(row["start_at"]),
            datetime.fromisoformat(row["end_at"]),
        ):
            raise ValueError("Conflito: o funcionário está indisponível nesse período.")


def collect_alerts(schedules, settings, start, end):
    alerts = []
    grouped = {}
    for row in schedules:
        grouped.setdefault(row["employee_id"], []).append(row)
    for rows in grouped.values():
        name = rows[0]["employee_name"]
        hours = sum(net_hours(row, start, end) for row in rows)
        if settings["weekly_alerts"] and hours > rows[0]["weekly_hours"] + 0.001:
            alerts.append(
                f"{name}: {hours:.1f}h nesta semana; jornada configurada de {rows[0]['weekly_hours']:g}h."
            )
        rows.sort(key=lambda row: row["start_at"])
        for previous, current in zip(rows, rows[1:]):
            gap = (
                datetime.fromisoformat(current["start_at"])
                - datetime.fromisoformat(previous["end_at"])
            ).total_seconds() / 3600
            # Inclui o par que cruza a borda da semana, mas apenas se toca a semana exibida.
            if (
                current["start_at"] < end.isoformat()
                and current["end_at"] > start.isoformat()
            ):
                if gap < 0:
                    alerts.append(f"{name}: sobreposição de horários cadastrada.")
                elif gap < settings["min_rest_hours"]:
                    alerts.append(
                        f"{name}: descanso de {gap:.1f}h antes de {datetime.fromisoformat(current['start_at']):%d/%m %H:%M}; mínimo configurado de {settings['min_rest_hours']:g}h."
                    )
    return alerts
