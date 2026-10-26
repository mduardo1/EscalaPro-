from app.database import get_db, parameters
from app.tenant import company_id


def list_shifts():
    return (
        get_db()
        .execute(
            "SELECT * FROM shifts WHERE company_id=:p0 ORDER BY start_time,name",
            parameters((company_id(),)),
        )
        .fetchall()
    )


def get_shift(shift_id):
    return (
        get_db()
        .execute(
            "SELECT * FROM shifts WHERE id=:p0 AND company_id=:p1",
            parameters((shift_id, company_id())),
        )
        .fetchone()
    )


def save_shift(data, shift_id=None):
    db = get_db()
    values = tuple(
        data[key]
        for key in ("name", "start_time", "end_time", "break_minutes", "color")
    )
    if shift_id is None:
        cursor = db.execute(
            "INSERT INTO shifts(name,start_time,end_time,break_minutes,color,company_id) VALUES(:p0,:p1,:p2,:p3,:p4,:p5) RETURNING id",
            parameters((*values, company_id())),
        )
        shift_id = cursor.fetchone()[0]
    else:
        db.execute(
            "UPDATE shifts SET name=:p0,start_time=:p1,end_time=:p2,break_minutes=:p3,color=:p4 WHERE id=:p5 AND company_id=:p6",
            parameters((*values, shift_id, company_id())),
        )
    db.commit()
    return shift_id
