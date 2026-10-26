-- Base compatível com o MVP anterior. app/migrations.py acrescenta empresas,
-- verificações e integridade por empresa, preservando tabelas e dados existentes.
-- Use init-db em instalação nova ou migrate-db para atualizar com backup.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 2 AND 100),
    role TEXT NOT NULL,
    department TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    weekly_hours REAL NOT NULL CHECK(weekly_hours > 0 AND weekly_hours <= 168)
);
CREATE INDEX IF NOT EXISTS idx_employees_name ON employees(name);
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    break_minutes INTEGER NOT NULL CHECK(break_minutes >= 0 AND break_minutes < 1440),
    color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
    shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE RESTRICT,
    work_date TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL CHECK(end_at > start_at),
    shift_name TEXT NOT NULL,
    break_minutes INTEGER NOT NULL CHECK(break_minutes >= 0),
    color TEXT NOT NULL,
    UNIQUE(employee_id, work_date, shift_id)
);
CREATE INDEX IF NOT EXISTS idx_schedules_employee_period ON schedules(employee_id, start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_schedules_period ON schedules(start_at, end_at);
CREATE TABLE IF NOT EXISTS unavailabilities (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL CHECK(end_at > start_at),
    reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unavailability_period ON unavailabilities(employee_id, start_at, end_at);
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    company_name TEXT NOT NULL DEFAULT 'Minha empresa',
    min_rest_hours REAL NOT NULL DEFAULT 0 CHECK(min_rest_hours BETWEEN 0 AND 72),
    weekly_alerts INTEGER NOT NULL DEFAULT 1 CHECK(weekly_alerts IN (0,1))
);
INSERT OR IGNORE INTO settings(id) VALUES(1);
CREATE TABLE IF NOT EXISTS login_attempts (
    identifier TEXT PRIMARY KEY,
    failures INTEGER NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);
