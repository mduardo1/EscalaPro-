"""A auditoria inspeciona conteúdo real do índice, além da cópia de trabalho."""

import json
from pathlib import Path
import subprocess

import pytest

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


def commit_fixture(root):
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Audit Test",
            "-c",
            "user.email=audit@example.test",
            "commit",
            "-qm",
            "test fixture",
        ],
        check=True,
        capture_output=True,
    )


def test_approved_test_urls_and_vendor_attribution_in_index_and_history(
    tmp_path, monkeypatch
):
    root = temporary_repository(tmp_path, monkeypatch)
    (root / "tests").mkdir()
    (root / "tests/test_fake.py").write_text(
        "postgresql://fake:isolated-test-only@localhost/escalapro_test",
        encoding="utf-8",
    )
    fonts = root / "app/assets/fonts"
    fonts.mkdir(parents=True)
    (fonts / "LICENSE.txt").write_bytes(b"Font author <author@" + b"vendor.example>")
    subprocess.run(
        ["git", "-C", str(root), "add", "."], check=True, capture_output=True
    )
    commit_fixture(root)
    report = audit.audit()
    assert report["history_commits"] == 1
    assert report["index_blobs_scanned"] == 3
    assert not report["findings"]


@pytest.mark.parametrize("history", [False, True])
def test_environment_template_secret_is_checked_in_every_git_layer(
    tmp_path, monkeypatch, history
):
    root = temporary_repository(tmp_path, monkeypatch)
    target = root / ".env.example"
    target.write_text(
        "SECRET_KEY=fictitious-template-value-for-regression", encoding="utf-8"
    )
    subprocess.run(
        ["git", "-C", str(root), "add", ".env.example"], check=True, capture_output=True
    )
    if history:
        commit_fixture(root)
    target.write_text("SECRET_KEY=", encoding="utf-8")
    report = audit.audit()
    origin = "history-blob:" if history else "index:"
    assert any(
        row["path"].startswith(origin)
        and row["category"] == "nonempty_private_environment_example"
        for row in report["findings"]
    )


def test_git_test_url_exception_does_not_allow_unapproved_password(
    tmp_path, monkeypatch
):
    root = temporary_repository(tmp_path, monkeypatch)
    (root / "tests").mkdir()
    target = root / "tests/test_fake.py"
    target.write_text(
        "postgresql://fake:" + "unapproved-sentinel@localhost/escalapro_test",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(root), "add", "."], check=True, capture_output=True
    )
    commit_fixture(root)
    target.write_text("clean working tree", encoding="utf-8")
    report = audit.audit()
    assert any(
        row["path"].startswith("index:")
        and row["category"] == "authenticated_database_url"
        for row in report["findings"]
    )
    assert any(
        row["path"].startswith("history-blob:")
        and row["category"] == "authenticated_database_url"
        for row in report["findings"]
    )
