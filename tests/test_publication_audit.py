"""A auditoria inspeciona conteúdo real do índice, além da cópia de trabalho."""

import json
from pathlib import Path
import subprocess

from scripts import audit_publication as audit


def temporary_repository(tmp_path, monkeypatch):
    subprocess.run(
        ["git", "init", "-q", str(tmp_path)], check=True, capture_output=True
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    (tmp_path / ".gitignore").write_text(".env\ntmp/\ninstance/\n", encoding="utf-8")
    return tmp_path


def test_publication_excludes_private_files_and_generates_exact_manifest(
    tmp_path, monkeypatch
):
    root = temporary_repository(tmp_path, monkeypatch)
    (root / ".env").write_text(
        "SECRET_KEY=fictitious-private-sentinel-value\n", encoding="utf-8"
    )
    (root / ".env.example").write_text("SECRET_KEY=\n", encoding="utf-8")
    (root / "README.md").write_text("Only fictional public content", encoding="utf-8")
    report = audit.audit(manifest=True)
    assert not report["findings"]
    assert ".env" not in report["files"]
    assert report["staged_count"] == report["history_commits"] == 0
    assert (root / "PUBLICATION_MANIFEST.txt").read_text().splitlines() == report[
        "files"
    ]
    assert report["sha256"]["README.md"]


def test_publication_detects_private_copy_without_disclosing_value(
    tmp_path, monkeypatch
):
    root = temporary_repository(tmp_path, monkeypatch)
    sentinel = "fictitious-sensitive-key-only-for-test"
    (root / ".env").write_text(f"SECRET_KEY={sentinel}\n", encoding="utf-8")
    (root / "leak.txt").write_text(sentinel, encoding="utf-8")
    report = audit.audit(manifest=True)
    assert any(
        row["category"] == "matches_private_local_value" for row in report["findings"]
    )
    assert sentinel not in json.dumps(report)
    assert not (root / "PUBLICATION_MANIFEST.txt").read_text()


def test_publication_checks_staged_blob_even_if_working_copy_is_clean(
    tmp_path, monkeypatch
):
    root = temporary_repository(tmp_path, monkeypatch)
    target = root / "file.txt"
    target.write_text("-----BEGIN " + "PRIVATE KEY-----", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(root), "add", "--", "file.txt"],
        check=True,
        capture_output=True,
    )
    target.write_text("clean working copy", encoding="utf-8")
    report = audit.audit()
    assert report["staged_count"] == report["index_blobs_scanned"] == 1
    assert any(
        row["path"] == "index:file.txt" and row["category"] == "private_key"
        for row in report["findings"]
    )


def test_publication_flags_force_tracked_database(tmp_path, monkeypatch):
    root = temporary_repository(tmp_path, monkeypatch)
    (root / "instance").mkdir()
    (root / "instance/data.db").write_bytes(b"SQLite format 3\x00")
    subprocess.run(
        ["git", "-C", str(root), "add", "-f", "--", "instance/data.db"],
        check=True,
        capture_output=True,
    )
    report = audit.audit()
    assert any("protected" in row["category"] for row in report["findings"])
    assert any(row["category"] == "database_content" for row in report["findings"])


def test_external_email_requires_review_except_reserved_and_vendor_license():
    assert audit.inspect_content("README.md", b"person@example.com", set()) == []
    findings = audit.inspect_content(
        "README.md", b"person@" + b"unreviewed.example", set()
    )
    assert findings[0]["category"] == "email_requires_review"


def test_publication_rejects_nonempty_secret_in_environment_example():
    findings = audit.inspect_content(
        ".env.example", b"SECRET_KEY=fictitious-unapproved-template-secret", set()
    )
    assert any(
        row["category"] == "nonempty_private_environment_example" for row in findings
    )


def test_publication_recognizes_plain_database_dump_disguised_as_text():
    findings = audit.inspect_content(
        "notes.txt", b"-- PostgreSQL database dump\n", set()
    )
    assert any(row["category"] == "database_dump_content" for row in findings)
