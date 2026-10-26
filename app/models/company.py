from app.database import get_db, parameters


def create_company(name):
    """Participa da transação do chamador, inclusive na ativação da conta."""
    db = get_db()
    cursor = db.execute(
        "INSERT INTO companies(name) VALUES(:p0) RETURNING id", parameters((name,))
    )
    company_id = cursor.fetchone()[0]
    db.execute(
        "INSERT INTO company_settings(company_id,company_name) VALUES(:p0,:p1)",
        parameters((company_id, name)),
    )
    return company_id
