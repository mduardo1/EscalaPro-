from app.database import get_db, parameters
from app.tenant import company_id

SELECT_SCHEDULES = """SELECT s.*, e.name AS employee_name, e.department, e.active,
    e.weekly_hours FROM schedules s JOIN employees e ON e.id = s.employee_id AND e.company_id=s.company_id """


def list_schedules(start, end):
    return (
        get_db()
        .execute(
            SELECT_SCHEDULES
            + "WHERE s.company_id=:p0 AND s.start_at < :p1 AND s.end_at > :p2 ORDER BY s.start_at, e.name",
            parameters((company_id(), end, start)),
        )
        .fetchall()
    )


def get_schedule(schedule_id):
    return (
        get_db()
        .execute(
            SELECT_SCHEDULES + "WHERE s.id=:p0 AND s.company_id=:p1",
            parameters((schedule_id, company_id())),
        )
        .fetchone()
    )


def employee_schedules(employee_id, exclude_id=0):
    return (
        get_db()
        .execute(
            "SELECT * FROM schedules WHERE company_id=:p0 AND employee_id=:p1 AND id != :p2 ORDER BY start_at",
            parameters((company_id(), employee_id, exclude_id)),
        )
        .fetchall()
    )


def list_unavailabilities(employee_id=None):
    return (
        get_db()
        .execute(
            "SELECT u.*, e.name AS employee_name FROM unavailabilities u JOIN employees e ON e.id=u.employee_id WHERE u.company_id=:p0 AND e.company_id=u.company_id AND (CAST(:p1 AS BIGINT) IS NULL OR u.employee_id=:p2) ORDER BY u.start_at DESC",
            parameters((company_id(), employee_id, employee_id)),
        )
        .fetchall()
    )
