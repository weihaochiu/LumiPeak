import ast
import copy
import io
import json
import os
import string
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from plstudio import __version__
from plstudio import i18n, updates


def release(version="v0.6.0", **changes):
    data = {"tag_name": version, "body": "Release notes", "draft": False, "prerelease": False,
            "assets": [{"name": "PL-Studio-Setup.exe", "browser_download_url":
                f"https://github.com/test/PL-Studio/releases/download/{version}/PL-Studio-Setup.exe"}]}
    return data | changes


@pytest.mark.parametrize("tag", ["v0.5.0", "v0.4.9", "invalid", "v0.6.0rc1", "v0.6.0.dev1"])
def test_ignores_old_or_unstable_releases(tag):
    assert updates.parse_release(release(tag), repo="test/PL-Studio") is None


def test_numeric_version_ordering_and_official_asset():
    found = updates.parse_release(release("v0.10.0"), current="0.9.0", repo="test/PL-Studio")
    assert found.version == "0.10.0"
    assert found.notes == "Release notes"
    assert found.download_url.endswith("/PL-Studio-Setup.exe")
    assert updates.parse_release(release(draft=True), repo="test/PL-Studio") is None
    assert updates.parse_release(release(prerelease=True), repo="test/PL-Studio") is None


@pytest.mark.parametrize("url", ["http://github.com/test/PL-Studio/releases/download/v0.6.0/PL-Studio-Setup.exe",
    "https://evil.example/PL-Studio-Setup.exe",
    "https://github.com/other/repo/releases/download/v0.6.0/PL-Studio-Setup.exe"])
def test_rejects_untrusted_downloads(url):
    data = release(assets=[{"name": "PL-Studio-Setup.exe", "browser_download_url": url}])
    with pytest.raises(ValueError):
        updates.parse_release(data, repo="test/PL-Studio")


def test_request_timeout_size_bound_and_offline():
    def opener(request, timeout):
        assert timeout == 8
        assert request.full_url == "https://api.github.com/repos/test/PL-Studio/releases/latest"
        return io.BytesIO(json.dumps(release()).encode())
    assert updates.check_latest("test/PL-Studio", opener=opener).version == "0.6.0"
    with pytest.raises(ValueError):
        updates.check_latest("test/PL-Studio", opener=lambda *a, **k: io.BytesIO(b" " * (512*1024+1)))
    def offline(*args, **kwargs):
        raise TimeoutError("offline")
    with pytest.raises(TimeoutError):
        updates.check_latest("test/PL-Studio", opener=offline)


def test_catalog_covers_messages_and_preserves_format_fields():
    formatter = string.Formatter()
    for source, translated in i18n.CATALOG.items():
        assert translated
        fields = lambda text: sorted(field for _, field, _, _ in formatter.parse(text) if field is not None)
        assert fields(source) == fields(translated), source
    for path in (Path(__file__).parent.parent / "plstudio").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                assert node.args[0].value in i18n.CATALOG, (path.name, node.args[0].value)


def test_saved_warning_translation_keeps_values_and_original_message():
    original = i18n.language()
    warning = "參數 α 接近上下限"
    try:
        i18n.set_language("en", persist=False)
        assert i18n.saved_message(warning) == "參數 α is near a bound"
        i18n.set_language("zh_TW", persist=False)
        assert i18n.saved_message("參數 α is near a bound") == warning
        assert i18n.saved_message("External library message") == "External library message"
    finally:
        i18n.set_language(original, persist=False)


def test_language_switch_preserves_project_and_template_edits(tmp_path, monkeypatch):
    from plstudio.gui import MainWindow
    from tests.test_core import synthetic
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_startup_update", lambda self: None)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(i18n, "preferences", lambda: settings)
    monkeypatch.setattr("plstudio.gui.preferences", lambda: settings)
    original_language = i18n.language()
    i18n.set_language("zh_TW", persist=False)
    w = MainWindow()
    try:
        w.spectra = [synthetic()]
        w.spectra[0].name = "中文 sample α"
        w.current_id = w.spectra[0].id
        w._refresh_tree()
        w._load_controls()
        w.template_dialog.widgets["title"].setText("我的 figure")
        before = copy.deepcopy(w.spectra[0].config)
        w.change_language("en")
        assert w.mode.tabText(0) == "Spectrum analysis"
        assert w.tree.headerItem().text(1) == "User-defined name"
        assert w.spectra[0].name == "中文 sample α"
        assert w.spectra[0].config == before
        assert w.template_dialog.widgets["title"].text() == "我的 figure"
        assert settings.value("language") == "en"
        assert any(b.text() == "Fit current spectrum" for b in w.findChildren(QPushButton))
        w.change_language("zh_TW")
        assert w.mode.tabText(0) == "光譜分析"
        assert w.tree.headerItem().text(1) == "使用者定義名稱"
        assert w.spectra[0].config == before
        assert w.template_dialog.widgets["title"].text() == "我的 figure"
    finally:
        w._maybe_save = lambda: True
        w.close()
        i18n.set_language(original_language, persist=False)
        app.processEvents()


def test_manual_update_without_repository_stays_usable(monkeypatch):
    from plstudio.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("plstudio.gui.repository", lambda: "")
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    w = MainWindow()
    try:
        w.check_updates(manual=True)
        assert messages and w.update_checker.reply is None
        assert w.isEnabled()
    finally:
        w._maybe_save = lambda: True
        w.close()
        app.processEvents()
