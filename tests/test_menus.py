import json

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QMessageBox, QToolBar

from plstudio import i18n
from tests.test_core import synthetic
from tests.test_gui import app, window


def entries(menu):
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_menu_structure_language_and_busy_commands(window):
    original = i18n.language()
    try:
        window.change_language("zh_TW")
        assert entries(window.menuBar()) == ["檔案", "圖形", "設定", "說明"]
        assert entries(window.file_menu) == [
            "新增專案", "開啟專案…", "儲存專案", "另存新檔…", "匯入資料…", "匯出", "結束"]
        assert entries(window.export_menu) == ["圖片…", "Excel…", "Origin 資料包…", "Origin 專案（.opju）…"]
        assert entries(window.figure_menu) == ["圖形版面設定（Figure Template）…", "載入圖形模板…", "儲存圖形模板…"]
        assert entries(window.settings_menu) == ["語言 / Language", "啟動時檢查更新"]
        assert entries(window.help_menu) == ["使用說明", "立即檢查更新…", "關於 PL Studio…"]
        assert window.findChild(QToolBar, "mainToolBar") is None
        window._set_commands_enabled(False)
        assert all(not action.isEnabled() for action in window.command_actions)
        window._set_commands_enabled(True)
        assert all(action.isEnabled() for action in window.command_actions)
        window.change_language("en")
        assert entries(window.menuBar()) == ["File", "Figure", "Settings", "Help"]
        assert "Export" in entries(window.file_menu)
        assert entries(window.export_menu)[0] == "Images…"
        assert window.save_as_action.shortcut().toString() == "Ctrl+Shift+S"
        assert window.help_menu.actions()[0].shortcut().toString() == "F1"
        assert [a.data() for a in window.language_actions.actions() if a.isChecked()] == ["en"]
        window.change_language("zh_TW")
        assert entries(window.menuBar()) == ["檔案", "圖形", "設定", "說明"]
        assert [a.data() for a in window.language_actions.actions() if a.isChecked()] == ["zh_TW"]
    finally:
        window._set_commands_enabled(True)
        window.change_language(original)


def test_file_menu_import_save_as_open_and_shortcuts(window, app, monkeypatch, tmp_path):
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    source = tmp_path / "spectrum.txt"
    source.write_bytes(synthetic().raw)
    saved = tmp_path / "analysis.plproj"
    copied = tmp_path / "analysis_copy.plproj"
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a: ([str(source)], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(saved), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(saved), ""))
    window.activateWindow()
    window.search.setFocus()
    app.processEvents()
    QTest.keyClick(window.search, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert len(window.spectra) == 1
    QTest.keyClick(window.search, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert saved.exists() and not window.dirty
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(copied), ""))
    window.save_as_action.trigger()
    assert copied.exists() and window.project_path == str(copied)
    window.new_action.trigger()
    assert not window.spectra
    window.open_action.trigger()
    assert len(window.spectra) == 1 and window.project_path == str(saved)


def test_figure_menu_uses_all_figure_templates(window, monkeypatch, tmp_path):
    path = tmp_path / "figures.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(path), ""))
    actions = [a for a in window.figure_menu.actions() if not a.isSeparator()]
    actions[2].trigger()
    assert window.template_dialog.isVisible()
    template = json.loads(path.read_text("utf-8"))
    assert template["version"] == 2
    assert set(template["figures"]) == {"spectrum", "overlay", "trends"}
    template["figures"]["spectrum"]["title"] = "Loaded spectrum"
    template["figures"]["overlay"]["title"] = "Loaded overlay"
    path.write_text(json.dumps(template), encoding="utf-8")
    actions[1].trigger()
    assert window.plot_settings["title"] == "Loaded spectrum"
    assert window._read_overlay_inputs()["title"] == "Loaded overlay"
    window.template_dialog.close()
