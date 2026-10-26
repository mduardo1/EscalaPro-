from app.database import get_db, parameters
from app.tenant import company_id


def list_employees(query="", active_only=False):
    # LIKE é parametrizado; curingas digitados pelo usuário são tratados como texto.
    query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return (
        get_db()
        .execute(
            "SELECT * FROM employees WHERE company_id=:p0 AND (lower(name) LIKE lower(:p1) ESCAPE '\\' OR lower(department) LIKE lower(:p2) ESCAPE '\\' OR lower(role) LIKE lower(:p3) ESCAPE '\\') AND (:p4 = 0 OR active = 1) ORDER BY active DESC, lower(name)",
            parameters(
                (
                    company_id(),
                    f"%{query}%",
                    f"%{query}%",
                    f"%{query}%",
                    int(active_only),
                )
            ),
        )
        .fetchall()
    )


def get_employee(employee_id):
    return (
        get_db()
        .execute(
            "SELECT * FROM employees WHERE id=:p0 AND company_id=:p1",
            parameters((employee_id, company_id())),
        )
        .fetchone()
    )


def save_employee(data, employee_id=None):
    db = get_db()
    values = (
        data["name"],
        data["role"],
        data["department"],
        data["email"],
        data["weekly_hours"],
    )
    if employee_id is None:
        cursor = db.execute(
            "INSERT INTO employees(name,role,department,email,weekly_hours,company_id) VALUES(:p0,:p1,:p2,:p3,:p4,:p5) RETURNING id",
            parameters((*values, company_id())),
        )
        employee_id = cursor.fetchone()[0]
    else:
        db.execute(
            "UPDATE employees SET name=:p0,role=:p1,department=:p2,email=:p3,weekly_hours=:p4 WHERE id=:p5 AND company_id=:p6",
            parameters((*values, employee_id, company_id())),
        )
    db.commit()
    return employee_id


def set_active(employee_id, active):
    db = get_db()
    db.execute(
        "UPDATE employees SET active=:p0 WHERE id=:p1 AND company_id=:p2",
        parameters((int(active), employee_id, company_id())),
    )
    db.commit()
