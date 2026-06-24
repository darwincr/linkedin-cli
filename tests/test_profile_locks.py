from __future__ import annotations

import os

from linkedin_cli.profile_locks import remove_stale_chromium_locks


def test_removes_singleton_files_for_dead_pid(tmp_path):
    os.symlink(f"host-{99999999}", tmp_path / "SingletonLock")
    os.symlink("cookie", tmp_path / "SingletonCookie")
    os.symlink("socket", tmp_path / "SingletonSocket")

    remove_stale_chromium_locks(tmp_path)

    assert not (tmp_path / "SingletonLock").exists()
    assert not (tmp_path / "SingletonCookie").exists()
    assert not (tmp_path / "SingletonSocket").exists()


def test_keeps_singleton_files_for_running_pid(tmp_path):
    os.symlink(f"host-{os.getpid()}", tmp_path / "SingletonLock")
    os.symlink("cookie", tmp_path / "SingletonCookie")

    remove_stale_chromium_locks(tmp_path)

    assert (tmp_path / "SingletonLock").is_symlink()
    assert (tmp_path / "SingletonCookie").is_symlink()
