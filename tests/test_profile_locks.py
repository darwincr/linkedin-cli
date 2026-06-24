from __future__ import annotations

import os

from linkedin_cli.profile_locks import remove_stale_chromium_locks


def test_removes_singleton_files_for_dead_pid(tmp_path):
    os.symlink(f"host-{99999999}", tmp_path / "SingletonLock")
    os.symlink("cookie", tmp_path / "SingletonCookie")
    os.symlink("socket", tmp_path / "SingletonSocket")

    remove_stale_chromium_locks(tmp_path)

    assert not (tmp_path / "SingletonLock").is_symlink()
    assert not (tmp_path / "SingletonCookie").is_symlink()
    assert not (tmp_path / "SingletonSocket").is_symlink()


def test_removes_singleton_files_for_non_chromium_running_pid(monkeypatch, tmp_path):
    import linkedin_cli.profile_locks as profile_locks

    pid = os.getpid()
    os.symlink(f"host-{pid}", tmp_path / "SingletonLock")
    os.symlink("cookie", tmp_path / "SingletonCookie")

    monkeypatch.setattr(profile_locks, "_process_cmdline", lambda _: ["/usr/bin/python"])

    remove_stale_chromium_locks(tmp_path)

    assert not (tmp_path / "SingletonLock").is_symlink()
    assert not (tmp_path / "SingletonCookie").is_symlink()


def test_keeps_singleton_files_for_chromium_owner(monkeypatch, tmp_path):
    import linkedin_cli.profile_locks as profile_locks

    pid = os.getpid()
    os.symlink(f"host-{pid}", tmp_path / "SingletonLock")
    os.symlink("cookie", tmp_path / "SingletonCookie")

    monkeypatch.setattr(profile_locks, "_process_cmdline", lambda _: ["/opt/chrome", f"--user-data-dir={tmp_path}"])

    remove_stale_chromium_locks(tmp_path)

    assert (tmp_path / "SingletonLock").is_symlink()
    assert (tmp_path / "SingletonCookie").is_symlink()
