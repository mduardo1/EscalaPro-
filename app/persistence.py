"""Adaptação PostgreSQL ao contrato pequeno usado pelos modelos existentes."""

from sqlalchemy import text


class Record:
    def __init__(self, row):
        self.row = row

    def __getitem__(self, key):
        return self.row[key] if isinstance(key, int) else self.row._mapping[key]

    def __iter__(self):
        return iter(self.row)

    def keys(self):
        return self.row._mapping.keys()


class Result:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return Record(row) if row is not None else None

    def fetchall(self):
        return [Record(row) for row in self.cursor.fetchall()]


class PostgresConnection:
    def __init__(self, engine):
        self.connection = engine.connect()

    def execute(self, statement, values=None):
        if values is not None and not isinstance(values, dict):
            raise TypeError("PostgreSQL requer parâmetros nomeados.")
        return Result(self.connection.execute(text(statement), values or {}))

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()
