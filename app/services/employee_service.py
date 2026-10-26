from app.services.validation import email_value, number_value, text_value


def validate_employee(form):
    return {
        "name": text_value(form.get("name", ""), "Nome", 2),
        "role": text_value(form.get("role", ""), "Cargo", 2, 80),
        "department": text_value(form.get("department", ""), "Setor", 2, 80),
        "email": email_value(form.get("email", "")),
        "weekly_hours": number_value(
            form.get("weekly_hours"), "Jornada semanal", 0.5, 168
        ),
    }
