from app.database import get_db, parameters
from app.tenant import company_id


def get_settings():
    return (
        get_db()
        .execute(
            "SELECT * FROM company_settings WHERE company_id=:p0",
            parameters((company_id(),)),
        )
        .fetchone()
    )


def save_settings(company_name, min_rest_hours, weekly_alerts):
    db = get_db()
    db.execute(
        "UPDATE company_settings SET company_name=:p0,min_rest_hours=:p1,weekly_alerts=:p2 WHERE company_id=:p3",
        parameters((company_name, min_rest_hours, int(weekly_alerts), company_id())),
    )
    db.execute(
        "UPDATE companies SET name=:p0 WHERE id=:p1",
        parameters((company_name, company_id())),
    )
    db.commit()
