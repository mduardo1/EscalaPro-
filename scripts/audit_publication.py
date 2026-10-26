"""Inspeciona candidatos Git sem adicionar arquivos nem imprimir valores privados.

O relatório JSON com hashes fica em tmp/. O manifesto público contém só caminhos.
Execute novamente antes de cada commit; nenhuma heurística certifica ausência de segredos.
"""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "provider_token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|AKIA[A-Z0-9]{16}|sk_live_[A-Za-z0-9]{16,}|re_[A-Za-z0-9]{24,})\b"
    ),
    "authenticated_database_url": re.compile(
        r"postgres(?:ql)?(?:\+psycopg)?://[^\s:@/]+:([^\s@]+)@"
    ),
    "personal_machine_path": re.compile(
        r"[A-Za-z]:[\\/]+Users[\\/]+(?!<|Public[\\/])[^\\/\s`]+", re.I
    ),
    "personal_identifier_requires_review": re.compile(
        r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)|\(\d{2}\)\s*9?\d{4}-\d{4}(?!\d)"
    ),
}
EMAIL = re.compile(r"[A-Za-z0-9_.+%-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
FORBIDDEN = {".env", ".envrc", ".coverage"}
FORBIDDEN_PARTS = {
    "instance",
    "tmp",
    "backups",
    ".venv",
    "private",
    "secrets",
    ".git",
    "__pycache__",
}
SAFE_TEST_PASSWORDS = {
    "fake",
    "fake+password",
    "password",
    "test",
    "isolated-test-only",
    "postgres",
    "pass",
    "other",
    "unused",
    "private",
    "password-sentinel",
    "secret",
    "changed",
}
PUBLIC_DEFAULT_NAMES = {"Administrador", "Minha empresa"}


def protected_name(name):
    path = Path(name)
    return (
        name in FORBIDDEN
        or bool(set(path.parts) & FORBIDDEN_PARTS)
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.suffix.lower()
        in {
            ".sqlite",
            ".sqlite3",
            ".db",
            ".dump",
            ".backup",
            ".pgdump",
            ".pem",
            ".key",
            ".pfx",
            ".p12",
            ".log",
        }
    )


def git(*args, data=None, check=True):
    result = subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True)
    if check and result.returncode:
        raise RuntimeError("Git indisponível ou consulta recusada; detalhes omitidos.")
    return result


def private_values():
    """Valores somente em memória, nunca serializados ou enviados ao terminal."""
    from dotenv import dotenv_values

    values = set()
    if (ROOT / ".env").exists():
        config = dotenv_values(ROOT / ".env", interpolate=False)
        for key, value in config.items():
            if (
                value
                and len(value) >= 8
                and any(
                    word in key.upper()
                    for word in (
                        "SECRET",
                        "PASSWORD",
                        "TOKEN",
                        "API_KEY",
                        "USERNAME",
                        "EMAIL",
                        "SMTP_FROM",
                    )
                )
            ):
                values.add(value)
    # Somente leitura: nomes/e-mails reais servem apenas à detecção de vazamentos.
    for path in (ROOT / "instance").glob("*.sqlite3"):
        with closing(
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            db.execute("PRAGMA query_only=ON")
            for table in ("companies", "users", "employees", "company_settings"):
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for column in ("name", "email", "company_name"):
                    if column in columns:
                        values.update(
                            row[0]
                            for row in db.execute(f"SELECT {column} FROM {table}")
                            if row[0]
                            and len(row[0]) >= 8
                            and (
                                column == "email" or row[0] not in PUBLIC_DEFAULT_NAMES
                            )
                        )
    return values


def inspect_content(name, raw, private):
    findings = []
    text = raw.decode("utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        for category, pattern in PATTERNS.items():
            matches = list(pattern.finditer(line))
            if category == "authenticated_database_url" and name.startswith(
                ("tests/", "compose.test.yml", ".github/workflows/")
            ):
                matches = [
                    match
                    for match in matches
                    if not (
                        match.group(1) in SAFE_TEST_PASSWORDS
                        and re.match(
                            r"(?:localhost|127\.0\.0\.1|postgres)(?=[:/])",
                            line[match.end() :],
                        )
                    )
                ]
            if matches:
                findings.append({"path": name, "line": number, "category": category})
        if any(value.casefold() in line.casefold() for value in private):
            findings.append(
                {
                    "path": name,
                    "line": number,
                    "category": "matches_private_local_value",
                }
            )
        external = [
            match
            for match in EMAIL.finditer(line)
            if not (
                match.group(1).lower()
                in {
                    "example.com",
                    "example.org",
                    "example.net",
                    "example.test",
                    "localhost",
                }
                or match.group(1).lower().endswith((".test", ".invalid"))
            )
        ]
        if external and name not in {
            "app/assets/fonts/LICENSE.txt",
            "app/assets/fonts/DejaVuSans.ttf",
            "app/assets/fonts/DejaVuSans-Bold.ttf",
        }:
            findings.append(
                {"path": name, "line": number, "category": "email_requires_review"}
            )
    if b"SQLite format 3\0" in raw[:16] or raw[:5] == b"PGDMP":
        findings.append({"path": name, "category": "database_content"})
    if re.search(
        r"(?m)^-- (?:PostgreSQL database dump|SQLite database dump)|^COPY .+ FROM stdin;",
        text,
    ):
        findings.append({"path": name, "category": "database_dump_content"})
    if Path(name).name == ".env.example":
        from dotenv import dotenv_values
        from io import StringIO

        template = dotenv_values(stream=StringIO(text), interpolate=False)
        private_keys = {
            "SECRET_KEY",
            "ADMIN_EMAIL",
            "ADMIN_PASSWORD",
            "SMTP_HOST",
            "SMTP_USERNAME",
            "SMTP_PASSWORD",
            "SMTP_FROM",
            "DATABASE_URL",
            "RESEND_API_KEY",
            "MAIL_FROM",
            "EMAIL_OUTBOX_KEY",
            "RESTORE_DATABASE_URL",
        }
        if any(template.get(key) for key in private_keys):
            findings.append(
                {"path": name, "category": "nonempty_private_environment_example"}
            )
    return findings


def audit(*, manifest=False):
    if manifest:
        (ROOT / "PUBLICATION_MANIFEST.txt").touch(exist_ok=True)
    tracked = git("ls-files", "-z").stdout.split(b"\0")
    others = git("ls-files", "--others", "--exclude-standard", "-z").stdout.split(b"\0")
    files = sorted({path.decode("utf-8") for path in tracked + others if path})
    private = private_values()
    findings, hashes = [], {}
    for name in files:
        path = ROOT / name
        ignored = (
            git(
                "check-ignore", "--no-index", "--quiet", "--", name, check=False
            ).returncode
            == 0
        )
        forbidden = protected_name(name)
        if ignored or forbidden or path.is_symlink() or not path.is_file():
            findings.append(
                {"path": name, "category": "protected_or_nonregular_candidate"}
            )
            continue
        raw = path.read_bytes()
        findings.extend(inspect_content(name, raw, private))
        hashes[name] = hashlib.sha256(raw).hexdigest()
    # O índice pode conter conteúdo diferente da cópia de trabalho.
    index_blobs = 0
    for entry in git("ls-files", "--stage", "-z").stdout.split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        index_blobs += 1
        if stage != "0" or mode not in {"100644", "100755"} or protected_name(name):
            findings.append(
                {"path": name, "category": "protected_or_conflicted_index_entry"}
            )
        findings.extend(
            inspect_content(
                f"index:{name}", git("cat-file", "blob", oid).stdout, private
            )
        )
    commits = git("rev-list", "--all", check=False).stdout.splitlines()
    history_objects = 0
    if commits:
        for entry in git("rev-list", "--objects", "--all").stdout.splitlines():
            oid = entry.split(b" ", 1)[0].decode("ascii")
            if git("cat-file", "-t", oid).stdout.strip() == b"blob":
                history_objects += 1
                name = entry.partition(b" ")[2].decode("utf-8")
                if protected_name(name):
                    findings.append(
                        {"path": name, "category": "protected_file_in_history"}
                    )
                findings.extend(
                    inspect_content(
                        f"history-blob:{oid}",
                        git("cat-file", "blob", oid).stdout,
                        private,
                    )
                )
    if manifest and not findings:
        destination = ROOT / "PUBLICATION_MANIFEST.txt"
        destination.write_text("\n".join(files) + "\n", encoding="utf-8")
        hashes[destination.name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    report = {
        "candidate_count": len(files),
        "tracked_count": len([path for path in tracked if path]),
        "staged_count": len(git("diff", "--cached", "--name-only").stdout.splitlines()),
        "history_commits": len(commits),
        "history_blobs_scanned": history_objects,
        "index_blobs_scanned": index_blobs,
        "files": files,
        "sha256": hashes,
        "findings": findings,
        "limits": "Heurísticas e comparação local não constituem certificação de segurança; revisar binários e diffs manualmente.",
    }
    (ROOT / "tmp").mkdir(exist_ok=True)
    (ROOT / "tmp" / "github-publication-audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Atualiza lista pública somente se não houver achados.",
    )
    args = parser.parse_args()
    try:
        report = audit(manifest=args.manifest)
    except OSError, RuntimeError, sqlite3.Error:
        parser.exit(
            1,
            "Auditoria incompleta: acesso recusado ou ferramenta indisponível; detalhes privados omitidos.\n",
        )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "candidate_count",
                    "tracked_count",
                    "staged_count",
                    "history_commits",
                    "history_blobs_scanned",
                    "findings",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(1 if report["findings"] else 0)


if __name__ == "__main__":
    main()
