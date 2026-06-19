"""Tests for version label and build metadata helpers."""

import app_meta


def test_version_label_release_only(monkeypatch):
    monkeypatch.setattr(
        app_meta,
        "get_build_info",
        lambda: {"sha": "", "branch": "", "describe": ""},
    )
    assert app_meta.get_version_label() == f"v{app_meta.APP_VERSION}"


def test_version_label_dev_build(monkeypatch):
    monkeypatch.setattr(
        app_meta,
        "get_build_info",
        lambda: {"sha": "47d575a", "branch": "dev", "describe": "v0.7.0-15-g47d575a"},
    )
    assert app_meta.get_version_label() == f"v{app_meta.APP_VERSION} · dev@47d575a"


def test_version_label_main_build_shows_sha(monkeypatch):
    monkeypatch.setattr(
        app_meta,
        "get_build_info",
        lambda: {"sha": "abc1234", "branch": "main", "describe": "v0.9.2"},
    )
    assert app_meta.get_version_label() == f"v{app_meta.APP_VERSION} · abc1234"


def test_get_commit_url(monkeypatch):
    monkeypatch.setattr(
        app_meta,
        "get_build_info",
        lambda: {"sha": "47d575a", "branch": "dev", "describe": "v0.7.0-15-g47d575a"},
    )
    about = app_meta.get_about_info()
    assert about["build"]["describe"] == "v0.7.0-15-g47d575a"
    assert about["commit_url"].endswith("/commit/47d575a")
