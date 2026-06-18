"""Tests for version label and build metadata helpers."""

import build_info
import app_meta


def test_version_label_release_only(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_SHA", "")
    monkeypatch.setattr(build_info, "BUILD_BRANCH", "")
    monkeypatch.setattr(build_info, "BUILD_DESCRIBE", "")
    assert app_meta.get_version_label() == f"v{app_meta.APP_VERSION}"


def test_version_label_dev_build(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_SHA", "47d575a")
    monkeypatch.setattr(build_info, "BUILD_BRANCH", "dev")
    monkeypatch.setattr(build_info, "BUILD_DESCRIBE", "v0.7.0-15-g47d575a")
    assert app_meta.get_version_label() == f"v{app_meta.APP_VERSION} · dev@47d575a"


def test_version_label_main_build_shows_sha(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_SHA", "abc1234")
    monkeypatch.setattr(build_info, "BUILD_BRANCH", "main")
    monkeypatch.setattr(build_info, "BUILD_DESCRIBE", "v0.9.2")
    assert app_meta.get_version_label() == f"v{app_meta.APP_VERSION} · abc1234"


def test_get_commit_url(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_SHA", "47d575a")
    monkeypatch.setattr(build_info, "BUILD_BRANCH", "dev")
    monkeypatch.setattr(build_info, "BUILD_DESCRIBE", "v0.7.0-15-g47d575a")
    about = app_meta.get_about_info()
    assert about["build"]["describe"] == "v0.7.0-15-g47d575a"
    assert about["commit_url"].endswith("/commit/47d575a")
